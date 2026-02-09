"""
hyperi-pylib - Enterprise Infrastructure for Python Applications
=============================================================

Zero-configuration infrastructure library for containerized Python apps.
Configuration, logging, metrics, database utilities - all automatic!

Quick Start
===========

    # Install
    pip install hyperi-pylib[database,metrics]

    # Use components directly:
    from hyperi_pylib import logger, get_runtime_paths, create_metrics
    from hyperi_pylib.config import settings
    from hyperi_pylib.database import build_database_url

    logger.info("Service starting")
    runtime = get_runtime_paths()                   # Auto-detects K8s/Docker/local
    metrics = create_metrics(namespace="myapp")     # Auto-collects process metrics
    db_url = build_database_url("postgresql")       # Reads POSTGRES_* ENV vars

Core Features
=============

**1. Configuration (7-Layer Cascade)**

    from hyperi_pylib.config import settings

    # Automatic cascade: ENV > .env > settings.yaml > defaults
    host = settings.database.host
    port = settings.api.port
    # No cascade implementation needed!

**2. Structured Logging (RFC 3339)**

    # Recommended: Import from submodule (gets logger object)
    from hyperi_pylib.logger import logger
    logger.info("User login", user_id=123, ip="192.168.1.1")
    logger.error("DB connection failed", database="prod", retry=3)

    # Also works: Convenience functions
    from hyperi_pylib.logger import info, error, success
    info("User logged in")

    # Note: logger is Loguru's global singleton
    # All imports reference the SAME logger instance

**3. Runtime Paths (Container-Aware)**

    from hyperi_pylib import get_runtime_paths

    runtime = get_runtime_paths()
    config = runtime.config_dir / "app.yaml"        # /config or ~/.config
    data = runtime.data_dir / "state.db"            # /data or ~/.local/share
    # Same code works in K8s, Docker, local!

**4. Database URLs (ENV-Based)**

    from hyperi_pylib import build_database_url

    postgres = build_database_url("postgresql")     # POSTGRES_HOST, POSTGRES_PORT, etc.
    redis = build_database_url("redis")             # REDIS_HOST, REDIS_PORT, etc.
    # Automatic connection string construction

**5. Prometheus Metrics**

    from hyperi_pylib import create_metrics

    metrics = create_metrics(namespace="myapp")
    metrics.http_requests.inc()                     # Counter
    metrics.active_users.set(42)                    # Gauge
    metrics.request_duration.observe(0.123)         # Histogram
    # Auto-collects process/container metrics too!

**6. Kafka Client**

    from hyperi_pylib.kafka import KafkaClient, KafkaConsumer, KafkaProducer

    # Full-featured Kafka support with admin, metrics, and health checks

Zero Configuration Philosophy
==============================

- **Auto-detects** everything (environment, paths, formats)
- **Sensible defaults** for all settings
- **ENV-based overrides** for deployment flexibility
- **Container-aware** (K8s, Docker, bare metal)
- **Production-ready** out of the box

Requires Python 3.12+ for modern type hints and enterprise features

---

NOTE: The Application framework (Application.api(), .cli(), .daemon(), etc.)
has been deprecated and moved to backlog. It was experimental and not used
in production. Use the core modules directly (logger, config, runtime, etc.)
for all production code. The Application framework may return in a future
version once the design is mature.
"""

__version__ = "2.13.4"  # Managed by semantic-release

# Import modules (packages) - logger is a module for extensibility
from . import cli, config, database, harness, logger, metrics, runtime

# Import commonly used objects and functions
from .config import get_environment, get_logging_config, get_mount_config
from .database import build_database_url, get_database_config, get_database_url_from_env
from .metrics import create_metrics
from .runtime import get_runtime_paths

# Backward compatibility aliases
dbconn = database  # Old name
prometheus = metrics  # Old name

__all__ = [
    # Core modules
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
