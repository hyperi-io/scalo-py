"""
Directory-based Configuration Store for hyperi-pylib.

Provides a YAML directory-backed configuration store where each YAML file
represents a config "table" (analogous to a database table). Supports
in-memory caching with background polling refresh, thread-safe access,
and optional git-aware writes with audit trail.

Git operations use dulwich (pure-Python git) -- no system git binary required.
Safe for containers and environments where git is not installed.

Key Features:
- Each YAML file in the directory = one config table
- Subdirectory support: table names are path-like (e.g. "loaders/dfe-loader")
- In-memory cache with background polling refresh (works on S3/FUSE mounts)
- Thread-safe reads via RLock
- Write support with advisory file locking
- Git-aware: auto-commit changes, branch management, optional push
- Change callbacks for reactive configuration

Usage:
    from hyperi_pylib.config import DirectoryConfigStore

    store = DirectoryConfigStore("/config/dfe", refresh_interval=30)
    store.start()

    # Read -- root-level table
    config = store.get("dfe-loader")
    host = store.get("dfe-loader", "database.host")

    # Read -- subdirectory table (path-like name)
    loader = store.get("loaders/dfe-loader", "database.host")

    # Write (if writable) -- creates subdirectories automatically
    store.set("loaders/dfe-loader", "database.host", "new-host",
              message="Update DB host", author="derek@hyperi.io")

    # Git branch management
    store.list_branches()
    store.switch_branch("staging", create=True)

    store.stop()
"""

import fcntl
import os
import threading
from pathlib import Path
from typing import Any, Callable

import yaml
from dulwich import porcelain as git
from dulwich.errors import NotGitRepository
from dulwich.repo import Repo as DulwichRepo

from ..logger import logger


class DirectoryConfigStore:
    """
    YAML directory-based configuration store with optional git awareness.

    Each YAML file in the directory (and subdirectories) is a "table".
    Table names use forward-slash paths: root files are just the stem
    (e.g. "globals"), subdirectory files include the path prefix
    (e.g. "loaders/dfe-loader", "monitoring/alerts/thresholds").

    Supports in-memory caching with background refresh, thread-safe reads,
    and git-tracked writes. Git operations use dulwich (pure-Python) -- no
    git binary required.

    Args:
        directory: Path to the YAML config directory.
        refresh_interval: Seconds between background refresh polls.
        writable: Whether writes are allowed. None = auto-detect from permissions.
        git_branch: Branch to checkout for writes. None = use current branch.
        git_push: Automatically push after git commits.
    """

    def __init__(
        self,
        directory: str | Path,
        refresh_interval: int = 30,
        writable: bool | None = None,
        git_branch: str | None = None,
        git_push: bool = False,
    ):
        self._directory = Path(directory).resolve()
        self._refresh_interval = refresh_interval
        self._git_push = git_push

        if not self._directory.is_dir():
            raise FileNotFoundError(f"Config directory does not exist: {self._directory}")

        # Auto-detect writability
        if writable is None:
            self._writable = os.access(str(self._directory), os.W_OK)
        else:
            self._writable = writable

        # Auto-detect git repo using dulwich
        self._repo: DulwichRepo | None = None
        self._is_git = self._open_git_repo()

        # In-memory cache: table_name -> (data_dict, file_mtime)
        self._cache: dict[str, tuple[dict, float]] = {}
        self._lock = threading.RLock()

        # Change watchers: table_name -> list of callbacks
        self._watchers: dict[str, list[Callable[[str, dict], None]]] = {}

        # Background refresh thread
        self._shutdown_event = threading.Event()
        self._refresh_thread: threading.Thread | None = None

        # If git_branch specified, checkout at init (after cache/lock init)
        if git_branch is not None:
            if not self._is_git:
                raise ValueError(f"git_branch='{git_branch}' specified but directory is not a git repo")
            self.switch_branch(git_branch, create=True)

        logger.info(
            f"DirectoryConfigStore initialized: dir={self._directory}, "
            f"writable={self._writable}, git={self._is_git}, "
            f"refresh={self._refresh_interval}s"
        )

    # -- Lifecycle ------------------------------------------------------

    def start(self) -> None:
        """Load initial data and start background polling."""
        self._refresh_all()

        if self._refresh_interval > 0:
            self._shutdown_event.clear()
            self._refresh_thread = threading.Thread(
                target=self._refresh_loop,
                name="directory-config-refresh",
                daemon=True,
            )
            self._refresh_thread.start()
            logger.debug(f"Background refresh started (interval={self._refresh_interval}s)")

    def stop(self) -> None:
        """Stop background polling and cleanup."""
        self._shutdown_event.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=10)
            self._refresh_thread = None
        if self._repo is not None:
            self._repo.close()
            self._repo = None
        logger.debug("DirectoryConfigStore stopped")

    def __enter__(self):
        """Context manager entry -- calls start()."""
        self.start()
        return self

    def __exit__(self, *args):
        """Context manager exit -- calls stop()."""
        self.stop()

    # -- Read -----------------------------------------------------------

    def get(self, table: str, key: str | None = None, default: Any = None) -> Any:
        """
        Get config value from a table.

        Args:
            table: Table name -- bare name for root files (e.g. "globals"),
                   path-like for subdirectories (e.g. "loaders/dfe-loader").
            key: Optional dot-notation key (e.g. "database.host").
                 If None, returns the entire table dict.
            default: Value to return if key not found.

        Returns:
            Config value, or default if not found.
        """
        table = self._validate_table_name(table)
        with self._lock:
            entry = self._cache.get(table)
            if entry is None:
                return default
            data, _ = entry
            if key is None:
                return data.copy()
            return self._get_nested(data, key, default)

    def list_tables(self) -> list[str]:
        """
        List available config tables (including subdirectories).

        Returns:
            Sorted list of table names. Root files return bare names
            (e.g. "globals"), subdirectory files return path-like names
            (e.g. "loaders/dfe-loader").
        """
        tables = set()
        for pattern in ("**/*.yaml", "**/*.yml"):
            for path in self._directory.glob(pattern):
                if path.is_file():
                    tables.add(self._path_to_table(self._directory, path))
        return sorted(tables)

    # -- Write ----------------------------------------------------------

    def set(
        self,
        table: str,
        key: str,
        value: Any,
        *,
        message: str | None = None,
        author: str | None = None,
    ) -> None:
        """
        Set a config value in a table.

        Writes to the YAML file, updates cache, and optionally commits to git.

        Args:
            table: Table name (YAML filename without extension).
            key: Dot-notation key (e.g. "database.host").
            value: Value to set.
            message: Git commit message (used only if directory is a git repo).
            author: Git author string (e.g. "Name <email>").

        Raises:
            PermissionError: If store is not writable.
        """
        if not self._writable:
            raise PermissionError("DirectoryConfigStore is read-only")

        table = self._validate_table_name(table)
        file_path = self._table_path(table)
        data = self._load_yaml_locked(file_path) or {}
        self._set_nested(data, key, value)
        self._write_yaml_locked(file_path, data)

        # Update cache
        mtime = file_path.stat().st_mtime
        with self._lock:
            self._cache[table] = (data, mtime)

        # Git commit
        if self._is_git:
            commit_msg = message or f"config: set {table}.{key}"
            self._git_commit(file_path, commit_msg, author)
            if self._git_push:
                self._git_push_remote()

        # Notify watchers
        self._notify_watchers(table, data)

    def delete(
        self,
        table: str,
        key: str,
        *,
        message: str | None = None,
        author: str | None = None,
    ) -> None:
        """
        Delete a config key from a table.

        Args:
            table: Table name.
            key: Dot-notation key to delete.
            message: Git commit message.
            author: Git author string.

        Raises:
            PermissionError: If store is not writable.
            KeyError: If key does not exist.
        """
        if not self._writable:
            raise PermissionError("DirectoryConfigStore is read-only")

        table = self._validate_table_name(table)
        file_path = self._table_path(table)
        data = self._load_yaml_locked(file_path)
        if data is None:
            raise KeyError(f"Table '{table}' does not exist")

        self._delete_nested(data, key)
        self._write_yaml_locked(file_path, data)

        # Update cache
        mtime = file_path.stat().st_mtime
        with self._lock:
            self._cache[table] = (data, mtime)

        # Git commit
        if self._is_git:
            commit_msg = message or f"config: delete {table}.{key}"
            self._git_commit(file_path, commit_msg, author)
            if self._git_push:
                self._git_push_remote()

        # Notify watchers
        self._notify_watchers(table, data)

    # -- Git ------------------------------------------------------------

    @property
    def is_git(self) -> bool:
        """Whether the config directory is inside a git repository."""
        return self._is_git

    @property
    def current_branch(self) -> str | None:
        """Current git branch name, or None if not a git repo or detached HEAD."""
        if not self._is_git or self._repo is None:
            return None
        try:
            symrefs = self._repo.refs.get_symrefs()
            head_target = symrefs.get(b"HEAD", b"")
            if head_target.startswith(b"refs/heads/"):
                return head_target[len(b"refs/heads/") :].decode("utf-8")
            return None
        except Exception:
            return None

    def list_branches(self) -> list[str]:
        """
        List all local git branches.

        Returns:
            Sorted list of branch names.

        Raises:
            RuntimeError: If not a git repo.
        """
        if not self._is_git or self._repo is None:
            raise RuntimeError("Directory is not a git repository")

        branches = []
        for ref in self._repo.refs:
            ref_str = ref.decode("utf-8") if isinstance(ref, bytes) else ref
            if ref_str.startswith("refs/heads/"):
                branches.append(ref_str[len("refs/heads/") :])

        return sorted(branches)

    def switch_branch(self, branch: str, create: bool = False) -> None:
        """
        Switch to a git branch.

        Args:
            branch: Branch name.
            create: If True, create the branch if it doesn't exist.
                    If False, raise ValueError if branch doesn't exist.

        Raises:
            RuntimeError: If not a git repo.
            ValueError: If branch doesn't exist and create=False.
        """
        if not self._is_git or self._repo is None:
            raise RuntimeError("Directory is not a git repository")

        ref_name = f"refs/heads/{branch}".encode()
        existing = self.list_branches()

        if branch in existing:
            # Switch HEAD to point at existing branch
            self._repo.refs.set_symbolic_ref(b"HEAD", ref_name)
            # Update working tree
            self._checkout_head()
        elif create:
            # Create branch from current HEAD, then switch
            head_sha = self._repo.head()
            self._repo.refs[ref_name] = head_sha
            self._repo.refs.set_symbolic_ref(b"HEAD", ref_name)
            # Working tree already matches HEAD, no checkout needed
        else:
            raise ValueError(f"Branch '{branch}' does not exist. Use create=True to create it.")

        logger.info(f"Switched to branch: {branch}")

        # Refresh cache after branch switch (files may differ)
        self._refresh_all()

    # -- Watch ----------------------------------------------------------

    def on_change(self, table: str, callback: Callable[[str, dict], None]) -> None:
        """
        Register a callback for when a table's config changes.

        The callback receives (table_name, new_data_dict) and is invoked
        from the background refresh thread.

        Args:
            table: Table name to watch (supports path-like names e.g. "loaders/dfe-loader").
            callback: Function called with (table_name, data) on change.
        """
        table = self._validate_table_name(table)
        if table not in self._watchers:
            self._watchers[table] = []
        self._watchers[table].append(callback)

    # -- Internal: Cache & Refresh --------------------------------------

    def _refresh_loop(self) -> None:
        """Background polling loop."""
        while not self._shutdown_event.wait(timeout=self._refresh_interval):
            try:
                self._refresh_all()
            except Exception as e:
                logger.error(f"Config refresh failed: {e}")

    def _refresh_all(self) -> None:
        """Re-read all YAML files (including subdirectories), detect changes, notify watchers."""
        yaml_files = []
        for pattern in ("**/*.yaml", "**/*.yml"):
            yaml_files.extend(p for p in self._directory.glob(pattern) if p.is_file())

        for path in yaml_files:
            table = self._path_to_table(self._directory, path)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            with self._lock:
                cached = self._cache.get(table)
                if cached is not None:
                    _, cached_mtime = cached
                    if mtime == cached_mtime:
                        continue

            # File changed or new -- reload
            data = self._load_yaml(path)
            if data is None:
                # Parse error -- keep last good version
                continue

            with self._lock:
                old_entry = self._cache.get(table)
                self._cache[table] = (data, mtime)

            # Notify watchers if data actually changed
            if old_entry is not None:
                old_data, _ = old_entry
                if old_data != data:
                    self._notify_watchers(table, data)

    def _notify_watchers(self, table: str, data: dict) -> None:
        """Invoke registered change callbacks for a table."""
        callbacks = self._watchers.get(table, [])
        for cb in callbacks:
            try:
                cb(table, data)
            except Exception as e:
                logger.error(f"Config change callback error for '{table}': {e}")

    # -- Internal: Table Name Handling ---------------------------------

    @staticmethod
    def _validate_table_name(table: str) -> str:
        """
        Validate and normalise a table name.

        Normalises backslashes to forward slashes, strips leading/trailing
        slashes, and rejects path traversal attempts.

        Args:
            table: Table name to validate.

        Returns:
            Normalised table name.

        Raises:
            ValueError: If table name contains path traversal or is absolute.
        """
        # Normalise backslashes
        table = table.replace("\\", "/")
        # Strip leading/trailing slashes
        table = table.strip("/")

        if ".." in table.split("/"):
            raise ValueError(f"Table name must not contain '..': {table}")
        if not table:
            raise ValueError("Table name must not be empty")

        return table

    @staticmethod
    def _path_to_table(base_dir: Path, file_path: Path) -> str:
        """
        Convert a YAML file path to a table name.

        Args:
            base_dir: The config root directory.
            file_path: Absolute path to a YAML file.

        Returns:
            Table name with forward-slash separators (e.g. "loaders/dfe-loader").
        """
        rel = file_path.relative_to(base_dir)
        return str(rel.with_suffix("")).replace(os.sep, "/")

    # -- Internal: YAML I/O ---------------------------------------------

    def _table_path(self, table: str) -> Path:
        """Get the YAML file path for a table name (supports subdirectories)."""
        # Table name uses "/" separators -- convert to path components
        path = self._directory / f"{table}.yaml"
        if not path.exists():
            yml_path = self._directory / f"{table}.yml"
            if yml_path.exists():
                return yml_path
        return path

    def _load_yaml(self, path: Path) -> dict | None:
        """
        Safely load a YAML file.

        Returns:
            Parsed dict, or None on error.
        """
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            if data is None:
                return {}
            if not isinstance(data, dict):
                logger.warning(f"YAML file is not a mapping: {path}")
                return None
            return data
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse YAML {path}: {e}")
            return None
        except OSError as e:
            logger.warning(f"Failed to read {path}: {e}")
            return None

    def _load_yaml_locked(self, path: Path) -> dict | None:
        """Load YAML with advisory file lock."""
        if not path.exists():
            return None
        try:
            fd = os.open(str(path), os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_SH)
                data = self._load_yaml(path)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            return data
        except OSError as e:
            logger.warning(f"Failed to lock/read {path}: {e}")
            return self._load_yaml(path)

    def _write_yaml_locked(self, path: Path, data: dict) -> None:
        """Write YAML with advisory file lock."""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                content = yaml.safe_dump(data, default_flow_style=False, sort_keys=True)
                os.write(fd, content.encode("utf-8"))
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        except OSError as e:
            raise OSError(f"Failed to write {path}: {e}") from e

    # -- Internal: Nested Key Access ------------------------------------

    @staticmethod
    def _get_nested(d: dict, key: str, default: Any = None) -> Any:
        """
        Get nested dict value from dot-notation key.

        Example: _get_nested({"database": {"host": "localhost"}}, "database.host")
                 -> "localhost"
        """
        keys = key.split(".")
        current = d
        for k in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(k)
            if current is None:
                return default
        return current

    @staticmethod
    def _set_nested(d: dict, key: str, value: Any) -> None:
        """
        Set nested dict value from dot-notation key.

        Example: _set_nested({}, "database.host", "localhost")
                 -> {"database": {"host": "localhost"}}
        """
        keys = key.split(".")
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    @staticmethod
    def _delete_nested(d: dict, key: str) -> None:
        """
        Delete nested dict value from dot-notation key.

        Raises KeyError if key doesn't exist.
        """
        keys = key.split(".")
        current = d
        for k in keys[:-1]:
            if not isinstance(current, dict) or k not in current:
                raise KeyError(f"Key '{key}' not found")
            current = current[k]
        if not isinstance(current, dict) or keys[-1] not in current:
            raise KeyError(f"Key '{key}' not found")
        del current[keys[-1]]

    # -- Internal: Git (dulwich) ----------------------------------------

    def _open_git_repo(self) -> bool:
        """Try to open the directory as a dulwich git repo."""
        try:
            self._repo = DulwichRepo.discover(str(self._directory))
            return True
        except NotGitRepository:
            self._repo = None
            return False
        except Exception as e:
            logger.warning(f"Failed to open git repo at {self._directory}: {e}")
            self._repo = None
            return False

    def _checkout_head(self) -> None:
        """Update working tree to match HEAD (after branch switch)."""
        if self._repo is None:
            return
        try:
            from dulwich.index import build_index_from_tree

            head_commit = self._repo[self._repo.head()]
            index_path = os.path.join(self._repo.controldir(), "index")
            build_index_from_tree(
                self._repo.path,
                index_path,
                self._repo.object_store,
                head_commit.tree,
            )
        except Exception as e:
            logger.error(f"Failed to checkout HEAD: {e}")

    def _git_commit(self, file_path: Path, message: str, author: str | None = None) -> None:
        """Stage and commit a file using dulwich."""
        if self._repo is None:
            return

        try:
            repo_root = Path(self._repo.path)
            rel_path = str(file_path.relative_to(repo_root))

            # Stage and commit via porcelain
            git.add(self._repo, paths=[rel_path])

            author_bytes = author.encode("utf-8") if author else None
            commit_id = git.commit(
                self._repo,
                message=message.encode("utf-8"),
                author=author_bytes,
                committer=author_bytes,
            )
            logger.debug(f"Git commit {commit_id.decode()[:8]}: {message}")
        except Exception as e:
            logger.error(f"Git commit failed: {e}")

    def _git_push_remote(self) -> None:
        """Push current branch to remote origin using dulwich."""
        if self._repo is None:
            return

        branch = self.current_branch
        if branch is None:
            logger.warning("Cannot push: detached HEAD")
            return

        try:
            refspec = f"refs/heads/{branch}".encode()
            git.push(self._repo, remote_location="origin", refspecs=[refspec])
            logger.debug(f"Git pushed to origin/{branch}")
        except Exception as e:
            logger.error(f"Git push failed: {e}")
