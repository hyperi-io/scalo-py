"""Parity tests for config cascade alignment with scalo-rs.

These tests verify that scalo's config cascade behaviour matches
scalo-rs's implementation per the unified spec.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestAppEnvDetection:
    """Test get_app_env() matches scalo-rs's detection chain."""

    def test_app_env_from_app_env_var(self, monkeypatch):
        """APP_ENV takes highest priority."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_from_environment_var(self, monkeypatch):
        """ENVIRONMENT is second priority."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "staging"

    def test_app_env_from_env_var(self, monkeypatch):
        """ENV is third priority."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("ENV", "testing")

        from scalo.config.config import get_app_env

        assert get_app_env() == "testing"

    def test_app_env_default_development(self, monkeypatch):
        """Default falls back to 'development'."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "development"

    def test_app_env_priority_order(self, monkeypatch):
        """APP_ENV wins over ENVIRONMENT and ENV."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("ENV", "testing")

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_strips_leading_whitespace(self, monkeypatch):
        """A padded value is trimmed, matching scalo-rs."""
        monkeypatch.setenv("APP_ENV", " production")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_strips_trailing_whitespace(self, monkeypatch):
        """A trailing newline is trimmed, matching scalo-rs."""
        monkeypatch.setenv("APP_ENV", "production\n")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_blank_falls_through(self, monkeypatch):
        """A blank APP_ENV is treated as unset, falling through to ENVIRONMENT."""
        monkeypatch.setenv("APP_ENV", "")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_whitespace_only_falls_through(self, monkeypatch):
        """A whitespace-only APP_ENV is treated as unset."""
        monkeypatch.setenv("APP_ENV", "   ")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_all_blank_defaults_to_development(self, monkeypatch):
        """All three variables blank still defaults to 'development'."""
        monkeypatch.setenv("APP_ENV", "")
        monkeypatch.setenv("ENVIRONMENT", "  ")
        monkeypatch.setenv("ENV", "")

        from scalo.config.config import get_app_env

        assert get_app_env() == "development"


class TestAppNameDetection:
    """Test get_app_name() priority matches scalo-rs."""

    def test_app_name_from_env(self, monkeypatch):
        """APP_NAME (bare, or app-prefixed) takes highest priority."""
        monkeypatch.setenv("APP_NAME", "myapp")

        from scalo.config.config import get_app_name

        assert get_app_name() == "myapp"


class TestLogFormatDefault:
    """Test log_format default matches scalo-rs's 'auto'."""

    def test_log_format_default_is_auto(self, monkeypatch):
        """Default log_format should be 'auto' (matches scalo-rs)."""
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        from scalo.config.config import get_logging_config

        config = get_logging_config()
        assert config["format"] == "auto"

    def test_log_format_env_override(self, monkeypatch):
        """LOG_FORMAT env var overrides default."""
        monkeypatch.setenv("LOG_FORMAT", "json")

        from scalo.config.config import get_logging_config

        config = get_logging_config()
        assert config["format"] == "json"


class TestLogLevelDefault:
    """Test log_level default matches scalo-rs's 'info'."""

    def test_log_level_default_is_info(self, monkeypatch):
        """Default log_level should be 'INFO' (matches scalo-rs 'info')."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        from scalo.config.config import get_logging_config

        config = get_logging_config()
        assert config["level"].lower() == "info"


class TestDotenvCascadeDefault:
    """Test .env cascade is opt-in (disabled by default)."""

    def test_dotenv_cascade_disabled_by_default(self, monkeypatch):
        """Home .env loading must be opt-in (matches scalo-rs load_home_dotenv=false)."""
        monkeypatch.delenv("DOTENV_CASCADE", raising=False)

        from scalo.config.config import _DOTENV_CASCADE_ENABLED

        assert not _DOTENV_CASCADE_ENABLED


class TestMultiLayerFileDiscovery:
    """Test that config file discovery searches multiple locations."""

    def test_find_config_files_searches_cwd(self, tmp_path, monkeypatch):
        """Should find config files in current directory."""
        monkeypatch.chdir(tmp_path)
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert str(defaults_file.resolve()) in found

    def test_find_config_files_searches_config_subdir(self, tmp_path, monkeypatch):
        """Should find config files in ./config/ subdirectory."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        settings_file = config_dir / "settings.yaml"
        settings_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("settings")
        assert str(settings_file.resolve()) in found

    def test_find_config_files_checks_both_extensions(self, tmp_path, monkeypatch):
        """Should check both .yaml and .yml extensions."""
        monkeypatch.chdir(tmp_path)
        yml_file = tmp_path / "defaults.yml"
        yml_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert str(yml_file.resolve()) in found

    def test_find_config_files_no_duplicates(self, tmp_path, monkeypatch):
        """Should not include duplicate paths."""
        monkeypatch.chdir(tmp_path)
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert len(found) == len(set(found))


class TestGetAppEnvExport:
    """Test that get_app_env is properly exported."""

    def test_get_app_env_importable(self):
        """get_app_env should be importable from scalo.config."""
        from scalo.config import get_app_env

        assert callable(get_app_env)
