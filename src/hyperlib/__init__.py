"""
HyperLib - Enterprise Infrastructure for Python Applications
==============================================================

Zero-configuration infrastructure library for containerized Python apps.
Configuration, logging, metrics, database utilities - all automatic!

Quick Start (Complete Example)
===============================

    # Install
    pip install hyperlib[database,metrics,api]

    # Create application (one line!)
    from hyperlib import Application

    app = Application()

    # Everything configured automatically:
    app.logger.info("Application started")          # Structured logging
    app.config.database.host                        # ENV > .env > yaml > defaults
    app.runtime.data_dir                            # /data (K8s) or ~/.local/share (local)

    # Or use components directly:
    from hyperlib import logger, get_runtime_paths, create_metrics
    from hyperlib.config import settings
    from hyperlib.dbconn import build_database_url

    logger.info("Service starting")
    runtime = get_runtime_paths()                   # Auto-detects K8s/Docker/local
    metrics = create_metrics(namespace="myapp")    # Auto-collects process metrics
    db_url = build_database_url("postgresql")      # Reads POSTGRES_* ENV vars

Core Features
=============

**1. Configuration (7-Layer Cascade)**

    from hyperlib.config import settings

    # Automatic cascade: ENV > .env > settings.yaml > defaults
    host = settings.database.host
    port = settings.api.port
    # No cascade implementation needed!

**2. Structured Logging (RFC 3339)**

    from hyperlib import logger

    logger.info("User login", user_id=123, ip="192.168.1.1")
    logger.error("DB connection failed", database="prod", retry=3)
    # Auto-formatted, timestamped, searchable

**3. Runtime Paths (Container-Aware)**

    from hyperlib import get_runtime_paths

    runtime = get_runtime_paths()
    config = runtime.config_dir / "app.yaml"        # /config or ~/.config
    data = runtime.data_dir / "state.db"            # /data or ~/.local/share
    # Same code works in K8s, Docker, local!

**4. Database URLs (ENV-Based)**

    from hyperlib import build_database_url

    postgres = build_database_url("postgresql")     # POSTGRES_HOST, POSTGRES_PORT, etc.
    redis = build_database_url("redis")             # REDIS_HOST, REDIS_PORT, etc.
    # Automatic connection string construction

**5. Prometheus Metrics**

    from hyperlib import create_metrics

    metrics = create_metrics(namespace="myapp")
    metrics.http_requests.inc()                     # Counter
    metrics.active_users.set(42)                    # Gauge
    metrics.request_duration.observe(0.123)         # Histogram
    # Auto-collects process/container metrics too!

Deployment Patterns
===================

**1. FastAPI Application:**

    from hyperlib import Application
    from fastapi import FastAPI

    app = Application()
    api = FastAPI()

    @api.get("/health")
    def health():
        return {"status": "healthy"}

    # Run with: uvicorn main:api --host 0.0.0.0 --port 8000

**2. CLI Tool:**

    from hyperlib import Application

    app = Application()
    app.logger.info("CLI started")

    # Access config, paths, metrics
    data_dir = app.runtime.data_dir

**3. Daemon/Background Worker:**

    from hyperlib import Application

    app = Application()

    while True:
        app.logger.debug("Processing queue")
        # Use app.config, app.logger, app.metrics

Zero Configuration Philosophy
==============================

✅ **Auto-detects** everything (environment, paths, formats)
✅ **Sensible defaults** for all settings
✅ **ENV-based overrides** for deployment flexibility
✅ **Container-aware** (K8s, Docker, bare metal)
✅ **Production-ready** out of the box

Requires Python 3.11+ for modern type hints and enterprise features
"""

__version__ = "2.6.2"

# Enforce Python 3.11+ requirement
import sys

from . import config, dbconn, harness, logger, prometheus, runtime
from .application import Application
from .config import get_environment, get_logging_config, get_mount_config
from .dbconn import build_database_url, get_database_config, get_database_url_from_env

# Re-export commonly used functions for convenience
from .prometheus import create_metrics
from .runtime import get_runtime_paths

__all__ = [
    "Application",  # Primary user-facing API
    "config",
    "dbconn",
    "harness",
    "logger",
    "runtime",
    "prometheus",
    "get_logging_config",
    "get_mount_config",
    "get_environment",
    "get_runtime_paths",
    "create_metrics",
    "build_database_url",
    "get_database_config",
    "get_database_url_from_env",
    "__version__",
]
