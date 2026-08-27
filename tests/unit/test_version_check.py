# Project:   scalo
# File:      tests/unit/test_version_check.py
# Purpose:   Unit tests for startup version check
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for the version_check module."""

import json
import os
import threading
from datetime import UTC

import pytest


class TestVersionCheckConfig:
    """Test VersionCheckConfig defaults (opt-in, no default endpoint)."""

    def test_default_config_is_opt_in(self):
        from scalo.version_check.checker import VersionCheckConfig

        config = VersionCheckConfig()
        # Opt-in: disabled by default, no baked-in endpoint.
        assert config.enabled is False
        assert config.api_url is None
        assert config.timeout == 5.0
        assert config.product == ""

    def test_explicit_config(self):
        from scalo.version_check.checker import VersionCheckConfig

        config = VersionCheckConfig(enabled=True, api_url="https://x.example.com/check", timeout=2.0)
        assert config.enabled is True
        assert config.api_url == "https://x.example.com/check"
        assert config.timeout == 2.0

    def test_config_from_cascade(self):
        from scalo.config import settings
        from scalo.version_check.checker import VersionCheckConfig

        settings.set("version_check.enabled", True)
        settings.set("version_check.api_url", "https://cascade.example.com/check")
        try:
            config = VersionCheckConfig()
            assert config.enabled is True
            assert config.api_url == "https://cascade.example.com/check"
        finally:
            settings.set("version_check.enabled", False)
            settings.set("version_check.api_url", None)


class TestVersionCheckResponse:
    """Test VersionCheckResponse dataclass."""

    def test_default_response(self):
        from scalo.version_check.checker import VersionCheckResponse

        resp = VersionCheckResponse()
        assert resp.latest_version is None
        assert not resp.update_available
        assert resp.release_url is None
        assert resp.message is None

    def test_update_available(self):
        from scalo.version_check.checker import VersionCheckResponse

        resp = VersionCheckResponse(
            latest_version="2.0.0",
            update_available=True,
            release_url="https://github.com/hyperi-io/test/releases/tag/v2.0.0",
        )
        assert resp.update_available
        assert resp.latest_version == "2.0.0"


class TestPayloadIsAnonymous:
    """The wire payload carries no identifier beyond product/version/platform."""

    def test_payload_has_no_instance_id(self):
        import http.server
        import json
        import threading

        from scalo.version_check import check_on_startup
        from scalo.version_check.checker import VersionCheckConfig

        received: list[dict] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append(json.loads(body))
                resp = b'{"update_available": false}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, *args):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            cfg = VersionCheckConfig(
                product="",
                current_version="",
                api_url=f"http://127.0.0.1:{srv.server_address[1]}/",
                enabled=True,
                deployment="secret-site-name",
            )
            thread = check_on_startup(product="test", version="1.0.0", config=cfg)
            assert thread is not None
            thread.join(timeout=10)
        finally:
            srv.shutdown()

        assert received == [
            {
                "product": "test",
                "current_version": "1.0.0",
                "os": received[0]["os"],
                "arch": received[0]["arch"],
            }
        ]


class TestCheckOnStartup:
    """Test the fire-and-forget check_on_startup function."""

    def test_not_enabled_returns_none(self):
        from scalo.version_check import check_on_startup

        # Opt-in: the default config is not enabled -> no thread, returns None.
        result = check_on_startup(product="test", version="1.0.0")
        assert result is None

    def test_empty_product_returns_immediately(self):
        from scalo.version_check import check_on_startup

        # Should not raise
        check_on_startup(product="", version="1.0.0")

    def test_empty_version_returns_immediately(self):
        from scalo.version_check import check_on_startup

        check_on_startup(product="test", version="")

    def test_spawns_daemon_thread(self, httpx_mock):
        """Verify check_on_startup spawns a thread and doesn't block."""
        from scalo.version_check.checker import VersionCheckConfig, check_on_startup

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
            enabled=True,
            api_url="https://test.example.com/api/v1/check",
        )

        thread = check_on_startup(
            product="test-app",
            version="1.0.0",
            config=config,
        )

        # The function returned a live daemon thread -- confirm + join
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
        from scalo.version_check.checker import VersionCheckConfig, check_on_startup

        httpx_mock.add_response(
            method="POST",
            url="https://test.example.com/api/v1/check",
            status_code=500,
        )

        config = VersionCheckConfig(
            enabled=True,
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

        from scalo.version_check.checker import VersionCheckConfig, check_on_startup

        config = VersionCheckConfig(
            enabled=True,
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

        from scalo.version_check.checker import VersionCheckConfig, VersionCheckResponse, _log_response

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

        from scalo.version_check.checker import VersionCheckConfig, VersionCheckResponse, _log_response

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

        from scalo.version_check.checker import VersionCheckConfig, VersionCheckResponse, _log_response

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

        from scalo.version_check.checker import _format_age

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(now) == "released today"

    def test_format_age_days(self):
        from datetime import datetime, timedelta, timezone

        from scalo.version_check.checker import _format_age

        ten_days_ago = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(ten_days_ago) == "released 10 days ago"

    def test_format_age_one_day(self):
        from datetime import datetime, timedelta, timezone

        from scalo.version_check.checker import _format_age

        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(yesterday) == "released 1 day ago"

    def test_format_age_months(self):
        from datetime import datetime, timedelta, timezone

        from scalo.version_check.checker import _format_age

        three_months_ago = (datetime.now(UTC) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert _format_age(three_months_ago) == "released 3 months ago"

    def test_format_age_invalid(self):
        from scalo.version_check.checker import _format_age

        assert _format_age("not-a-date") == ""
