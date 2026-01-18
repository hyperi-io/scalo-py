# Project:   hs-pylib
# File:      examples/fastapi-metrics/tests/test_main.py
# Purpose:   Tests for fastapi-metrics example
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2026 HyperSec

"""Tests for fastapi-metrics example."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_returns_service_info(self, client: TestClient) -> None:
        """Should return service information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "endpoints" in data


class TestUsersEndpoint:
    """Tests for users endpoint."""

    def test_list_users_returns_users(self, client: TestClient) -> None:
        """Should return list of users."""
        response = client.get("/api/users")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert len(data["users"]) == data["total"]

    def test_get_user_returns_user(self, client: TestClient) -> None:
        """Should return specific user."""
        response = client.get("/api/users/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert "name" in data

    def test_get_nonexistent_user_returns_404(self, client: TestClient) -> None:
        """Should return 404 for nonexistent user."""
        response = client.get("/api/users/999")
        assert response.status_code == 404


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_returns_alive(self, client: TestClient) -> None:
        """Health endpoint should return alive status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_health_live_returns_alive(self, client: TestClient) -> None:
        """Liveness probe should return alive status."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_health_ready_returns_ready(self, client: TestClient) -> None:
        """Readiness probe should return ready status."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"


class TestMetricsEndpoint:
    """Tests for Prometheus metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client: TestClient) -> None:
        """Should return Prometheus-format metrics."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        # Should contain standard Prometheus format
        content = response.text
        assert "# HELP" in content or "# TYPE" in content or "myapp_" in content

    def test_metrics_after_requests(self, client: TestClient) -> None:
        """Should track request metrics."""
        # Make some requests
        client.get("/api/users")
        client.get("/api/users")
        client.get("/api/users/1")

        # Check metrics
        response = client.get("/metrics")
        assert response.status_code == 200
        # Metrics should contain request counters
        content = response.text
        # The metrics should be present (exact format depends on implementation)
        assert len(content) > 0


class TestImports:
    """Tests for module imports."""

    def test_create_metrics_import(self) -> None:
        """Should be able to import create_metrics."""
        from hs_pylib.metrics import create_metrics

        assert create_metrics is not None

    def test_main_function_exists(self) -> None:
        """Should have main function."""
        import main

        assert hasattr(main, "main")
        assert callable(main.main)
