"""
Unit tests for hyperi_pylib.config.merge module.

Tests config file merging with:
- Valid data for all supported file types
- Invalid data and error handling
- Auto-detection logic
- Multiple merge strategies
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from hyperi_pylib.config.merge import (
    detect_file_type,
    merge_files,
    merge_gitignore,
    merge_json,
    merge_toml,
    merge_yaml,
)


class TestFileTypeDetection:
    """Test file type auto-detection."""

    def test_detect_json_by_extension(self):
        """Test JSON detection by .json extension."""
        assert detect_file_type(Path("config.json")) == "json"

    def test_detect_yaml_by_extension(self):
        """Test YAML detection by .yaml/.yml extension."""
        assert detect_file_type(Path("config.yaml")) == "yaml"
        assert detect_file_type(Path("config.yml")) == "yaml"

    def test_detect_toml_by_extension(self):
        """Test TOML detection by .toml extension."""
        assert detect_file_type(Path("pyproject.toml")) == "toml"

    def test_detect_gitignore_by_name(self):
        """Test .gitignore detection by filename."""
        assert detect_file_type(Path(".gitignore")) == "gitignore"
        assert detect_file_type(Path(".dockerignore")) == "gitignore"

    def test_detect_env_by_name(self):
        """Test .env detection by filename."""
        assert detect_file_type(Path(".env")) == "env"

    def test_detect_json_by_content(self, tmp_path):
        """Test JSON detection by content (no extension)."""
        file = tmp_path / "noext"
        file.write_text('{"key": "value"}')
        assert detect_file_type(file) == "json"

    def test_detect_yaml_by_content(self, tmp_path):
        """Test YAML detection by content."""
        file = tmp_path / "noext"
        file.write_text("---\nkey: value")
        assert detect_file_type(file) == "yaml"


class TestMergeJSON:
    """Test JSON file merging."""

    def test_merge_json_deep_nested(self, tmp_path):
        """Test deep merge of nested JSON structures."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text(json.dumps({"a": {"b": 2}, "c": 3}))
        target.write_text(json.dumps({"a": {"x": 1}, "d": 4}))

        result = merge_json(source, target)

        assert result == {"a": {"x": 1, "b": 2}, "c": 3, "d": 4}

    def test_merge_json_arrays(self, tmp_path):
        """Test JSON array merging (concatenates)."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text(json.dumps({"items": [3, 4]}))
        target.write_text(json.dumps({"items": [1, 2]}))

        result = merge_json(source, target)

        assert result["items"] == [1, 2, 3, 4]

    def test_merge_json_target_missing(self, tmp_path):
        """Test JSON merge when target doesn't exist."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text(json.dumps({"key": "value"}))

        result = merge_json(source, target)

        assert result == {"key": "value"}

    def test_merge_json_invalid_syntax(self, tmp_path):
        """Test error handling for invalid JSON."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text("{invalid json}")
        target.write_text("{}")

        with pytest.raises(json.JSONDecodeError):
            merge_json(source, target)


class TestMergeYAML:
    """Test YAML file merging."""

    def test_merge_yaml_deep_nested(self, tmp_path):
        """Test deep merge of nested YAML structures."""
        source = tmp_path / "source.yaml"
        target = tmp_path / "target.yaml"

        source.write_text("a:\n  b: 2\nc: 3")
        target.write_text("a:\n  x: 1\nd: 4")

        result = merge_yaml(source, target)

        assert result == {"a": {"x": 1, "b": 2}, "c": 3, "d": 4}

    def test_merge_yaml_lists(self, tmp_path):
        """Test YAML list merging."""
        source = tmp_path / "source.yaml"
        target = tmp_path / "target.yaml"

        source.write_text("items:\n  - three\n  - four")
        target.write_text("items:\n  - one\n  - two")

        result = merge_yaml(source, target)

        assert result["items"] == ["one", "two", "three", "four"]

    def test_merge_yaml_invalid_syntax(self, tmp_path):
        """Test error handling for invalid YAML."""
        source = tmp_path / "source.yaml"
        target = tmp_path / "target.yaml"

        source.write_text("invalid: yaml:\n  - [unclosed")
        target.write_text("key: value")

        with pytest.raises(yaml.YAMLError):
            merge_yaml(source, target)


class TestMergeTOML:
    """Test TOML file merging."""

    def test_merge_toml_tables(self, tmp_path):
        """Test TOML table merging."""
        source = tmp_path / "source.toml"
        target = tmp_path / "target.toml"

        source.write_text("[section]\nb = 2\nc = 3")
        target.write_text("[section]\na = 1\n[other]\nx = 10")

        result = merge_toml(source, target)

        assert result == {"section": {"a": 1, "b": 2, "c": 3}, "other": {"x": 10}}

    def test_merge_toml_arrays(self, tmp_path):
        """Test TOML array merging."""
        source = tmp_path / "source.toml"
        target = tmp_path / "target.toml"

        source.write_text("items = [3, 4]")
        target.write_text("items = [1, 2]")

        result = merge_toml(source, target)

        assert result["items"] == [1, 2, 3, 4]

    def test_merge_toml_invalid_syntax(self, tmp_path):
        """Test error handling for invalid TOML."""
        source = tmp_path / "source.toml"
        target = tmp_path / "target.toml"

        source.write_text("[unclosed\nkey = value")
        target.write_text("key = 'value'")

        with pytest.raises(Exception):  # tomllib.TOMLDecodeError
            merge_toml(source, target)


class TestMergeGitignore:
    """Test gitignore-style file merging."""

    def test_merge_gitignore_deduplicates(self, tmp_path):
        """Test gitignore merge deduplicates patterns."""
        source = tmp_path / ".gitignore"
        target = tmp_path / "target"

        source.write_text("*.log\n*.tmp\n.venv/\n")
        target.write_text("*.pyc\n*.log\n__pycache__/\n")

        result = merge_gitignore(source, target)

        assert "*.log" in result
        assert result.count("*.log") == 1  # Deduplicated
        assert "*.tmp" in result
        assert "*.pyc" in result

    def test_merge_gitignore_preserves_order(self, tmp_path):
        """Test gitignore merge preserves target order."""
        source = tmp_path / "source"
        target = tmp_path / "target"

        source.write_text("new1\nnew2\n")
        target.write_text("old1\nold2\n")

        result = merge_gitignore(source, target)

        assert result[0] == "old1"
        assert result[1] == "old2"
        assert "new1" in result[2:]
        assert "new2" in result[2:]

    def test_merge_gitignore_target_missing(self, tmp_path):
        """Test gitignore merge when target doesn't exist."""
        source = tmp_path / "source"
        target = tmp_path / "target"

        source.write_text("*.log\n*.tmp\n")

        result = merge_gitignore(source, target)

        assert result == ["*.log", "*.tmp"]


class TestMergeFilesHighLevel:
    """Test high-level merge_files() function."""

    def test_merge_files_json_auto(self, tmp_path):
        """Test auto-detect JSON merge."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text('{"new": "value"}')
        target.write_text('{"old": "value"}')

        merge_files(source, target)

        result = json.loads(target.read_text())
        assert result == {"old": "value", "new": "value"}

    def test_merge_files_yaml_auto(self, tmp_path):
        """Test auto-detect YAML merge."""
        source = tmp_path / "source.yaml"
        target = tmp_path / "target.yaml"

        source.write_text("new: value")
        target.write_text("old: value")

        merge_files(source, target)

        result = yaml.safe_load(target.read_text())
        assert result == {"old": "value", "new": "value"}

    def test_merge_files_toml_auto(self, tmp_path):
        """Test auto-detect TOML merge."""
        source = tmp_path / "source.toml"
        target = tmp_path / "target.toml"

        source.write_text("new = 'value'")
        target.write_text("old = 'value'")

        merge_files(source, target)

        import tomllib

        with open(target, "rb") as f:
            result = tomllib.load(f)

        assert result == {"old": "value", "new": "value"}

    def test_merge_files_gitignore_auto(self, tmp_path):
        """Test auto-detect gitignore merge."""
        source = tmp_path / "source"
        target = tmp_path / ".gitignore"

        source.write_text("*.new")
        target.write_text("*.old")

        merge_files(source, target)

        result = target.read_text().splitlines()
        assert "*.old" in result
        assert "*.new" in result

    def test_merge_files_dry_run(self, tmp_path):
        """Test dry-run returns content without writing."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text('{"new": "value"}')
        target.write_text('{"old": "value"}')

        content = merge_files(source, target, dry_run=True)

        # Target should not be modified
        assert json.loads(target.read_text()) == {"old": "value"}

        # Content should be merged
        result = json.loads(content)
        assert result == {"old": "value", "new": "value"}

    def test_merge_files_batch(self, tmp_path):
        """Test batch merge multiple sources."""
        base = tmp_path / "base.yaml"
        env = tmp_path / "env.yaml"
        local = tmp_path / "local.yaml"
        target = tmp_path / "merged.yaml"

        base.write_text("a: 1\nb: 2")
        env.write_text("b: 20\nc: 3")
        local.write_text("c: 30\nd: 4")

        merge_files([base, env, local], target)

        result = yaml.safe_load(target.read_text())
        assert result == {"a": 1, "b": 20, "c": 30, "d": 4}

    def test_merge_files_source_missing(self, tmp_path):
        """Test error when source file doesn't exist."""
        source = tmp_path / "missing.json"
        target = tmp_path / "target.json"

        with pytest.raises(FileNotFoundError):
            merge_files(source, target)

    def test_merge_files_invalid_strategy(self, tmp_path):
        """Test error for invalid merge strategy."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text("{}")
        target.write_text("{}")

        with pytest.raises(ValueError, match="Unknown strategy"):
            merge_files(source, target, strategy="invalid")  # type: ignore

    def test_merge_files_creates_parent_dirs(self, tmp_path):
        """Test merge creates parent directories if needed."""
        source = tmp_path / "source.json"
        target = tmp_path / "subdir" / "nested" / "target.json"

        source.write_text('{"key": "value"}')

        merge_files(source, target)

        assert target.exists()
        assert target.parent.exists()


class TestErrorHandling:
    """Test error handling for invalid data and I/O errors."""

    def test_invalid_json_in_source(self, tmp_path):
        """Test error for malformed JSON in source."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text("{invalid json}")
        target.write_text('{"key": "value"}')

        with pytest.raises(ValueError, match="Invalid JSON"):
            merge_files(source, target)

    def test_permission_error_on_source_read(self, tmp_path):
        """Test PermissionError when cannot read source file."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text('{"key": "value"}')
        target.write_text("{}")

        # Make source unreadable
        source.chmod(0o000)

        try:
            with pytest.raises(PermissionError, match="Cannot read source file"):
                merge_files(source, target)
        finally:
            # Restore permissions for cleanup
            source.chmod(0o644)

    def test_permission_error_on_target_write(self, tmp_path):
        """Test PermissionError when cannot write to target."""
        source = tmp_path / "source.json"
        target_dir = tmp_path / "readonly"
        target = target_dir / "target.json"

        source.write_text('{"key": "value"}')
        target_dir.mkdir()

        # Make directory read-only
        target_dir.chmod(0o555)

        try:
            with pytest.raises((PermissionError, OSError), match="Cannot write to|Cannot create"):
                merge_files(source, target)
        finally:
            # Restore permissions for cleanup
            target_dir.chmod(0o755)

    def test_invalid_json_in_target(self, tmp_path):
        """Test error for malformed JSON in target."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text('{"key": "value"}')
        target.write_text("{broken json")

        with pytest.raises(ValueError, match="Invalid JSON"):
            merge_files(source, target)

    def test_invalid_yaml_syntax(self, tmp_path):
        """Test error for invalid YAML syntax."""
        source = tmp_path / "source.yaml"
        target = tmp_path / "target.yaml"

        source.write_text("key: [unclosed")
        target.write_text("other: value")

        with pytest.raises(ValueError, match="Invalid YAML"):
            merge_files(source, target)

    def test_invalid_toml_syntax(self, tmp_path):
        """Test error for invalid TOML syntax."""
        source = tmp_path / "source.toml"
        target = tmp_path / "target.toml"

        source.write_text("[unclosed")
        target.write_text("key = 'value'")

        with pytest.raises(ValueError):
            merge_files(source, target)

    def test_deep_merge_on_unsupported_type(self, tmp_path):
        """Test error for deep merge on unsupported file type."""
        source = tmp_path / "source.txt"
        target = tmp_path / "target.txt"

        source.write_text("content")
        target.write_text("content")

        with pytest.raises(ValueError, match="Deep merge not supported"):
            merge_files(source, target, strategy="deep")


class TestMergeStrategies:
    """Test different merge strategies."""

    def test_strategy_deep_json(self, tmp_path):
        """Test explicit deep strategy on JSON."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text('{"a": {"b": 2}}')
        target.write_text('{"a": {"x": 1}}')

        merge_files(source, target, strategy="deep")

        result = json.loads(target.read_text())
        assert result == {"a": {"x": 1, "b": 2}}

    def test_strategy_append_gitignore(self, tmp_path):
        """Test explicit append strategy."""
        source = tmp_path / "source"
        target = tmp_path / "target"

        source.write_text("*.new")
        target.write_text("*.old")

        merge_files(source, target, strategy="append")

        lines = target.read_text().splitlines()
        assert "*.old" in lines
        assert "*.new" in lines

    def test_strategy_overwrite(self, tmp_path):
        """Test overwrite strategy (no merge)."""
        source = tmp_path / "source.txt"
        target = tmp_path / "target.txt"

        source.write_text("new content")
        target.write_text("old content")

        merge_files(source, target, strategy="overwrite")

        assert target.read_text() == "new content"

    def test_strategy_auto_selects_deep_for_json(self, tmp_path):
        """Test auto strategy selects deep for JSON."""
        source = tmp_path / "source.json"
        target = tmp_path / "target.json"

        source.write_text('{"new": 1}')
        target.write_text('{"old": 2}')

        merge_files(source, target, strategy="auto")

        result = json.loads(target.read_text())
        assert result == {"old": 2, "new": 1}

    def test_strategy_auto_selects_append_for_gitignore(self, tmp_path):
        """Test auto strategy selects append for .gitignore."""
        source = tmp_path / "add"
        target = tmp_path / ".gitignore"

        source.write_text("*.new")
        target.write_text("*.old")

        merge_files(source, target, strategy="auto")

        lines = target.read_text().splitlines()
        assert len([l for l in lines if l.strip()]) == 2
