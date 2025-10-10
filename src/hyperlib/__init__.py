"""
HyperLib - Enterprise Infrastructure for Containerized Python Applications
Provides configuration, logging, timeout, container, and resource management

Requires Python 3.11+ for modern type hints and enterprise features
"""

__version__ = "1.5.5"

# Enforce Python 3.11+ requirement
import sys

from . import config, dbconn, harness, logger, prometheus, runtime
from .application import Application
from .config import get_logging_config, get_mount_config, get_environment
from .dbconn import build_database_url, get_database_config, get_database_url_from_env

# Re-export commonly used functions for convenience
from .logger import get_logger
from .logger import setup as setup_logger
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
    "get_logger",
    "setup_logger",
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
