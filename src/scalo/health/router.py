#  Project:   scalo
#  File:      src/scalo/health/router.py
#  Purpose:   FastAPI router factory for health probe endpoints
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""
FastAPI router factory for Kubernetes health probes.

Creates a router with ``/health/live``, ``/health/ready``, and
``/health/startup`` endpoints. FastAPI is imported lazily so this
module can be installed without requiring FastAPI at import time.

Usage::

    from fastapi import FastAPI
    from scalo.health import create_health_router, HealthManager

    manager = HealthManager()
    app = FastAPI()
    app.include_router(create_health_router(manager))

    # Later, during startup:
    manager.set_started()
    manager.set_ready()
"""

from __future__ import annotations

from .manager import HealthManager
from .observability import LIVENESS_PATH, READINESS_PATH


def create_health_router(manager: HealthManager | None = None) -> APIRouter:
    """Create a FastAPI router with standard health probe endpoints.

    Canonical paths (these match scalo-rs and the deployment contract's
    ``HealthContract`` defaults):

    - ``GET /healthz`` - Liveness probe (200 if alive, 503 if not)
    - ``GET /readyz`` - Readiness probe (200 if ready, 503 if not)

    Sanctioned aliases, kept so existing charts keep working:

    - ``GET /health/live`` - alias of ``/healthz``
    - ``GET /health/ready`` - alias of ``/readyz``
    - ``GET /health/startup`` - startup probe (200 if started, 503 if not)

    The ``*z`` suffix is the convention, chosen to keep probe routes
    visually distinct from application routes. Startup deliberately has no
    canonical path of its own -- the standard points ``startupProbe`` at the
    liveness path so the two cannot drift apart -- so ``/health/startup``
    remains available but is not the recommended target.

    Prefer the dedicated observability port for these
    (:func:`scalo.health.serve_observability`); mounting them on the
    application's own listener puts the operator surface behind the same
    ingress as user traffic.

    Args:
        manager: HealthManager instance. If None, a default is created
            with no checks and not-ready/not-started state.

    Returns:
        FastAPI APIRouter ready to be included via ``app.include_router()``.

    Raises:
        ImportError: If FastAPI is not installed.
    """
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError("FastAPI required for health router. Install with: pip install fastapi")

    if manager is None:
        manager = HealthManager()

    router = APIRouter(tags=["health"])

    @router.get(LIVENESS_PATH)
    @router.get("/health/live")
    async def liveness() -> JSONResponse:
        """Liveness probe -- is the process alive?

        Checks run concurrently via ``run_blocking`` with per-check
        timeout so a single slow check can't stall the kubelet probe.
        """
        resp = await manager.liveness_response_async()
        status_code = 200 if resp["status"] == "alive" else 503
        return JSONResponse(content=resp, status_code=status_code)

    @router.get(READINESS_PATH)
    @router.get("/health/ready")
    async def readiness() -> JSONResponse:
        resp = await manager.readiness_response_async()
        status_code = 200 if resp["status"] == "ready" else 503
        return JSONResponse(content=resp, status_code=status_code)

    @router.get("/health/startup")
    async def startup() -> JSONResponse:
        resp = manager.startup_response()
        status_code = 200 if resp["status"] == "started" else 503
        return JSONResponse(content=resp, status_code=status_code)

    return router
