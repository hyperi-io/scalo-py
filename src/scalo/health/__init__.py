#  Project:   scalo
#  File:      src/scalo/health/__init__.py
#  Purpose:   Health probe module -- HealthManager and FastAPI router factory
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Health probe module for Kubernetes-style liveness and readiness checks.

Provides a pure-Python ``HealthManager`` for tracking probe state, and a
FastAPI router factory for exposing ``/livez`` and ``/readyz`` with one line.

Startup state lives on the manager (``set_started()``) but has no endpoint of
its own: a ``startupProbe`` targets ``/livez``, since Kubernetes suspends
liveness until the startup probe passes.

Quick start::

    from fastapi import FastAPI
    from scalo.health import create_health_router, HealthManager

    manager = HealthManager()
    app = FastAPI()
    app.include_router(create_health_router(manager))

    # After initialisation completes:
    manager.set_started()
    manager.set_ready()

The ``HealthManager`` has no external dependencies. The router factory
requires FastAPI and raises ``ImportError`` if it is not installed.

Mounting the probes on the application's own port is only one of the two
shapes. The other -- and the one the container standard wants -- is a
dedicated observability port carrying health AND metrics, separate from the
port serving user traffic. ``ServiceApp`` does that for you; standalone
services can do it directly::

    from scalo.health import HealthManager, serve_observability

    health = HealthManager()
    server = serve_observability(health, metrics, "0.0.0.0:9090")

That listener is stdlib-only, so it does not depend on the FastAPI extra.
"""

from .manager import HealthManager, HealthStatus
from .observability import (
    DEFAULT_OBSERVABILITY_ADDR,
    LIVENESS_PATH,
    METRICS_PATH,
    READINESS_PATH,
    ObservabilityServer,
    parse_addr,
    serve_observability,
)
from .router import create_health_router

__all__ = [
    "DEFAULT_OBSERVABILITY_ADDR",
    "LIVENESS_PATH",
    "METRICS_PATH",
    "READINESS_PATH",
    "HealthManager",
    "HealthStatus",
    "ObservabilityServer",
    "create_health_router",
    "parse_addr",
    "serve_observability",
]
