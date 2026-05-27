#  Project:   hyperi-pylib
#  File:      tests/unit/test_health_manager.py
#  Purpose:   Unit tests for HealthManager
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for the HealthManager -- pure Python health state tracking.

Tests liveness, readiness, and startup probe logic with registered checks,
timestamp formatting, and response structure matching rustlib's health probes.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from hyperi_pylib.health.manager import HealthManager, HealthStatus


class TestHealthStatus:
    """HealthStatus enum behaves as string (StrEnum)."""

    def test_alive_value(self):
        assert HealthStatus.ALIVE == "alive"

    def test_ready_value(self):
        assert HealthStatus.READY == "ready"

    def test_not_ready_value(self):
        assert HealthStatus.NOT_READY == "not_ready"

    def test_starting_value(self):
        assert HealthStatus.STARTING == "starting"

    def test_str_usage(self):
        assert f"status={HealthStatus.ALIVE}" == "status=alive"


class TestHealthManagerDefaults:
    """Fresh HealthManager with no checks registered."""

    def test_is_live_default(self):
        """No live checks registered means the process is alive."""
        mgr = HealthManager()
        assert mgr.is_live() is True

    def test_is_ready_default_false(self):
        """Ready defaults to False until explicitly set."""
        mgr = HealthManager()
        assert mgr.is_ready() is False

    def test_is_started_default_false(self):
        """Started defaults to False until explicitly set."""
        mgr = HealthManager()
        assert mgr.is_started() is False


class TestHealthManagerSetters:
    """set_ready and set_started toggle state."""

    def test_set_ready(self):
        mgr = HealthManager()
        mgr.set_ready()
        assert mgr.is_ready() is True

    def test_set_ready_false(self):
        mgr = HealthManager()
        mgr.set_ready()
        mgr.set_ready(False)
        assert mgr.is_ready() is False

    def test_set_started(self):
        mgr = HealthManager()
        mgr.set_started()
        assert mgr.is_started() is True

    def test_set_started_false(self):
        mgr = HealthManager()
        mgr.set_started()
        mgr.set_started(False)
        assert mgr.is_started() is False


class TestLivenessChecks:
    """Registered liveness checks gate is_live()."""

    def test_single_passing_check(self):
        mgr = HealthManager()
        mgr.register_live_check("always_ok", lambda: True)
        assert mgr.is_live() is True

    def test_single_failing_check(self):
        mgr = HealthManager()
        mgr.register_live_check("always_fail", lambda: False)
        assert mgr.is_live() is False

    def test_mixed_checks_fails_on_any(self):
        mgr = HealthManager()
        mgr.register_live_check("ok", lambda: True)
        mgr.register_live_check("bad", lambda: False)
        assert mgr.is_live() is False

    def test_all_checks_pass(self):
        mgr = HealthManager()
        mgr.register_live_check("check_a", lambda: True)
        mgr.register_live_check("check_b", lambda: True)
        assert mgr.is_live() is True

    def test_exception_in_check_treated_as_failure(self):
        """A check that raises is treated as unhealthy, not propagated."""
        mgr = HealthManager()

        def bad_check():
            raise RuntimeError("boom")

        mgr.register_live_check("exploding", bad_check)
        assert mgr.is_live() is False


class TestReadinessChecks:
    """Registered readiness checks AND _ready flag must all be True."""

    def test_ready_flag_false_ignores_checks(self):
        """Even if all checks pass, ready flag must be set."""
        mgr = HealthManager()
        mgr.register_ready_check("ok", lambda: True)
        assert mgr.is_ready() is False

    def test_ready_flag_true_no_checks(self):
        mgr = HealthManager()
        mgr.set_ready()
        assert mgr.is_ready() is True

    def test_ready_flag_true_passing_checks(self):
        mgr = HealthManager()
        mgr.register_ready_check("db", lambda: True)
        mgr.set_ready()
        assert mgr.is_ready() is True

    def test_ready_flag_true_failing_check(self):
        mgr = HealthManager()
        mgr.register_ready_check("db", lambda: False)
        mgr.set_ready()
        assert mgr.is_ready() is False

    def test_exception_in_ready_check_treated_as_failure(self):
        mgr = HealthManager()
        mgr.set_ready()
        mgr.register_ready_check("exploding", lambda: (_ for _ in ()).throw(ValueError("oops")))
        assert mgr.is_ready() is False


class TestLivenessResponse:
    """liveness_response() returns structured dict matching rustlib format."""

    def test_response_structure(self):
        mgr = HealthManager()
        resp = mgr.liveness_response()
        assert "status" in resp
        assert "timestamp" in resp
        assert "checks" in resp

    def test_alive_status(self):
        mgr = HealthManager()
        resp = mgr.liveness_response()
        assert resp["status"] == "alive"

    def test_dead_status(self):
        mgr = HealthManager()
        mgr.register_live_check("bad", lambda: False)
        resp = mgr.liveness_response()
        assert resp["status"] == "not_alive"

    def test_checks_detail(self):
        mgr = HealthManager()
        mgr.register_live_check("process", lambda: True)
        mgr.register_live_check("watchdog", lambda: False)
        resp = mgr.liveness_response()
        assert resp["checks"]["process"] is True
        assert resp["checks"]["watchdog"] is False

    def test_timestamp_rfc3339(self):
        mgr = HealthManager()
        resp = mgr.liveness_response()
        ts = resp["timestamp"]
        # Must be parseable and have timezone info
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


class TestReadinessResponse:
    def test_not_ready_status(self):
        mgr = HealthManager()
        resp = mgr.readiness_response()
        assert resp["status"] == "not_ready"

    def test_ready_status(self):
        mgr = HealthManager()
        mgr.set_ready()
        resp = mgr.readiness_response()
        assert resp["status"] == "ready"

    def test_ready_with_failing_check(self):
        mgr = HealthManager()
        mgr.set_ready()
        mgr.register_ready_check("db", lambda: False)
        resp = mgr.readiness_response()
        assert resp["status"] == "not_ready"
        assert resp["checks"]["db"] is False

    def test_ready_response_has_timestamp(self):
        mgr = HealthManager()
        resp = mgr.readiness_response()
        assert "timestamp" in resp
        parsed = datetime.fromisoformat(resp["timestamp"])
        assert parsed.tzinfo is not None


class TestStartupResponse:
    def test_not_started_status(self):
        mgr = HealthManager()
        resp = mgr.startup_response()
        assert resp["status"] == "starting"

    def test_started_status(self):
        mgr = HealthManager()
        mgr.set_started()
        resp = mgr.startup_response()
        assert resp["status"] == "started"

    def test_startup_response_has_timestamp(self):
        mgr = HealthManager()
        resp = mgr.startup_response()
        assert "timestamp" in resp
        parsed = datetime.fromisoformat(resp["timestamp"])
        assert parsed.tzinfo is not None

    def test_startup_response_has_checks(self):
        mgr = HealthManager()
        resp = mgr.startup_response()
        assert "checks" in resp
        assert isinstance(resp["checks"], dict)
