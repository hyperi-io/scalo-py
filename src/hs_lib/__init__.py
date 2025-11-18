"""
HS-Lib - Enterprise Infrastructure for Python Applications
===========================================================

Zero-configuration infrastructure library for containerized Python apps.
Configuration, logging, metrics, database utilities - all automatic!

Quick Start (Complete Example)
===============================

    # Install
    pip install hs-lib[database,metrics,api]

    # Create application (one line!)
    from hs_lib import Application

    app = Application()

    # Everything configured automatically:
    app.logger.info("Application started")          # Structured logging
    app.config.database.host                        # ENV > .env > yaml > defaults
    app.runtime.data_dir                            # /data (K8s) or ~/.local/share (local)

    # Or use components directly:
    from hs_lib import logger, get_runtime_paths, create_metrics
    from hs_lib.config import settings
    from hs_lib.dbconn import build_database_url

    logger.info("Service starting")
    runtime = get_runtime_paths()                   # Auto-detects K8s/Docker/local
    metrics = create_metrics(namespace="myapp")    # Auto-collects process metrics
    db_url = build_database_url("postgresql")      # Reads POSTGRES_* ENV vars

Core Features
=============

**1. Configuration (7-Layer Cascade)**

    from hs_lib.config import settings

    # Automatic cascade: ENV > .env > settings.yaml > defaults
    host = settings.database.host
    port = settings.api.port
    # No cascade implementation needed!

**2. Structured Logging (RFC 3339)**

    # Recommended: Import from submodule (gets logger object)
    from hs_lib.logger import logger
    logger.info("User login", user_id=123, ip="192.168.1.1")
    logger.error("DB connection failed", database="prod", retry=3)

    # Also works: Convenience functions
    from hs_lib.logger import info, error, success
    info("User logged in")

    # Note: logger is Loguru's global singleton
    # All imports reference the SAME logger instance

**3. Runtime Paths (Container-Aware)**

    from hs_lib import get_runtime_paths

    runtime = get_runtime_paths()
    config = runtime.config_dir / "app.yaml"        # /config or ~/.config
    data = runtime.data_dir / "state.db"            # /data or ~/.local/share
    # Same code works in K8s, Docker, local!

**4. Database URLs (ENV-Based)**

    from hs_lib import build_database_url

    postgres = build_database_url("postgresql")     # POSTGRES_HOST, POSTGRES_PORT, etc.
    redis = build_database_url("redis")             # REDIS_HOST, REDIS_PORT, etc.
    # Automatic connection string construction

**5. Prometheus Metrics**

    from hs_lib import create_metrics

    metrics = create_metrics(namespace="myapp")
    metrics.http_requests.inc()                     # Counter
    metrics.active_users.set(42)                    # Gauge
    metrics.request_duration.observe(0.123)         # Histogram
    # Auto-collects process/container metrics too!

Deployment Patterns
===================

**1. FastAPI Application:**

    from hs_lib import Application
    from fastapi import FastAPI

    app = Application()
    api = FastAPI()

    @api.get("/health")
    def health():
        return {"status": "healthy"}

    # Run with: uvicorn main:api --host 0.0.0.0 --port 8000

**2. CLI Tool (with Typer):**

    from hs_lib import Application
    from hs_lib.cli import Typer, Argument, Option

    app = Application()
    cli = Typer(help="My CLI tool")

    @cli.command()
    def process(file: str = Argument(...)):
        app.logger.info("Processing file", file=file)
        # Access config, paths, metrics
        data_dir = app.runtime.data_dir

    if __name__ == "__main__":
        cli()

**3. Daemon/Background Worker:**

    from hs_lib import Application

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

Requires Python 3.12+ for modern type hints and enterprise features
"""

__version__ = "2.9.0"  # Managed by semantic-release

# Import modules (packages) - logger is a module for extensibility
from . import cli, config, database, harness, logger, metrics, runtime
from .application import Application

# Import commonly used objects and functions
from .config import get_environment, get_logging_config, get_mount_config
from .database import build_database_url, get_database_config, get_database_url_from_env
from .metrics import create_metrics
from .runtime import get_runtime_paths

# Backward compatibility aliases
dbconn = database  # Old name
prometheus = metrics  # Old name

__all__ = [
    "Application",  # Primary user-facing API
    "cli",
    "config",
    "database",
    "harness",
    "logger",
    "runtime",
    "metrics",
    # Backward compatibility
    "dbconn",
    "prometheus",
    # Functions
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
