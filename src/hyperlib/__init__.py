"""
HyperLib - Enterprise Infrastructure for Containerized Python Applications
Provides configuration, logging, timeout, container, and resource management

Requires Python 3.11+ for modern type hints and enterprise features
"""

__version__ = "1.5.5"

# Enforce Python 3.11+ requirement
import sys

from . import config, container, logger, runtime, sampling, timeout
from .application import Application
from .config import get_logging_config

# Re-export commonly used functions for convenience
from .logger import get_logger
from .logger import setup as setup_logger
from .runtime import get_runtime_paths

__all__ = [
    "Application",  # Primary user-facing API
    "config",
    "logger",
    "timeout",
    "container",
    "runtime",
    "sampling",
    "get_logger",
    "setup_logger",
    "get_logging_config",
    "get_runtime_paths",
    "__version__",
]
