#  Project:   scalo
#  File:      tests/unit/test_health_router.py
#  Purpose:   Unit tests for health FastAPI router factory
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for the health FastAPI router.

Uses FastAPI TestClient for real HTTP-level testing (not mocking).
Tests the /livez and /readyz endpoints with various HealthManager states,
and asserts the retired paths are gone.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scalo.health.manager import HealthManager
from scalo.health.router import create_health_router

RETIRED_PATHS = [
    "/healthz",
    "/health/live",
    "/health/ready",
    "/health/startup",
    "/startupz",
]


@pytest.fixture
def manager() -> HealthManager:
    """Fresh HealthManager for each test."""
    return HealthManager()


@pytest.fixture
def app(manager: HealthManager) -> FastAPI:
    """FastAPI app with health router mounted."""
    app = FastAPI()
    router = create_health_router(manager)
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """TestClient for real HTTP testing."""
    return TestClient(app)


class TestRouterFactory:
    """create_health_router() creates a working FastAPI router."""

    def test_creates_router_with_provided_manager(self):
        mgr = HealthManager()
        router = create_health_router(mgr)
        assert router is not None

    def test_creates_router_with_default_manager(self):
        """When no manager is given, a default is created."""
        router = create_health_router()
        assert router is not None

    def test_router_has_health_tag(self):
        router = create_health_router()
        assert "health" in router.tags


class TestLivenessEndpoint:
    """/livez returns 200 or 503 based on liveness state."""

    def test_live_200_default(self, client: TestClient):
        resp = client.get("/livez")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_live_200_with_passing_checks(self, client: TestClient, manager: HealthManager):
        manager.register_live_check("ok", lambda: True)
        resp = client.get("/livez")
        assert resp.status_code == 200
        assert resp.json()["checks"]["ok"] is True

    def test_live_503_with_failing_check(self, client: TestClient, manager: HealthManager):
        manager.register_live_check("bad", lambda: False)
        resp = client.get("/livez")
        assert resp.status_code == 503
        assert resp.json()["status"] == "not_alive"

    def test_live_response_json_content_type(self, client: TestClient):
        resp = client.get("/livez")
        assert resp.headers["content-type"] == "application/json"

    def test_live_response_has_timestamp(self, client: TestClient):
        resp = client.get("/livez")
        ts = resp.json()["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


class TestReadinessEndpoint:
    """/readyz returns 200 when ready, 503 otherwise."""

    def test_ready_503_default(self, client: TestClient):
        """Not ready by default."""
        resp = client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "not_ready"

    def test_ready_200_after_set_ready(self, client: TestClient, manager: HealthManager):
        manager.set_ready()
        resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_ready_503_with_failing_check(self, client: TestClient, manager: HealthManager):
        manager.set_ready()
        manager.register_ready_check("db", lambda: False)
        resp = client.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["checks"]["db"] is False

    def test_ready_200_with_passing_checks(self, client: TestClient, manager: HealthManager):
        manager.set_ready()
        manager.register_ready_check("db", lambda: True)
        manager.register_ready_check("cache", lambda: True)
        resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["checks"]["db"] is True
        assert resp.json()["checks"]["cache"] is True


class TestRetiredPaths:
    """The retired paths are GONE, not quietly still answering.

    This is the half of the contract that stops an alias creeping back: an
    alias that keeps returning 200 hides a probe still aimed at the old name,
    which is precisely how a chart/app mismatch survives unnoticed.
    """

    @pytest.mark.parametrize("path", RETIRED_PATHS)
    def test_retired_path_404(self, client: TestClient, manager: HealthManager, path: str):
        manager.set_ready()
        manager.set_started()
        assert client.get(path).status_code == 404

    def test_startup_probe_targets_liveness(self, client: TestClient):
        """There is no startup route -- a startupProbe aims at /livez.

        Kubernetes suspends liveness until the startup probe passes, so one
        path serves both without the two drifting apart.
        """
        assert client.get("/livez").status_code == 200
        assert client.get("/health/startup").status_code == 404


class TestEndpointResponseFormat:
    """Both endpoints return consistent JSON matching scalo-rs's format."""

    def test_all_endpoints_have_status_timestamp_checks(self, client: TestClient, manager: HealthManager):
        manager.set_ready()
        for path in ["/livez", "/readyz"]:
            resp = client.get(path)
            data = resp.json()
            assert "status" in data, f"{path} missing 'status'"
            assert "timestamp" in data, f"{path} missing 'timestamp'"
            assert "checks" in data, f"{path} missing 'checks'"

    def test_timestamps_are_rfc3339_with_timezone(self, client: TestClient, manager: HealthManager):
        manager.set_ready()
        for path in ["/livez", "/readyz"]:
            resp = client.get(path)
            ts = resp.json()["timestamp"]
            parsed = datetime.fromisoformat(ts)
            assert parsed.tzinfo is not None, f"{path} timestamp missing timezone: {ts}"
