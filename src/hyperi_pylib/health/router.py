#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/health/router.py
#  Purpose:   FastAPI router factory for health probe endpoints
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""
FastAPI router factory for Kubernetes health probes.

Creates a router with ``/health/live``, ``/health/ready``, and
``/health/startup`` endpoints. FastAPI is imported lazily so this
module can be installed without requiring FastAPI at import time.

Usage::

    from fastapi import FastAPI
    from hyperi_pylib.health import create_health_router, HealthManager

    manager = HealthManager()
    app = FastAPI()
    app.include_router(create_health_router(manager))

    # Later, during startup:
    manager.set_started()
    manager.set_ready()
"""

from __future__ import annotations

from .manager import HealthManager


def create_health_router(manager: HealthManager | None = None) -> "APIRouter":
    """Create a FastAPI router with standard health probe endpoints.

    Provides three endpoints matching rustlib's built-in health probes:

    - ``GET /health/live`` - Liveness probe (200 if alive, 503 if not)
    - ``GET /health/ready`` - Readiness probe (200 if ready, 503 if not)
    - ``GET /health/startup`` - Startup probe (200 if started, 503 if not)

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

    @router.get("/health/live")
    async def liveness() -> JSONResponse:
        """Liveness probe — is the process alive?"""
        resp = manager.liveness_response()
        status_code = 200 if manager.is_live() else 503
        return JSONResponse(content=resp, status_code=status_code)

    @router.get("/health/ready")
    async def readiness() -> JSONResponse:
        """Readiness probe — can the service handle traffic?"""
        resp = manager.readiness_response()
        status_code = 200 if manager.is_ready() else 503
        return JSONResponse(content=resp, status_code=status_code)

    @router.get("/health/startup")
    async def startup() -> JSONResponse:
        """Startup probe — has initialisation completed?"""
        resp = manager.startup_response()
        status_code = 200 if manager.is_started() else 503
        return JSONResponse(content=resp, status_code=status_code)

    return router
