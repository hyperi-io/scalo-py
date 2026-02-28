"""Parity tests for config cascade alignment with hyperi-rustlib.

These tests verify that hyperi-pylib's config cascade behaviour matches
hyperi-rustlib's implementation per the unified spec.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestAppEnvDetection:
    """Test get_app_env() matches rustlib's detection chain."""

    def test_app_env_from_app_env_var(self, monkeypatch):
        """APP_ENV takes highest priority."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from hyperi_pylib.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_from_environment_var(self, monkeypatch):
        """ENVIRONMENT is second priority."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("ENV", raising=False)

        from hyperi_pylib.config.config import get_app_env

        assert get_app_env() == "staging"

    def test_app_env_from_env_var(self, monkeypatch):
        """ENV is third priority."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("ENV", "testing")

        from hyperi_pylib.config.config import get_app_env

        assert get_app_env() == "testing"

    def test_app_env_default_development(self, monkeypatch):
        """Default falls back to 'development'."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from hyperi_pylib.config.config import get_app_env

        assert get_app_env() == "development"

    def test_app_env_priority_order(self, monkeypatch):
        """APP_ENV wins over ENVIRONMENT and ENV."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("ENV", "testing")

        from hyperi_pylib.config.config import get_app_env

        assert get_app_env() == "production"


class TestAppNameDetection:
    """Test get_app_name() priority matches rustlib."""

    def test_app_name_from_env(self, monkeypatch):
        """APP_NAME takes highest priority."""
        monkeypatch.setenv("APP_NAME", "myapp")
        monkeypatch.delenv("HYPERI_LIB_APP_NAME", raising=False)

        from hyperi_pylib.config.config import get_app_name

        assert get_app_name() == "myapp"

    def test_app_name_from_hyperi_env(self, monkeypatch):
        """HYPERI_LIB_APP_NAME is second priority."""
        monkeypatch.delenv("APP_NAME", raising=False)
        monkeypatch.setenv("HYPERI_LIB_APP_NAME", "hyperi-app")

        from hyperi_pylib.config.config import get_app_name

        assert get_app_name() == "hyperi-app"


class TestLogFormatDefault:
    """Test log_format default matches rustlib's 'auto'."""

    def test_log_format_default_is_auto(self, monkeypatch):
        """Default log_format should be 'auto' (matches rustlib)."""
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        from hyperi_pylib.config.config import get_logging_config

        config = get_logging_config()
        assert config["format"] == "auto"

    def test_log_format_env_override(self, monkeypatch):
        """LOG_FORMAT env var overrides default."""
        monkeypatch.setenv("LOG_FORMAT", "json")

        from hyperi_pylib.config.config import get_logging_config

        config = get_logging_config()
        assert config["format"] == "json"


class TestLogLevelDefault:
    """Test log_level default matches rustlib's 'info'."""

    def test_log_level_default_is_info(self, monkeypatch):
        """Default log_level should be 'INFO' (matches rustlib 'info')."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        from hyperi_pylib.config.config import get_logging_config

        config = get_logging_config()
        assert config["level"].lower() == "info"


class TestDotenvCascadeDefault:
    """Test .env cascade is opt-in (disabled by default)."""

    def test_dotenv_cascade_disabled_by_default(self, monkeypatch):
        """Home .env loading must be opt-in (matches rustlib load_home_dotenv=false)."""
        monkeypatch.delenv("HYPERI_DOTENV_CASCADE", raising=False)

        from hyperi_pylib.config.config import _DOTENV_CASCADE_ENABLED

        assert not _DOTENV_CASCADE_ENABLED


class TestMultiLayerFileDiscovery:
    """Test that config file discovery searches multiple locations."""

    def test_find_config_files_searches_cwd(self, tmp_path, monkeypatch):
        """Should find config files in current directory."""
        monkeypatch.chdir(tmp_path)
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text("key: value\n")

        from hyperi_pylib.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert str(defaults_file.resolve()) in found

    def test_find_config_files_searches_config_subdir(self, tmp_path, monkeypatch):
        """Should find config files in ./config/ subdirectory."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        settings_file = config_dir / "settings.yaml"
        settings_file.write_text("key: value\n")

        from hyperi_pylib.config.config import _find_config_files

        found = _find_config_files("settings")
        assert str(settings_file.resolve()) in found

    def test_find_config_files_checks_both_extensions(self, tmp_path, monkeypatch):
        """Should check both .yaml and .yml extensions."""
        monkeypatch.chdir(tmp_path)
        yml_file = tmp_path / "defaults.yml"
        yml_file.write_text("key: value\n")

        from hyperi_pylib.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert str(yml_file.resolve()) in found

    def test_find_config_files_no_duplicates(self, tmp_path, monkeypatch):
        """Should not include duplicate paths."""
        monkeypatch.chdir(tmp_path)
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text("key: value\n")

        from hyperi_pylib.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert len(found) == len(set(found))


class TestGetAppEnvExport:
    """Test that get_app_env is properly exported."""

    def test_get_app_env_importable(self):
        """get_app_env should be importable from hyperi_pylib.config."""
        from hyperi_pylib.config import get_app_env

        assert callable(get_app_env)
