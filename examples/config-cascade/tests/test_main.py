# Project:   hyperi-pylib
# File:      examples/config-cascade/tests/test_main.py
# Purpose:   Tests for config-cascade example
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for config-cascade example."""

import os

import pytest
from main import (
    demonstrate_config_files,
    demonstrate_env_override,
    get_all_config,
    main,
    show_api_config,
    show_cache_config,
    show_database_config,
)


class TestDatabaseConfig:
    """Tests for database configuration."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        config = show_database_config()
        assert isinstance(config, dict)

    def test_has_required_keys(self) -> None:
        """Should have all required keys."""
        config = show_database_config()
        assert "host" in config
        assert "port" in config
        assert "name" in config
        assert "pool_size" in config

    def test_port_is_integer(self) -> None:
        """Port should be an integer."""
        config = show_database_config()
        assert isinstance(config["port"], int)


class TestApiConfig:
    """Tests for API configuration."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        config = show_api_config()
        assert isinstance(config, dict)

    def test_has_required_keys(self) -> None:
        """Should have all required keys."""
        config = show_api_config()
        assert "host" in config
        assert "port" in config
        assert "timeout" in config


class TestCacheConfig:
    """Tests for cache configuration."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        config = show_cache_config()
        assert isinstance(config, dict)

    def test_has_required_keys(self) -> None:
        """Should have all required keys."""
        config = show_cache_config()
        assert "enabled" in config
        assert "ttl_seconds" in config
        assert "backend" in config


class TestGetAllConfig:
    """Tests for get_all_config function."""

    def test_returns_all_sections(self) -> None:
        """Should return all configuration sections."""
        config = get_all_config()
        assert "database" in config
        assert "api" in config
        assert "cache" in config


class TestDemonstrations:
    """Tests for demonstration functions."""

    def test_demonstrate_config_files_runs(self, capsys: pytest.CaptureFixture) -> None:
        """Config files demonstration should run without error."""
        demonstrate_config_files()
        captured = capsys.readouterr()
        assert "Configuration Files" in captured.out

    def test_demonstrate_env_override_runs(self, capsys: pytest.CaptureFixture) -> None:
        """Env override demonstration should run without error."""
        demonstrate_env_override()
        captured = capsys.readouterr()
        assert "Environment Variable Override" in captured.out


class TestMain:
    """Tests for main function."""

    def test_main_runs_without_error(self, capsys: pytest.CaptureFixture) -> None:
        """Main function should run and produce output."""
        main()
        captured = capsys.readouterr()
        assert "Configuration Cascade Demo" in captured.out
        assert "Summary" in captured.out
