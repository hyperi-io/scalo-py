"""
HyperLib Logger - Standard Loguru Interface
Enforces consistent logging usage across ALL /src code with RFC 3339 compliance
"""

import sys

from loguru import logger as _logger

from .config import get_logging_config

# Standard logger instance
logger = _logger


def setup(settings=None):
    """Setup standard logging with RFC 3339 compliance"""

    # Remove default handler
    logger.remove()

    # Get logging config
    config = get_logging_config()

    # Add console handler with RFC 3339 format (Solarized colors)
    if config.get("console", True):
        logger.add(
            sys.stderr,
            level=config.get("level", "INFO"),
            format="<fg #859900>{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}</fg #859900> | <level>{level: <8}</level> | <fg #2aa198>{name}</fg #2aa198>:<fg #2aa198>{function}</fg #2aa198>:<fg #2aa198>{line}</fg #2aa198> - <level>{message}</level>",
            colorize=True,
        )

    # Add file handler if specified
    log_file = config.get("file")
    if log_file:
        logger.add(
            log_file,
            level=config.get("level", "INFO"),
            format="{time:YYYY-MM-DDTHH:mm:ss.SSSZZ} [{level: <8}] {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
        )

    return logger


def get_logger(name=None):
    """Get standard logger instance

    Args:
        name: Optional logger name (for compatibility, currently ignored)

    Returns:
        Logger instance
    """
    # Note: name parameter is accepted for API compatibility but ignored
    # Loguru's logger is a singleton and uses module context for naming
    return logger


# Initialize with default setup
setup()


# Standard logging functions for convenience
def info(msg):
    logger.info(msg)


def warning(msg):
    logger.warning(msg)


def error(msg):
    logger.error(msg)


def success(msg):
    logger.success(msg)


def debug(msg):
    logger.debug(msg)


# Export for direct usage
__all__ = ["logger", "setup", "get_logger", "info", "warning", "error", "success", "debug"]
