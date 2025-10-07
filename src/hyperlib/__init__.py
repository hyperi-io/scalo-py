"""
HyperLib - Enterprise Infrastructure for Containerized Python Applications
Provides configuration, logging, timeout, container, and resource management

Requires Python 3.11+ for modern type hints and enterprise features
"""

__version__ = "1.5.5"

# Enforce Python 3.11+ requirement
import sys

from . import config, container, logger, sampling, timeout
from .config import get_logging_config

# Re-export commonly used functions for convenience
from .logger import get_logger
from .logger import setup as setup_logger

__all__ = [
    "config",
    "logger",
    "timeout",
    "container",
    "sampling",
    "get_logger",
    "setup_logger",
    "get_logging_config",
    "__version__",
]
