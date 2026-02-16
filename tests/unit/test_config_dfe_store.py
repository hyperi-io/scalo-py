"""Tests for DirectoryConfigStore."""

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from hyperi_pylib.config import DirectoryConfigStore


@pytest.fixture
def config_dir(tmp_path):
    """Create a temp directory with sample YAML config files."""
    # dfe-loader.yaml
    loader_config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "loader_db",
        },
        "batch_size": 1000,
        "enabled": True,
    }
    (tmp_path / "dfe-loader.yaml").write_text(yaml.safe_dump(loader_config))

    # dfe-engine.yaml
    engine_config = {
        "workers": 4,
        "timeout": 30,
        "features": {
            "anonymizer": True,
            "metrics": True,
        },
    }
    (tmp_path / "dfe-engine.yaml").write_text(yaml.safe_dump(engine_config))

    # empty.yaml
    (tmp_path / "empty.yaml").write_text("")

    return tmp_path


@pytest.fixture
def store(config_dir):
    """Create a DirectoryConfigStore with sample data."""
    s = DirectoryConfigStore(config_dir, refresh_interval=0)
    s.start()
    yield s
    s.stop()


class TestConstructor:
    """Test DirectoryConfigStore initialization."""

    def test_basic_init(self, config_dir):
        store = DirectoryConfigStore(config_dir)
        assert store._directory == config_dir
        assert store._refresh_interval == 30
        assert store._writable is True
        assert store._is_git is False

    def test_nonexistent_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            DirectoryConfigStore(tmp_path / "nonexistent")

    def test_writable_auto_detect(self, config_dir):
        store = DirectoryConfigStore(config_dir)
        assert store._writable is True

    def test_writable_override(self, config_dir):
        store = DirectoryConfigStore(config_dir, writable=False)
        assert store._writable is False

    def test_custom_refresh_interval(self, config_dir):
        store = DirectoryConfigStore(config_dir, refresh_interval=10)
        assert store._refresh_interval == 10

    def test_git_branch_without_repo_raises(self, config_dir):
        with pytest.raises(ValueError, match="not a git repo"):
            DirectoryConfigStore(config_dir, git_branch="staging")


class TestRead:
    """Test read operations."""

    def test_get_full_table(self, store):
        data = store.get("dfe-loader")
        assert data["database"]["host"] == "localhost"
        assert data["database"]["port"] == 5432
        assert data["batch_size"] == 1000

    def test_get_dot_notation_key(self, store):
        assert store.get("dfe-loader", "database.host") == "localhost"
        assert store.get("dfe-loader", "database.port") == 5432

    def test_get_nested_key(self, store):
        assert store.get("dfe-engine", "features.anonymizer") is True

    def test_get_top_level_key(self, store):
        assert store.get("dfe-loader", "batch_size") == 1000

    def test_get_missing_key_returns_default(self, store):
        assert store.get("dfe-loader", "nonexistent") is None
        assert store.get("dfe-loader", "nonexistent", "fallback") == "fallback"

    def test_get_missing_table_returns_default(self, store):
        assert store.get("nonexistent") is None
        assert store.get("nonexistent", default={"key": "val"}) == {"key": "val"}

    def test_get_empty_yaml_returns_empty_dict(self, store):
        data = store.get("empty")
        assert data == {}

    def test_get_returns_copy(self, store):
        """Ensure get() returns a copy, not a reference to the cache."""
        data1 = store.get("dfe-loader")
        data1["mutated"] = True
        data2 = store.get("dfe-loader")
        assert "mutated" not in data2


class TestListTables:
    """Test table listing."""

    def test_list_tables(self, store):
        tables = store.list_tables()
        assert "dfe-loader" in tables
        assert "dfe-engine" in tables
        assert "empty" in tables

    def test_list_tables_sorted(self, store):
        tables = store.list_tables()
        assert tables == sorted(tables)

    def test_list_tables_excludes_non_yaml(self, config_dir):
        (config_dir / "README.md").write_text("# not yaml")
        (config_dir / "notes.txt").write_text("just notes")
        store = DirectoryConfigStore(config_dir, refresh_interval=0)
        store.start()
        tables = store.list_tables()
        assert "README" not in tables
        assert "notes" not in tables
        store.stop()

    def test_list_tables_includes_yml(self, config_dir):
        (config_dir / "alt-config.yml").write_text(yaml.safe_dump({"key": "value"}))
        store = DirectoryConfigStore(config_dir, refresh_interval=0)
        store.start()
        assert "alt-config" in store.list_tables()
        store.stop()


class TestWrite:
    """Test write operations."""

    def test_set_new_key(self, store, config_dir):
        store.set("dfe-loader", "new_key", "new_value")
        assert store.get("dfe-loader", "new_key") == "new_value"

        # Verify persisted to disk
        data = yaml.safe_load((config_dir / "dfe-loader.yaml").read_text())
        assert data["new_key"] == "new_value"

    def test_set_nested_key(self, store, config_dir):
        store.set("dfe-loader", "database.host", "new-host.example.com")
        assert store.get("dfe-loader", "database.host") == "new-host.example.com"

        data = yaml.safe_load((config_dir / "dfe-loader.yaml").read_text())
        assert data["database"]["host"] == "new-host.example.com"

    def test_set_creates_new_table(self, store, config_dir):
        store.set("new-table", "key", "value")
        assert store.get("new-table", "key") == "value"
        assert (config_dir / "new-table.yaml").exists()

    def test_set_deep_nested_key(self, store):
        store.set("dfe-engine", "features.new.deep.key", "deep_value")
        assert store.get("dfe-engine", "features.new.deep.key") == "deep_value"

    def test_set_readonly_raises(self, config_dir):
        store = DirectoryConfigStore(config_dir, writable=False, refresh_interval=0)
        store.start()
        with pytest.raises(PermissionError, match="read-only"):
            store.set("dfe-loader", "key", "val")
        store.stop()

    def test_delete_key(self, store, config_dir):
        store.delete("dfe-loader", "batch_size")
        assert store.get("dfe-loader", "batch_size") is None

        data = yaml.safe_load((config_dir / "dfe-loader.yaml").read_text())
        assert "batch_size" not in data

    def test_delete_nested_key(self, store, config_dir):
        store.delete("dfe-engine", "features.anonymizer")
        assert store.get("dfe-engine", "features.anonymizer") is None

        data = yaml.safe_load((config_dir / "dfe-engine.yaml").read_text())
        assert "anonymizer" not in data["features"]

    def test_delete_missing_key_raises(self, store):
        with pytest.raises(KeyError, match="not found"):
            store.delete("dfe-loader", "nonexistent.key")

    def test_delete_missing_table_raises(self, store):
        with pytest.raises(KeyError, match="does not exist"):
            store.delete("nonexistent-table", "key")

    def test_delete_readonly_raises(self, config_dir):
        store = DirectoryConfigStore(config_dir, writable=False, refresh_interval=0)
        store.start()
        with pytest.raises(PermissionError, match="read-only"):
            store.delete("dfe-loader", "batch_size")
        store.stop()


class TestCorruptYAML:
    """Test handling of corrupt/invalid YAML files."""

    def test_corrupt_yaml_keeps_last_good(self, store, config_dir):
        # Verify initial good state
        assert store.get("dfe-loader", "database.host") == "localhost"

        # Corrupt the file
        (config_dir / "dfe-loader.yaml").write_text("{{{{invalid yaml: [")

        # Trigger refresh
        store._refresh_all()

        # Should still have last good version
        assert store.get("dfe-loader", "database.host") == "localhost"

    def test_non_dict_yaml_skipped(self, config_dir):
        (config_dir / "bad.yaml").write_text("- just\n- a\n- list\n")
        store = DirectoryConfigStore(config_dir, refresh_interval=0)
        store.start()
        assert store.get("bad") is None
        store.stop()


class TestRefresh:
    """Test background refresh and change detection."""

    def test_refresh_detects_file_change(self, store, config_dir):
        assert store.get("dfe-loader", "batch_size") == 1000

        # Modify file externally (simulate external change)
        data = yaml.safe_load((config_dir / "dfe-loader.yaml").read_text())
        data["batch_size"] = 2000
        # Ensure mtime changes (some filesystems have 1s resolution)
        time.sleep(0.05)
        (config_dir / "dfe-loader.yaml").write_text(yaml.safe_dump(data))

        # Force mtime bump for fast filesystems
        path = config_dir / "dfe-loader.yaml"
        mtime = path.stat().st_mtime + 1
        import os

        os.utime(str(path), (mtime, mtime))

        # Trigger refresh
        store._refresh_all()

        assert store.get("dfe-loader", "batch_size") == 2000

    def test_refresh_detects_new_file(self, store, config_dir):
        assert "new-service" not in store.list_tables()

        (config_dir / "new-service.yaml").write_text(yaml.safe_dump({"port": 8080}))
        store._refresh_all()

        assert store.get("new-service", "port") == 8080


class TestWatchers:
    """Test change notification callbacks."""

    def test_on_change_called_on_set(self, store):
        changes = []
        store.on_change("dfe-loader", lambda table, data: changes.append((table, data)))

        store.set("dfe-loader", "batch_size", 2000)

        assert len(changes) == 1
        assert changes[0][0] == "dfe-loader"
        assert changes[0][1]["batch_size"] == 2000

    def test_on_change_called_on_external_change(self, store, config_dir):
        changes = []
        store.on_change("dfe-loader", lambda table, data: changes.append((table, data)))

        # Modify file externally
        data = yaml.safe_load((config_dir / "dfe-loader.yaml").read_text())
        data["batch_size"] = 5000
        path = config_dir / "dfe-loader.yaml"
        path.write_text(yaml.safe_dump(data))
        # Bump mtime
        mtime = path.stat().st_mtime + 1
        import os

        os.utime(str(path), (mtime, mtime))

        store._refresh_all()

        assert len(changes) == 1
        assert changes[0][1]["batch_size"] == 5000

    def test_on_change_not_called_when_unchanged(self, store):
        changes = []
        store.on_change("dfe-loader", lambda _table, _data: changes.append(1))

        # Refresh without any changes
        store._refresh_all()

        assert len(changes) == 0

    def test_multiple_watchers(self, store):
        changes_a = []
        changes_b = []
        store.on_change("dfe-loader", lambda _t, _d: changes_a.append(1))
        store.on_change("dfe-loader", lambda _t, _d: changes_b.append(1))

        store.set("dfe-loader", "batch_size", 3000)

        assert len(changes_a) == 1
        assert len(changes_b) == 1

    def test_callback_error_does_not_break_others(self, store):
        changes = []

        def bad_callback(_t, _d):
            raise RuntimeError("callback error")

        store.on_change("dfe-loader", bad_callback)
        store.on_change("dfe-loader", lambda _t, _d: changes.append(1))

        store.set("dfe-loader", "batch_size", 4000)

        # Second callback should still be called
        assert len(changes) == 1


class TestNestedKeyAccess:
    """Test dot-notation key utilities."""

    def test_get_nested_simple(self):
        d = {"a": {"b": {"c": 42}}}
        assert DirectoryConfigStore._get_nested(d, "a.b.c") == 42

    def test_get_nested_missing(self):
        d = {"a": {"b": 1}}
        assert DirectoryConfigStore._get_nested(d, "a.c") is None
        assert DirectoryConfigStore._get_nested(d, "a.c", "default") == "default"

    def test_get_nested_non_dict_intermediate(self):
        d = {"a": "string"}
        assert DirectoryConfigStore._get_nested(d, "a.b") is None

    def test_set_nested_creates_path(self):
        d = {}
        DirectoryConfigStore._set_nested(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_set_nested_overwrites(self):
        d = {"a": {"b": {"c": 1}}}
        DirectoryConfigStore._set_nested(d, "a.b.c", 2)
        assert d["a"]["b"]["c"] == 2

    def test_delete_nested_simple(self):
        d = {"a": {"b": 1, "c": 2}}
        DirectoryConfigStore._delete_nested(d, "a.b")
        assert d == {"a": {"c": 2}}

    def test_delete_nested_missing_raises(self):
        d = {"a": 1}
        with pytest.raises(KeyError):
            DirectoryConfigStore._delete_nested(d, "b")

    def test_delete_nested_deep_missing_raises(self):
        d = {"a": {"b": 1}}
        with pytest.raises(KeyError):
            DirectoryConfigStore._delete_nested(d, "a.c")


class TestThreadSafety:
    """Test concurrent read access."""

    def test_concurrent_reads(self, store):
        errors = []
        results = []

        def read_config():
            try:
                for _ in range(100):
                    val = store.get("dfe-loader", "database.host")
                    results.append(val)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_config) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == "localhost" for r in results)


class TestContextManager:
    """Test context manager protocol."""

    def test_context_manager(self, config_dir):
        with DirectoryConfigStore(config_dir, refresh_interval=0) as store:
            assert store.get("dfe-loader", "database.host") == "localhost"


class TestGitDetection:
    """Test git repository detection (without a real git repo)."""

    def test_not_git_repo(self, config_dir):
        store = DirectoryConfigStore(config_dir)
        assert store.is_git is False
        assert store.current_branch is None

    def test_list_branches_not_git_raises(self, config_dir):
        store = DirectoryConfigStore(config_dir)
        with pytest.raises(RuntimeError, match="not a git repository"):
            store.list_branches()

    def test_switch_branch_not_git_raises(self, config_dir):
        store = DirectoryConfigStore(config_dir)
        with pytest.raises(RuntimeError, match="not a git repository"):
            store.switch_branch("feature-branch")
