# Project:   hyperi-pylib
# File:      tests/unit/test_version_check.py
# Purpose:   Unit tests for startup version check
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for the version_check module."""

import json
import os
import threading
from datetime import UTC

import pytest


class TestVersionCheckConfig:
    """Test VersionCheckConfig defaults and env overrides."""

    def test_default_config(self):
        from hyperi_pylib.version_check.checker import VersionCheckConfig

        config = VersionCheckConfig()
        assert config.api_url == "https://releases.hyperi.io/api/v1/check"
        assert config.timeout == 5.0
        assert not config.disabled
        assert config.product == ""

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("VERSION_CHECK_DISABLED", "true")
        from hyperi_pylib.version_check.checker import VersionCheckConfig

        config = VersionCheckConfig()
        assert config.disabled

    def test_custom_url_via_env(self, monkeypatch):
        monkeypatch.setenv("VERSION_CHECK_URL", "https://custom.example.com/check")
        from hyperi_pylib.version_check.checker import VersionCheckConfig

        config = VersionCheckConfig()
        assert config.api_url == "https://custom.example.com/check"


class TestVersionCheckResponse:
    """Test VersionCheckResponse dataclass."""

    def test_default_response(self):
        from hyperi_pylib.version_check.checker import VersionCheckResponse

        resp = VersionCheckResponse()
        assert resp.latest_version is None
        assert not resp.update_available
        assert resp.release_url is None
        assert resp.message is None

    def test_update_available(self):
        from hyperi_pylib.version_check.checker import VersionCheckResponse

        resp = VersionCheckResponse(
            latest_version="2.0.0",
            update_available=True,
            release_url="https://github.com/hyperi-io/test/releases/tag/v2.0.0",
        )
        assert resp.update_available
        assert resp.latest_version == "2.0.0"


class TestInstanceId:
    """Test persistent instance ID generation."""

    def test_instance_id_is_uuid(self):
        import uuid as uuid_mod

        from hyperi_pylib.version_check.checker import _get_or_create_instance_id

        instance_id = _get_or_create_instance_id()
        # Should be a valid UUID
        parsed = uuid_mod.UUID(instance_id)
        assert parsed.version == 4

    def test_instance_id_stable(self):
        from hyperi_pylib.version_check.checker import _get_or_create_instance_id

        id1 = _get_or_create_instance_id()
        id2 = _get_or_create_instance_id()
        assert id1 == id2


class TestCheckOnStartup:
    """Test the fire-and-forget check_on_startup function."""

    def test_disabled_returns_immediately(self):
        from hyperi_pylib.version_check import check_on_startup

        # Should not raise, not spawn a thread
        check_on_startup(
            product="test",
            version="1.0.0",
            config=__import__("hyperi_pylib.version_check.checker", fromlist=["VersionCheckConfig"]).VersionCheckConfig(
                disabled=True,
            ),
        )

    def test_empty_product_returns_immediately(self):
        from hyperi_pylib.version_check import check_on_startup

        # Should not raise
        check_on_startup(product="", version="1.0.0")

    def test_empty_version_returns_immediately(self):
        from hyperi_pylib.version_check import check_on_startup

        check_on_startup(product="test", version="")

    def test_spawns_daemon_thread(self, httpx_mock):
        """Verify check_on_startup spawns a thread and doesn't block."""
        from hyperi_pylib.version_check.checker import VersionCheckConfig, check_on_startup

        httpx_mock.add_response(
            method="POST",
            url="https://test.example.com/api/v1/check",
            json={
                "latest_version": "2.0.0",
                "update_available": True,
                "release_url": None,
                "message": None,
            },
        )

        config = VersionCheckConfig(
            api_url="https://test.example.com/api/v1/check",
        )

        thread = check_on_startup(
            product="test-app",
            version="1.0.0",
            config=config,
        )

        # The function returned a live daemon thread — confirm + join
        # deterministically rather than racing on time.sleep(). Without
        # the join, a busy test runner can finish the test before the
        # daemon's HTTP request completes, leaving pytest-httpx's
        # registered mock response unconsumed at teardown (which
        # pytest-httpx then reports as an error).
        assert thread is not None
        assert thread.daemon is True
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "daemon thread did not finish in 5s"

    def test_handles_http_error_gracefully(self, httpx_mock):
        """Verify HTTP errors are swallowed gracefully."""
        from hyperi_pylib.version_check.checker import VersionCheckConfig, check_on_startup

        httpx_mock.add_response(
            method="POST",
            url="https://test.example.com/api/v1/check",
            status_code=500,
        )

        config = VersionCheckConfig(
            api_url="https://test.example.com/api/v1/check",
        )

        # Should not raise
        thread = check_on_startup(product="test-app", version="1.0.0", config=config)
        assert thread is not None
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "daemon thread did not finish in 5s"

    def test_handles_connection_error_gracefully(self, httpx_mock):
        """Verify connection errors are swallowed gracefully."""
        import httpx

        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://unreachable.example.com/api/v1/check",
        )

        from hyperi_pylib.version_check.checker import VersionCheckConfig, check_on_startup

        config = VersionCheckConfig(
            api_url="https://unreachable.example.com/api/v1/check",
        )

        # Should not raise
        thread = check_on_startup(product="test-app", version="1.0.0", config=config)
        assert thread is not None
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "daemon thread did not finish in 5s"


class TestLogResponse:
    """Test the log output for different response types."""

    def test_log_update_available_with_age(self, caplog):
        import logging

        from hyperi_pylib.version_check.checker import VersionCheckConfig, VersionCheckResponse, _log_response

        config = VersionCheckConfig(product="dfe-loader", current_version="1.8.0")
        resp = VersionCheckResponse(
            latest_version="1.9.0",
            update_available=True,
            release_url="https://github.com/hyperi-io/dfe-loader/releases/tag/v1.9.0",
            published_at="2026-01-15T10:00:00Z",
        )

        with caplog.at_level(logging.INFO, logger="hyperi.version_check"):
            _log_response(config, resp)

        assert "new version available" in caplog.text
        assert "1.9.0" in caplog.text
        assert "1.8.0" in caplog.text
        assert "released" in caplog.text

    def test_log_update_available_without_published_at(self, caplog):
        import logging

        from hyperi_pylib.version_check.checker import VersionCheckConfig, VersionCheckResponse, _log_response

        config = VersionCheckConfig(product="dfe-loader", current_version="1.8.0")
        resp = VersionCheckResponse(
            latest_version="1.9.0",
            update_available=True,
        )

        with caplog.at_level(logging.INFO, logger="hyperi.version_check"):
            _log_response(config, resp)

        assert "new version available" in caplog.text
        assert "1.9.0" in caplog.text

    def test_log_up_to_date(self, caplog):
        import logging

        from hyperi_pylib.version_check.checker import VersionCheckConfig, VersionCheckResponse, _log_response

        config = VersionCheckConfig(product="dfe-loader", current_version="1.8.0")
        resp = VersionCheckResponse(
            latest_version="1.8.0",
            update_available=False,
        )

        with caplog.at_level(logging.DEBUG, logger="hyperi.version_check"):
            _log_response(config, resp)

        assert "latest version" in caplog.text


class TestFormatAge:
    """Test the age formatting function."""

    def test_format_age_today(self):
        from datetime import datetime, timezone

        from hyperi_pylib.version_check.checker import _format_age

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(now) == "released today"

    def test_format_age_days(self):
        from datetime import datetime, timedelta, timezone

        from hyperi_pylib.version_check.checker import _format_age

        ten_days_ago = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(ten_days_ago) == "released 10 days ago"

    def test_format_age_one_day(self):
        from datetime import datetime, timedelta, timezone

        from hyperi_pylib.version_check.checker import _format_age

        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(yesterday) == "released 1 day ago"

    def test_format_age_months(self):
        from datetime import datetime, timedelta, timezone

        from hyperi_pylib.version_check.checker import _format_age

        three_months_ago = (datetime.now(UTC) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(three_months_ago) == "released 3 months ago"

    def test_format_age_invalid(self):
        from hyperi_pylib.version_check.checker import _format_age

        assert _format_age("not-a-date") == ""
