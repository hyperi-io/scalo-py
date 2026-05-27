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

Sync checks run via ``run_blocking`` with a per-check timeout to avoid
stalling the event loop when called from async probe endpoints.

Usage::

    from hyperi_pylib.health import HealthManager

    mgr = HealthManager()
    mgr.register_ready_check("database", db.is_connected)        # sync
    mgr.register_ready_check("kafka", kafka.is_ready_async)      # async
    mgr.set_started()
    mgr.set_ready()

    # Async probe responses (use these from FastAPI endpoints)
    await mgr.liveness_response_async()
    await mgr.readiness_response_async()
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from datetime import UTC, datetime
from enum import StrEnum
from typing import Awaitable, Callable

# Per-check soft cap. Kubelet timeoutSeconds typically 3s; we default
# the per-check budget to 2s so that even the slowest registered check
# leaves headroom for HTTP serialisation + network roundtrip.
DEFAULT_CHECK_TIMEOUT = 2.0

CheckResult = bool
SyncCheck = Callable[[], CheckResult]
AsyncCheck = Callable[[], Awaitable[CheckResult]]
AnyCheck = SyncCheck | AsyncCheck


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

    Checks may be sync (``Callable[[], bool]``) or async
    (``Callable[[], Awaitable[bool]]``). A check that raises, times
    out, or returns falsy is treated as failing.
    """

    def __init__(self, default_check_timeout: float = DEFAULT_CHECK_TIMEOUT) -> None:
        self._default_timeout = default_check_timeout
        self._ready: bool = False
        self._started: bool = False
        self._live_checks: list[tuple[str, AnyCheck, float]] = []
        self._ready_checks: list[tuple[str, AnyCheck, float]] = []
        self._lock = threading.Lock()

    def register_live_check(
        self,
        name: str,
        check: AnyCheck,
        per_check_timeout: float | None = None,
    ) -> None:
        """Register a named liveness check (sync or async)."""
        with self._lock:
            self._live_checks.append((name, check, per_check_timeout or self._default_timeout))

    def register_ready_check(
        self,
        name: str,
        check: AnyCheck,
        per_check_timeout: float | None = None,
    ) -> None:
        """Register a named readiness check (sync or async)."""
        with self._lock:
            self._ready_checks.append((name, check, per_check_timeout or self._default_timeout))

    def set_ready(self, ready: bool = True) -> None:
        with self._lock:
            self._ready = ready

    def set_started(self, started: bool = True) -> None:
        with self._lock:
            self._started = started

    def is_started(self) -> bool:
        with self._lock:
            return self._started

    # --- sync probe responses (legacy / non-async callers) ---

    def is_live(self) -> bool:
        """True if all registered liveness checks pass. Sync-only callers.

        Async-context callers should use :meth:`liveness_response_async`
        which runs sync checks via ``run_blocking`` and applies timeouts.
        """
        with self._lock:
            checks = list(self._live_checks)
        return all(self._run_check_sync(c, t) for _, c, t in checks) if checks else True

    def is_ready(self) -> bool:
        """True if ready flag set AND all readiness checks pass. Sync-only callers."""
        with self._lock:
            ready_flag = self._ready
            checks = list(self._ready_checks)
        if not ready_flag:
            return False
        return all(self._run_check_sync(c, t) for _, c, t in checks) if checks else True

    def liveness_response(self) -> dict:
        """Sync probe response. Prefer ``liveness_response_async`` from async code."""
        with self._lock:
            checks = list(self._live_checks)
        results = {name: self._run_check_sync(check, timeout) for name, check, timeout in checks}
        alive = all(results.values()) if results else True
        return self._build_response("alive" if alive else "not_alive", results)

    def readiness_response(self) -> dict:
        """Sync probe response. Prefer ``readiness_response_async`` from async code."""
        with self._lock:
            ready_flag = self._ready
            checks = list(self._ready_checks)
        results = {name: self._run_check_sync(check, timeout) for name, check, timeout in checks}
        ready = ready_flag and (all(results.values()) if results else True)
        return self._build_response("ready" if ready else "not_ready", results)

    def startup_response(self) -> dict:
        with self._lock:
            started = self._started
        return self._build_response("started" if started else "starting", {})

    # --- async probe responses (preferred for FastAPI endpoints) ---

    async def liveness_response_async(self) -> dict:
        """Run all liveness checks concurrently with per-check timeouts."""
        with self._lock:
            checks = list(self._live_checks)
        results = await self._run_checks_async(checks)
        alive = all(results.values()) if results else True
        return self._build_response("alive" if alive else "not_alive", results)

    async def readiness_response_async(self) -> dict:
        """Run all readiness checks concurrently with per-check timeouts."""
        with self._lock:
            ready_flag = self._ready
            checks = list(self._ready_checks)
        results = await self._run_checks_async(checks)
        ready = ready_flag and (all(results.values()) if results else True)
        return self._build_response("ready" if ready else "not_ready", results)

    async def is_live_async(self) -> bool:
        with self._lock:
            checks = list(self._live_checks)
        results = await self._run_checks_async(checks)
        return all(results.values()) if results else True

    async def is_ready_async(self) -> bool:
        with self._lock:
            ready_flag = self._ready
            checks = list(self._ready_checks)
        if not ready_flag:
            return False
        results = await self._run_checks_async(checks)
        return all(results.values()) if results else True

    # --- internals ---

    async def _run_checks_async(self, checks: list[tuple[str, AnyCheck, float]]) -> dict[str, bool]:
        """Run checks concurrently. Each check has its own timeout budget."""
        if not checks:
            return {}
        tasks = [asyncio.create_task(self._run_check_async(check, timeout)) for _, check, timeout in checks]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            name: (outcome if isinstance(outcome, bool) else False)
            for (name, _, _), outcome in zip(checks, outcomes, strict=True)
        }

    @staticmethod
    async def _run_check_async(check: AnyCheck, timeout: float) -> bool:
        """Execute one check with timeout. Sync checks go via run_blocking."""
        try:
            async with asyncio.timeout(timeout):
                if inspect.iscoroutinefunction(check):
                    return bool(await check())
                from hyperi_pylib.concurrency import run_blocking

                return bool(await run_blocking(check))
        except TimeoutError:
            return False
        except Exception:
            return False

    @staticmethod
    def _run_check_sync(check: AnyCheck, _timeout: float) -> bool:
        """Sync execution path. Timeout NOT enforced -- sync callers accept blocking."""
        try:
            result = check()
            if inspect.isawaitable(result):
                # Caller registered an async check but invoked the sync path.
                # Run it on a fresh loop with timeout.
                return bool(asyncio.run(asyncio.wait_for(result, _timeout)))
            return bool(result)
        except Exception:
            return False

    def _build_response(self, status: str, checks: dict[str, bool]) -> dict:
        return {
            "status": status,
            "timestamp": self._now_rfc3339(),
            "checks": checks,
        }

    @staticmethod
    def _now_rfc3339() -> str:
        return datetime.now(UTC).isoformat()
