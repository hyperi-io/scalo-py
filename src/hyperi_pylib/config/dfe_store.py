"""
Directory-based Configuration Store for hyperi-pylib.

Provides a YAML directory-backed configuration store where each YAML file
represents a config "table" (analogous to a database table). Supports
in-memory caching with background polling refresh, thread-safe access,
and optional git-aware writes with audit trail.

Key Features:
- Each YAML file in the directory = one config table
- In-memory cache with background polling refresh (works on S3/FUSE mounts)
- Thread-safe reads via RLock
- Write support with advisory file locking
- Git-aware: auto-commit changes, branch management, optional push
- Change callbacks for reactive configuration

Usage:
    from hyperi_pylib.config import DirectoryConfigStore

    store = DirectoryConfigStore("/config/dfe", refresh_interval=30)
    store.start()

    # Read
    config = store.get("dfe-loader")
    host = store.get("dfe-loader", "database.host")

    # Write (if writable)
    store.set("dfe-loader", "database.host", "new-host",
              message="Update DB host", author="derek@hyperi.io")

    # Git branch management
    store.list_branches()
    store.switch_branch("staging", create=True)

    store.stop()
"""

import fcntl
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from ..logger import logger


class DirectoryConfigStore:
    """
    YAML directory-based configuration store with optional git awareness.

    Each YAML file in the directory is a "table". Supports in-memory caching
    with background refresh, thread-safe reads, and git-tracked writes.

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

        # Auto-detect git
        self._is_git = self._check_git_repo()

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

    # ── Lifecycle ──────────────────────────────────────────────────────

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
        logger.debug("DirectoryConfigStore stopped")

    def __enter__(self):
        """Context manager entry — calls start()."""
        self.start()
        return self

    def __exit__(self, *args):
        """Context manager exit — calls stop()."""
        self.stop()

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, table: str, key: str | None = None, default: Any = None) -> Any:
        """
        Get config value from a table.

        Args:
            table: Table name (YAML filename without extension).
            key: Optional dot-notation key (e.g. "database.host").
                 If None, returns the entire table dict.
            default: Value to return if key not found.

        Returns:
            Config value, or default if not found.
        """
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
        List available config tables.

        Returns:
            Sorted list of table names (YAML filenames without extension).
        """
        tables = []
        for path in self._directory.iterdir():
            if path.is_file() and path.suffix in (".yaml", ".yml"):
                tables.append(path.stem)
        return sorted(tables)

    # ── Write ──────────────────────────────────────────────────────────

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

    # ── Git ────────────────────────────────────────────────────────────

    @property
    def is_git(self) -> bool:
        """Whether the config directory is inside a git repository."""
        return self._is_git

    @property
    def current_branch(self) -> str | None:
        """Current git branch name, or None if not a git repo or detached HEAD."""
        if not self._is_git:
            return None
        result = self._git_run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if result is None:
            return None
        branch = result.strip()
        return None if branch == "HEAD" else branch

    def list_branches(self) -> list[str]:
        """
        List all local git branches.

        Returns:
            Sorted list of branch names.

        Raises:
            RuntimeError: If not a git repo.
        """
        if not self._is_git:
            raise RuntimeError("Directory is not a git repository")

        result = self._git_run(["git", "branch", "--list", "--format=%(refname:short)"])
        if result is None:
            return []
        return sorted(line.strip() for line in result.strip().splitlines() if line.strip())

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
        if not self._is_git:
            raise RuntimeError("Directory is not a git repository")

        existing = self.list_branches()

        if branch in existing:
            self._git_run(["git", "checkout", branch])
        elif create:
            self._git_run(["git", "checkout", "-b", branch])
        else:
            raise ValueError(f"Branch '{branch}' does not exist. Use create=True to create it.")

        logger.info(f"Switched to branch: {branch}")

        # Refresh cache after branch switch (files may differ)
        self._refresh_all()

    # ── Watch ──────────────────────────────────────────────────────────

    def on_change(self, table: str, callback: Callable[[str, dict], None]) -> None:
        """
        Register a callback for when a table's config changes.

        The callback receives (table_name, new_data_dict) and is invoked
        from the background refresh thread.

        Args:
            table: Table name to watch.
            callback: Function called with (table_name, data) on change.
        """
        if table not in self._watchers:
            self._watchers[table] = []
        self._watchers[table].append(callback)

    # ── Internal: Cache & Refresh ──────────────────────────────────────

    def _refresh_loop(self) -> None:
        """Background polling loop."""
        while not self._shutdown_event.wait(timeout=self._refresh_interval):
            try:
                self._refresh_all()
            except Exception as e:
                logger.error(f"Config refresh failed: {e}")

    def _refresh_all(self) -> None:
        """Re-read all YAML files, detect changes, notify watchers."""
        for path in self._directory.iterdir():
            if not path.is_file() or path.suffix not in (".yaml", ".yml"):
                continue

            table = path.stem
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

            # File changed or new — reload
            data = self._load_yaml(path)
            if data is None:
                # Parse error — keep last good version
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

    # ── Internal: YAML I/O ─────────────────────────────────────────────

    def _table_path(self, table: str) -> Path:
        """Get the YAML file path for a table name."""
        # Try .yaml first, then .yml
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

    # ── Internal: Nested Key Access ────────────────────────────────────

    @staticmethod
    def _get_nested(d: dict, key: str, default: Any = None) -> Any:
        """
        Get nested dict value from dot-notation key.

        Example: _get_nested({"database": {"host": "localhost"}}, "database.host")
                 → "localhost"
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
                 → {"database": {"host": "localhost"}}
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

    # ── Internal: Git ──────────────────────────────────────────────────

    def _check_git_repo(self) -> bool:
        """Check if the directory is inside a git repository."""
        result = self._git_run(["git", "rev-parse", "--git-dir"])
        return result is not None

    def _git_run(self, cmd: list[str], check: bool = False) -> str | None:
        """
        Run a git command in the config directory.

        Returns:
            stdout as string, or None on failure.
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._directory),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                if check:
                    logger.error(f"Git command failed: {' '.join(cmd)}: {result.stderr.strip()}")
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            if check:
                logger.error(f"Git command error: {e}")
            return None

    def _git_commit(self, file_path: Path, message: str, author: str | None = None) -> None:
        """Stage and commit a file."""
        # Stage the file
        rel_path = file_path.relative_to(self._directory)
        self._git_run(["git", "add", str(rel_path)], check=True)

        # Build commit command
        cmd = ["git", "commit", "-m", message]
        if author:
            cmd.extend(["--author", author])

        result = self._git_run(cmd, check=True)
        if result is not None:
            logger.debug(f"Git commit: {message}")

    def _git_push_remote(self) -> None:
        """Push to the remote origin."""
        branch = self.current_branch
        if branch is None:
            logger.warning("Cannot push: detached HEAD")
            return
        result = self._git_run(["git", "push", "origin", branch], check=True)
        if result is not None:
            logger.debug(f"Git pushed to origin/{branch}")
