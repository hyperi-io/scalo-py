"""scalo -- Opinionated, drop-in toolkit for production Python services.

An integrated runtime for control-plane services. Attach and 'enterprise-up'
your application.

Opinionated, drop-in, working out of the box. The patterns from blog posts,
watercooler chats and beers with your Google mates as actual library -- not
a framework you assemble from twenty pip extras and 8 weeks of arguing about
asyncio.

Built as the foundation for HyperI's production Python services. Generic
enough that you don't need to be at HyperI to use it.

Quick Start
===========

    # Install
    pip install scalo[metrics]

    # Use components directly:
    from scalo import logger, get_runtime_paths, create_metrics
    from scalo.config import settings

    logger.info("Service starting")
    runtime = get_runtime_paths()                   # Auto-detects K8s/Docker/local
    metrics = create_metrics(namespace="myapp")     # Auto-collects process metrics

Core Features
=============

**1. Configuration (7-Layer Cascade)**

    from scalo.config import settings

    # Automatic cascade: ENV > .env > settings.yaml > defaults
    host = settings.database.host
    port = settings.api.port
    # No cascade implementation needed!

**2. Structured Logging (RFC 3339)**

    # Recommended: Import from submodule (gets logger object)
    from scalo.logger import logger
    logger.info("User login", user_id=123, ip="192.168.1.1")
    logger.error("DB connection failed", database="prod", retry=3)

    # Also works: Convenience functions
    from scalo.logger import info, error, success
    info("User logged in")

    # Note: logger is Loguru's global singleton
    # All imports reference the SAME logger instance

**3. Runtime Paths (Container-Aware)**

    from scalo import get_runtime_paths

    runtime = get_runtime_paths()
    config = runtime.config_dir / "app.yaml"        # /config or ~/.config
    data = runtime.data_dir / "state.db"            # /data or ~/.local/share
    # Same code works in K8s, Docker, local!

**4. Prometheus Metrics**

    from scalo import create_metrics

    metrics = create_metrics(namespace="myapp")
    metrics.http_requests.inc()                     # Counter
    metrics.active_users.set(42)                    # Gauge
    metrics.request_duration.observe(0.123)         # Histogram
    # Auto-collects process/container metrics too!

**5. Kafka Client**

    from scalo.kafka import KafkaClient, KafkaConsumer, KafkaProducer

    # Full-featured Kafka support with admin, metrics, and health checks

Zero Configuration Philosophy
==============================

- **Auto-detects** everything (environment, paths, formats)
- **Sensible defaults** for all settings
- **ENV-based overrides** for deployment flexibility
- **Container-aware** (K8s, Docker, bare metal)
- **Production-ready** out of the box

Requires Python 3.14+ for modern type hints and enterprise features

---

NOTE: The Application framework (Application.api(), .cli(), .daemon(), etc.)
has been deprecated and moved to backlog. It was experimental and not used
in production. Use the core modules directly (logger, config, runtime, etc.)
for all production code. The Application framework may return in a future
version once the design is mature.
"""

from importlib.metadata import version as _pkg_version

# Single source of truth: installed package metadata. CI stamps pyproject.toml
# at build time, so this matches the published tag and never drifts. No
# hardcoded version, no release-time file rewrite.
__version__ = _pkg_version("scalo")

# Import modules (packages) - logger is a module for extensibility
from . import cli, config, health, logger, metrics, runtime, version_check

# Import commonly used objects and functions
from .config import get_environment, get_logging_config, get_mount_config
from .metrics import create_metrics
from .runtime import get_runtime_paths

# Backward compatibility aliases
prometheus = metrics  # Old name

__all__ = [
    "__version__",
    # Core modules
    "cli",
    "config",
    "create_metrics",
    "get_environment",
    # Functions
    "get_logging_config",
    "get_mount_config",
    "get_runtime_paths",
    "health",
    "logger",
    "metrics",
    "prometheus",
    "runtime",
    "version_check",
]
