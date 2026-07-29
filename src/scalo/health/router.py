#  Project:   scalo
#  File:      src/scalo/health/router.py
#  Purpose:   FastAPI router factory for health probe endpoints
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""
FastAPI router factory for Kubernetes health probes.

Creates a router with ``/livez`` and ``/readyz`` endpoints. FastAPI is
imported lazily so this module can be installed without requiring FastAPI
at import time.

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
    """Create a FastAPI router with the standard health probe endpoints.

    These match scalo-rs and the deployment contract's ``HealthContract``
    defaults:

    - ``GET /livez`` - Liveness probe (200 if alive, 503 if not)
    - ``GET /readyz`` - Readiness probe (200 if ready, 503 if not)

    That is the whole surface -- there are no aliases. A second path meaning
    the same thing eventually stops meaning the same thing, and an alias that
    keeps answering 200 hides a probe still pointed at the old name.

    The ``*z`` suffix keeps probe routes visually distinct from application
    routes, following the Kubernetes API server and etcd convention.

    There is no startup route. Point a ``startupProbe`` at ``/livez``:
    Kubernetes suspends liveness until the startup probe passes, so one path
    gives both a generous boot budget and a tight liveness period without the
    two drifting apart.

    Liveness MUST NOT check dependencies -- restarting will not fix someone
    else's datastore, it just destroys warm state mid-outage. Put dependency
    checks in readiness.

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
    async def liveness() -> JSONResponse:
        """Liveness probe -- is the process alive?

        Checks run concurrently via ``run_blocking`` with per-check
        timeout so a single slow check can't stall the kubelet probe.
        """
        resp = await manager.liveness_response_async()
        status_code = 200 if resp["status"] == "alive" else 503
        return JSONResponse(content=resp, status_code=status_code)

    @router.get(READINESS_PATH)
    async def readiness() -> JSONResponse:
        resp = await manager.readiness_response_async()
        status_code = 200 if resp["status"] == "ready" else 503
        return JSONResponse(content=resp, status_code=status_code)

    return router
