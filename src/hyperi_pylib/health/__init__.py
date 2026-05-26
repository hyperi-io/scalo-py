#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/health/__init__.py
#  Purpose:   Health probe module -- HealthManager and FastAPI router factory
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Health probe module for Kubernetes-style liveness, readiness, and startup checks.

Provides a pure-Python ``HealthManager`` for tracking probe state, and a
FastAPI router factory for exposing ``/health/live``, ``/health/ready``,
``/health/startup`` endpoints with one line.

Quick start::

    from fastapi import FastAPI
    from hyperi_pylib.health import create_health_router, HealthManager

    manager = HealthManager()
    app = FastAPI()
    app.include_router(create_health_router(manager))

    # After initialisation completes:
    manager.set_started()
    manager.set_ready()

The ``HealthManager`` has no external dependencies. The router factory
requires FastAPI and raises ``ImportError`` if it is not installed.
"""

from .manager import HealthManager, HealthStatus
from .router import create_health_router

__all__ = [
    "HealthManager",
    "HealthStatus",
    "create_health_router",
]
