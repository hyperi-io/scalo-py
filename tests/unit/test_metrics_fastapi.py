# Project:   hyperi-pylib
# File:      tests/unit/test_metrics_fastapi.py
# Purpose:   Unit tests for hyperi_pylib.metrics.fastapi module
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for hyperi_pylib.metrics.fastapi module."""

import pytest


class TestPrometheusMiddleware:
    """Tests for PrometheusMiddleware."""

    def test_import(self):
        """Test that PrometheusMiddleware can be imported."""
        from hyperi_pylib.metrics.fastapi import PrometheusMiddleware

        assert PrometheusMiddleware is not None

    def test_middleware_creates_metrics(self):
        """Test middleware creates HTTP metrics."""
        from unittest.mock import MagicMock

        from hyperi_pylib.metrics.fastapi import PrometheusMiddleware

        mock_app = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.counter = MagicMock(return_value=MagicMock())
        mock_metrics.histogram = MagicMock(return_value=MagicMock())

        PrometheusMiddleware(mock_app, metrics_manager=mock_metrics)

        # Verify metrics were created
        mock_metrics.counter.assert_called_once()
        mock_metrics.histogram.assert_called_once()

        # Verify correct metric names
        counter_call = mock_metrics.counter.call_args
        assert counter_call[0][0] == "http_requests_total"

        histogram_call = mock_metrics.histogram.call_args
        assert histogram_call[0][0] == "http_request_duration_seconds"

    def test_default_exclude_paths(self):
        """Test default excluded paths."""
        from unittest.mock import MagicMock

        from hyperi_pylib.metrics.fastapi import PrometheusMiddleware

        mock_app = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.counter = MagicMock(return_value=MagicMock())
        mock_metrics.histogram = MagicMock(return_value=MagicMock())

        middleware = PrometheusMiddleware(mock_app, metrics_manager=mock_metrics)

        assert "/metrics" in middleware.exclude_paths
        assert "/health" in middleware.exclude_paths
        assert "/health/live" in middleware.exclude_paths
        assert "/health/ready" in middleware.exclude_paths

    def test_custom_exclude_paths(self):
        """Test custom excluded paths."""
        from unittest.mock import MagicMock

        from hyperi_pylib.metrics.fastapi import PrometheusMiddleware

        mock_app = MagicMock()
        mock_metrics = MagicMock()
        mock_metrics.counter = MagicMock(return_value=MagicMock())
        mock_metrics.histogram = MagicMock(return_value=MagicMock())

        middleware = PrometheusMiddleware(
            mock_app,
            metrics_manager=mock_metrics,
            exclude_paths=["/custom", "/internal"],
        )

        assert "/custom" in middleware.exclude_paths
        assert "/internal" in middleware.exclude_paths


class TestCreateMetricsRouter:
    """Tests for create_metrics_router."""

    def test_import(self):
        """Test that create_metrics_router can be imported."""
        from hyperi_pylib.metrics.fastapi import create_metrics_router

        assert create_metrics_router is not None

    def test_creates_router(self):
        """Test creates a router with metrics endpoint."""
        from unittest.mock import MagicMock

        from hyperi_pylib.metrics.fastapi import create_metrics_router

        mock_metrics = MagicMock()
        mock_metrics.metrics = b"# HELP test\n"
        mock_metrics.content_type = "text/plain"

        router = create_metrics_router(mock_metrics)

        # Router should have routes
        assert len(router.routes) > 0

        # Find metrics route
        metrics_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/metrics":
                metrics_route = route
                break

        assert metrics_route is not None

    def test_custom_path(self):
        """Test custom metrics path."""
        from unittest.mock import MagicMock

        from hyperi_pylib.metrics.fastapi import create_metrics_router

        mock_metrics = MagicMock()
        router = create_metrics_router(mock_metrics, path="/custom-metrics")

        # Find custom route
        custom_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/custom-metrics":
                custom_route = route
                break

        assert custom_route is not None


class TestCreateHealthRouter:
    """Tests for create_health_router."""

    def test_import(self):
        """Test that create_health_router can be imported."""
        from hyperi_pylib.metrics.fastapi import create_health_router

        assert create_health_router is not None

    def test_creates_router_with_health_endpoints(self):
        """Test creates router with all health endpoints."""
        from hyperi_pylib.metrics.fastapi import create_health_router

        router = create_health_router()

        # Should have 3 routes: /health/live, /health/ready, /health/startup
        paths = [route.path for route in router.routes if hasattr(route, "path")]
        assert "/health/live" in paths
        assert "/health/ready" in paths
        assert "/health/startup" in paths

    def test_health_router_prefix(self):
        """Test health router has correct prefix."""
        from hyperi_pylib.metrics.fastapi import create_health_router

        router = create_health_router()
        assert router.prefix == "/health"

    @pytest.mark.asyncio
    async def test_liveness_endpoint(self):
        """Test liveness endpoint returns alive status."""
        from hyperi_pylib.metrics.fastapi import create_health_router

        router = create_health_router()

        # Find liveness route
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/health/live":
                result = await route.endpoint()
                assert result == {"status": "alive"}
                break

    @pytest.mark.asyncio
    async def test_readiness_with_check(self):
        """Test readiness endpoint with custom check."""
        from hyperi_pylib.metrics.fastapi import create_health_router

        # Test with passing check
        router = create_health_router(ready_check=lambda: True)

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/health/ready":
                response = await route.endpoint()
                assert response.status_code == 200
                break

    @pytest.mark.asyncio
    async def test_readiness_with_failing_check(self):
        """Test readiness endpoint with failing check."""
        from hyperi_pylib.metrics.fastapi import create_health_router

        router = create_health_router(ready_check=lambda: False)

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/health/ready":
                response = await route.endpoint()
                assert response.status_code == 503
                break
