#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/health/manager.py
#  Purpose:   Health state manager for liveness, readiness, and startup probes
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Health state manager for Kubernetes-style probes.

Pure Python, no external dependencies. Tracks liveness, readiness, and
startup state with optional registered checks. Response format matches
rustlib's built-in health endpoints.

Usage::

    from hyperi_pylib.health import HealthManager

    mgr = HealthManager()
    mgr.register_ready_check("database", lambda: db.is_connected())
    mgr.set_started()
    mgr.set_ready()

    # Probe responses for K8s
    mgr.liveness_response()   # {"status": "alive", "timestamp": "...", "checks": {}}
    mgr.readiness_response()  # {"status": "ready", "timestamp": "...", "checks": {"database": true}}
    mgr.startup_response()    # {"status": "started", "timestamp": "...", "checks": {}}
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable


class HealthStatus(StrEnum):
    """Health probe status values matching rustlib conventions."""

    ALIVE = "alive"
    READY = "ready"
    NOT_READY = "not_ready"
    STARTING = "starting"


class HealthManager:
    """Track application health state for K8s probes.

    Manages three independent probe states:

    - **Liveness:** Is the process alive? Registered checks must all pass.
      No registered checks means alive (default).
    - **Readiness:** Can the service handle traffic? Requires explicit
      ``set_ready()`` AND all registered readiness checks passing.
    - **Startup:** Has initialisation completed? Requires explicit
      ``set_started()``.

    Checks are synchronous callables returning bool. A check that raises
    an exception is treated as failing (returns False in the response).
    """

    def __init__(self) -> None:
        self._ready: bool = False
        self._started: bool = False
        self._live_checks: list[tuple[str, Callable[[], bool]]] = []
        self._ready_checks: list[tuple[str, Callable[[], bool]]] = []

    def register_live_check(self, name: str, check: Callable[[], bool]) -> None:
        """Register a named liveness check.

        Args:
            name: Human-readable check name (appears in response).
            check: Callable returning True if healthy.
        """
        self._live_checks.append((name, check))

    def register_ready_check(self, name: str, check: Callable[[], bool]) -> None:
        """Register a named readiness check.

        Args:
            name: Human-readable check name (appears in response).
            check: Callable returning True if ready.
        """
        self._ready_checks.append((name, check))

    def set_ready(self, ready: bool = True) -> None:
        """Set the readiness flag.

        Readiness requires both this flag AND all registered readiness
        checks passing.
        """
        self._ready = ready

    def set_started(self, started: bool = True) -> None:
        """Set the startup-complete flag."""
        self._started = started

    def is_live(self) -> bool:
        """True if all registered liveness checks pass (or none registered)."""
        return all(self._run_check(check) for _, check in self._live_checks) if self._live_checks else True

    def is_ready(self) -> bool:
        """True if the ready flag is set AND all readiness checks pass."""
        if not self._ready:
            return False
        if self._ready_checks:
            return all(self._run_check(check) for _, check in self._ready_checks)
        return True

    def is_started(self) -> bool:
        """True if startup has completed."""
        return self._started

    def liveness_response(self) -> dict:
        """Build liveness probe response.

        Returns:
            Dict with status, RFC 3339 timestamp, and per-check details.
        """
        checks = {name: self._run_check(check) for name, check in self._live_checks}
        alive = all(checks.values()) if checks else True
        return {
            "status": "alive" if alive else "not_alive",
            "timestamp": self._now_rfc3339(),
            "checks": checks,
        }

    def readiness_response(self) -> dict:
        """Build readiness probe response.

        Returns:
            Dict with status, RFC 3339 timestamp, and per-check details.
        """
        checks = {name: self._run_check(check) for name, check in self._ready_checks}
        ready = self._ready and (all(checks.values()) if checks else True)
        return {
            "status": "ready" if ready else "not_ready",
            "timestamp": self._now_rfc3339(),
            "checks": checks,
        }

    def startup_response(self) -> dict:
        """Build startup probe response.

        Returns:
            Dict with status, RFC 3339 timestamp, and empty checks.
        """
        return {
            "status": "started" if self._started else "starting",
            "timestamp": self._now_rfc3339(),
            "checks": {},
        }

    @staticmethod
    def _run_check(check: Callable[[], bool]) -> bool:
        """Execute a health check, treating exceptions as failures."""
        try:
            return bool(check())
        except Exception:
            return False

    @staticmethod
    def _now_rfc3339() -> str:
        """Current time as RFC 3339 string with timezone offset."""
        return datetime.now(UTC).isoformat()
