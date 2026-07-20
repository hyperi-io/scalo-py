#  Project:   scalo
#  File:      tests/unit/test_cli_observability.py
#  Purpose:   ServiceApp actually serves the observability port it advertises
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""ServiceApp observability-port wiring (scalo-py#5).

These assert against a RUNNING service rather than against the wiring code:
the defect was that everything looked wired -- flag, env var, default, log
line -- while nothing listened. So each test drives ``run`` and makes a real
HTTP request to the advertised address from inside the service.
"""

from __future__ import annotations

import http.client
import json

import pytest

from scalo.cli import ServiceApp, VersionInfo


def _get(port: int, path: str) -> tuple[int, dict]:
    """GET a JSON probe, returning (status, body).

    http.client keeps the fixed host/port explicit and returns 4xx/5xx as
    ordinary responses -- these tests assert on 503 as much as on 200.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())
    finally:
        conn.close()


class _ProbeApp(ServiceApp):
    """Service that probes its own observability port while running."""

    name = "obs-probe-app"
    env_prefix = "OBS_PROBE"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.1.0")

    def run_service(self, config) -> None:
        self.observed = {}
        port = self._observability.bound_address[1]
        self.observed["port"] = port
        self.observed["healthz"] = _get(port, "/healthz")
        self.observed["startup"] = _get(port, "/health/startup")
        self.observed["readyz_before"] = _get(port, "/readyz")
        self.health().set_ready()
        self.observed["readyz_after"] = _get(port, "/readyz")


def _run(app: ServiceApp, addr: str = "127.0.0.1:0") -> None:
    with pytest.raises(SystemExit) as exc:
        app.cli(["run", "--metrics-addr", addr])
    assert exc.value.code in (0, None), f"service exited {exc.value.code}"


class TestServiceAppServesTheAdvertisedPort:
    def test_healthz_answers_during_run(self):
        app = _ProbeApp()
        _run(app)
        status, body = app.observed["healthz"]
        assert status == 200
        assert body["status"] == "alive"

    def test_readiness_reflects_the_apps_own_manager(self):
        # The app and scalo must share ONE HealthManager, or /readyz reports
        # something the service does not mean.
        app = _ProbeApp()
        _run(app)
        assert app.observed["readyz_before"][0] == 503
        assert app.observed["readyz_after"][0] == 200

    def test_startup_marked_before_service_runs(self):
        # ServiceApp calls health().set_started() before handing control to
        # run_service, so a startupProbe arriving during startup gets 200
        # rather than a 503 that would restart the pod.
        app = _ProbeApp()
        _run(app)
        status, body = app.observed["startup"]
        assert status == 200
        assert body["status"] == "started"

    def test_port_is_closed_after_run(self):
        app = _ProbeApp()
        _run(app)
        port = app.observed["port"]
        # Re-probing must now fail to connect -- the listener is gone.
        with pytest.raises(OSError):
            _get(port, "/healthz")

    def test_server_handle_released_after_run(self):
        app = _ProbeApp()
        _run(app)
        assert app._observability is None


class TestAsyncService:
    def test_async_service_also_gets_the_port(self):
        class _AsyncApp(ServiceApp):
            name = "obs-async-app"
            env_prefix = "OBS_ASYNC"

            def version_info(self) -> VersionInfo:
                return VersionInfo(self.name, "0.1.0")

            def run_service(self, config) -> None:  # pragma: no cover
                raise AssertionError("async path should be used")

            async def run_service_async(self, config) -> None:
                port = self._observability.bound_address[1]
                self.observed = _get(port, "/healthz")

        app = _AsyncApp()
        _run(app)
        assert app.observed[0] == 200


class TestOptOut:
    def test_disabled_binds_nothing(self):
        class _NoObsApp(ServiceApp):
            name = "obs-off-app"
            env_prefix = "OBS_OFF"
            serve_observability = False

            def version_info(self) -> VersionInfo:
                return VersionInfo(self.name, "0.1.0")

            def run_service(self, config) -> None:
                self.observed = self._observability

        app = _NoObsApp()
        _run(app)
        assert app.observed is None


class TestHealthAccessor:
    def test_health_is_stable_across_calls(self):
        app = _ProbeApp()
        assert app.health() is app.health()

    def test_health_available_before_run(self):
        # Apps register readiness checks during construction/startup, so the
        # manager must exist without having run the service.
        app = _ProbeApp()
        app.health().register_ready_check("noop", lambda: True)
        assert app.health().is_ready() is False
