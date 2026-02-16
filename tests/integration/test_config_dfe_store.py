"""Integration tests for DirectoryConfigStore with git operations."""

import subprocess

import pytest
import yaml

from hyperi_pylib.config import DirectoryConfigStore


def _git(cwd, *args):
    """Run a git command in a directory."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


@pytest.fixture
def git_config_dir(tmp_path):
    """Create a temp directory with a git repo and sample YAML configs."""
    # Init git repo
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")

    # Create initial config files
    loader_config = {
        "database": {"host": "localhost", "port": 5432},
        "batch_size": 1000,
    }
    (tmp_path / "dfe-loader.yaml").write_text(yaml.safe_dump(loader_config))

    engine_config = {
        "workers": 4,
        "timeout": 30,
    }
    (tmp_path / "dfe-engine.yaml").write_text(yaml.safe_dump(engine_config))

    # Initial commit
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "Initial config")

    return tmp_path


class TestGitDetection:
    """Test git repository detection with a real repo."""

    def test_detects_git_repo(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        assert store.is_git is True

    def test_current_branch(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        # Default branch may be 'main' or 'master' depending on git config
        branch = store.current_branch
        assert branch in ("main", "master")


class TestGitBranches:
    """Test branch management."""

    def test_list_branches(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        branches = store.list_branches()
        assert len(branches) >= 1

    def test_switch_to_new_branch(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.switch_branch("staging", create=True)
        assert store.current_branch == "staging"

        branches = store.list_branches()
        assert "staging" in branches
        store.stop()

    def test_switch_to_existing_branch(self, git_config_dir):
        # Create a branch manually
        _git(git_config_dir, "branch", "feature-x")

        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.switch_branch("feature-x")
        assert store.current_branch == "feature-x"
        store.stop()

    def test_switch_to_nonexistent_branch_raises(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        with pytest.raises(ValueError, match="does not exist"):
            store.switch_branch("nonexistent")
        store.stop()

    def test_git_branch_constructor_param(self, git_config_dir):
        """Test that git_branch in constructor creates and checks out the branch."""
        store = DirectoryConfigStore(git_config_dir, git_branch="auto-created", refresh_interval=0)
        assert store.current_branch == "auto-created"

    def test_branch_switch_refreshes_cache(self, git_config_dir):
        """Test that switching branches reloads config from the new branch's files."""
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        # Create branch and modify config on it
        store.switch_branch("modified", create=True)
        store.set("dfe-loader", "batch_size", 9999, message="Change batch size")

        # Switch back to original branch
        # We're already on 'modified', go back
        main_branch = [b for b in store.list_branches() if b != "modified"][0]
        store.switch_branch(main_branch)

        # Should have the original value
        assert store.get("dfe-loader", "batch_size") == 1000

        # Switch back to modified
        store.switch_branch("modified")
        assert store.get("dfe-loader", "batch_size") == 9999

        store.stop()


class TestGitCommits:
    """Test git commit behavior on writes."""

    def test_set_creates_git_commit(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.set("dfe-loader", "database.host", "new-host.example.com", message="Update DB host")

        # Verify commit was created
        log = _git(git_config_dir, "log", "--oneline", "-1")
        assert "Update DB host" in log
        store.stop()

    def test_set_with_author(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.set(
            "dfe-loader",
            "batch_size",
            2000,
            message="Increase batch size",
            author="Admin <admin@hyperi.io>",
        )

        # Verify author
        log = _git(git_config_dir, "log", "-1", "--format=%an <%ae>")
        assert "Admin" in log
        assert "admin@hyperi.io" in log
        store.stop()

    def test_set_default_commit_message(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.set("dfe-loader", "batch_size", 3000)

        log = _git(git_config_dir, "log", "--oneline", "-1")
        assert "config: set dfe-loader.batch_size" in log
        store.stop()

    def test_delete_creates_git_commit(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.delete("dfe-loader", "batch_size", message="Remove batch_size")

        log = _git(git_config_dir, "log", "--oneline", "-1")
        assert "Remove batch_size" in log
        store.stop()

    def test_multiple_commits(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.set("dfe-loader", "batch_size", 2000, message="Change 1")
        store.set("dfe-loader", "batch_size", 3000, message="Change 2")
        store.set("dfe-engine", "workers", 8, message="Change 3")

        # Should have 3 new commits (+ initial)
        log = _git(git_config_dir, "log", "--oneline")
        lines = log.strip().splitlines()
        assert len(lines) >= 4  # initial + 3 changes
        store.stop()

    def test_no_commit_without_message_in_git_repo(self, git_config_dir):
        """Even without explicit message, a default message is generated."""
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        initial_count = len(_git(git_config_dir, "log", "--oneline").splitlines())
        store.set("dfe-loader", "batch_size", 5000)
        new_count = len(_git(git_config_dir, "log", "--oneline").splitlines())

        assert new_count == initial_count + 1
        store.stop()


class TestGitHistory:
    """Test that git provides a full audit trail."""

    def test_diff_shows_change(self, git_config_dir):
        store = DirectoryConfigStore(git_config_dir, refresh_interval=0)
        store.start()

        store.set("dfe-loader", "database.host", "prod-db.example.com", message="Migrate to prod DB")

        # Check that diff shows the change
        diff = _git(git_config_dir, "log", "-1", "-p", "--", "dfe-loader.yaml")
        assert "prod-db.example.com" in diff
        store.stop()
