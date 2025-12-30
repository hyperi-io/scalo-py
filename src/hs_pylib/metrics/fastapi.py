# Project:   hs-pylib
# File:      metrics/fastapi.py
# Purpose:   FastAPI metrics middleware and router for Prometheus
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
FastAPI metrics integration - middleware and router for Prometheus metrics.

Provides:
    - PrometheusMiddleware: Auto-instrument HTTP requests
    - create_metrics_router: Create /metrics endpoint

Quick Start:
    >>> from fastapi import FastAPI
    >>> from hs_pylib.metrics import create_metrics
    >>> from hs_pylib.metrics.fastapi import PrometheusMiddleware, create_metrics_router
    >>>
    >>> app = FastAPI()
    >>> metrics = create_metrics("myapp")
    >>>
    >>> # Add middleware for HTTP metrics
    >>> app.add_middleware(PrometheusMiddleware, metrics_manager=metrics)
    >>>
    >>> # Add /metrics endpoint
    >>> app.include_router(create_metrics_router(metrics))

Metrics Exposed:
    - http_requests_total: Counter with labels [method, endpoint, status_code]
    - http_request_duration_seconds: Histogram with labels [method, endpoint]
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from fastapi import APIRouter, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from .manager import MetricsManager


class PrometheusMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that instruments FastAPI requests with Prometheus metrics.

    Tracks:
        - http_requests_total: Total request count by method, endpoint, status
        - http_request_duration_seconds: Request latency histogram

    Usage:
        >>> from fastapi import FastAPI
        >>> from hs_pylib.metrics import create_metrics
        >>> from hs_pylib.metrics.fastapi import PrometheusMiddleware
        >>>
        >>> app = FastAPI()
        >>> metrics = create_metrics("myapp")
        >>> app.add_middleware(PrometheusMiddleware, metrics_manager=metrics)

    Endpoint Normalisation:
        Path parameters are normalised to reduce cardinality:
        - /users/123 -> /users/{id}
        - /items/abc-def -> /items/{id}

        This prevents metric explosion from high-cardinality endpoints.
    """

    def __init__(
        self,
        app: Any,
        metrics_manager: MetricsManager | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        """Initialise Prometheus middleware.

        Args:
            app: ASGI application
            metrics_manager: MetricsManager instance (creates default if None)
            exclude_paths: Paths to exclude from metrics (default: ["/metrics", "/health"])
        """
        super().__init__(app)

        # Create default metrics manager if not provided
        if metrics_manager is None:
            from .manager import create_metrics

            metrics_manager = create_metrics("app")

        self.metrics = metrics_manager
        self.exclude_paths = exclude_paths or ["/metrics", "/health", "/health/live", "/health/ready", "/health/startup"]

        # Create HTTP metrics
        self.request_counter = self.metrics.counter(
            "http_requests_total",
            "Total HTTP requests",
            labels=["method", "endpoint", "status_code"],
        )
        self.request_duration = self.metrics.histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            labels=["method", "endpoint"],
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and record metrics."""
        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)

        # Normalise endpoint for metrics (reduce cardinality)
        endpoint = self._normalise_path(request)
        method = request.method

        # Time the request
        start_time = time.perf_counter()
        status_code = "200"
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except HTTPException as exc:  # Capture known HTTP errors
            status_code = str(exc.status_code)
            raise
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.perf_counter() - start_time
            self.request_counter.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)

    def _normalise_path(self, request: Request) -> str:
        """Normalise path to reduce metric cardinality.

        Uses route pattern if available, otherwise returns raw path with
        numeric/UUID segments replaced.

        Args:
            request: Starlette Request object

        Returns:
            Normalised path string
        """
        # Try to get route pattern from matched route
        if hasattr(request, "scope") and "route" in request.scope:
            route = request.scope["route"]
            if hasattr(route, "path"):
                return route.path

        # Fallback: replace numeric/UUID segments with {id}
        import re

        path = request.url.path
        # Replace UUIDs
        path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/{id}", path, flags=re.I)
        # Replace numeric IDs
        path = re.sub(r"/\d+", "/{id}", path)
        return path


def create_metrics_router(
    metrics_manager: MetricsManager,
    path: str = "/metrics",
    tags: list[str] | None = None,
) -> APIRouter:
    """Create FastAPI router with /metrics endpoint.

    Args:
        metrics_manager: MetricsManager instance
        path: Endpoint path (default: /metrics)
        tags: OpenAPI tags for endpoint

    Returns:
        APIRouter with metrics endpoint

    Usage:
        >>> from fastapi import FastAPI
        >>> from hs_pylib.metrics import create_metrics
        >>> from hs_pylib.metrics.fastapi import create_metrics_router
        >>>
        >>> app = FastAPI()
        >>> metrics = create_metrics("myapp")
        >>> app.include_router(create_metrics_router(metrics))
    """
    router = APIRouter(tags=tags or ["metrics"])

    @router.get(path, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=metrics_manager.metrics,
            media_type=metrics_manager.content_type,
        )

    return router


def create_health_router(
    tags: list[str] | None = None,
    ready_check: Callable[[], bool] | None = None,
    startup_check: Callable[[], bool] | None = None,
) -> APIRouter:
    """Create FastAPI router with standard health endpoints.

    Endpoints:
        - /health/live: Always 200 if process running (K8s liveness)
        - /health/ready: 200 if app can serve traffic (K8s readiness)
        - /health/startup: 200 if initialisation complete (K8s startup)

    Args:
        tags: OpenAPI tags for endpoints
        ready_check: Optional callable returning True if ready
        startup_check: Optional callable returning True if started

    Returns:
        APIRouter with health endpoints

    Usage:
        >>> from fastapi import FastAPI
        >>> from hs_pylib.metrics.fastapi import create_health_router
        >>>
        >>> app = FastAPI()
        >>> app.include_router(create_health_router())
        >>>
        >>> # With custom checks
        >>> def is_db_connected():
        ...     return db.is_connected()
        >>>
        >>> app.include_router(create_health_router(ready_check=is_db_connected))
    """
    router = APIRouter(prefix="/health", tags=tags or ["health"])

    @router.get("/live")
    async def liveness() -> dict[str, str]:
        """Liveness probe - is process alive?"""
        return {"status": "alive"}

    @router.get("/ready")
    async def readiness() -> Response:
        """Readiness probe - can handle traffic?"""
        if ready_check is not None and not ready_check():
            return Response(
                content='{"status": "not_ready"}',
                status_code=503,
                media_type="application/json",
            )
        return Response(
            content='{"status": "ready"}',
            status_code=200,
            media_type="application/json",
        )

    @router.get("/startup")
    async def startup() -> Response:
        """Startup probe - initialisation complete?"""
        if startup_check is not None and not startup_check():
            return Response(
                content='{"status": "starting"}',
                status_code=503,
                media_type="application/json",
            )
        return Response(
            content='{"status": "started"}',
            status_code=200,
            media_type="application/json",
        )

    return router
