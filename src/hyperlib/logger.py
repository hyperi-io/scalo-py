"""
HyperLib Logger - Standard Loguru Interface
Enforces consistent logging usage across ALL /src code with RFC 3339 compliance
"""

import sys

from loguru import logger as _logger

from .config import get_logging_config

# Standard logger instance
logger = _logger

# Solarized color palette (https://ethanschoonover.com/solarized/)
SOLARIZED = {
    "base03": "#002b36",
    "base02": "#073642",
    "base01": "#586e75",
    "base00": "#657b83",
    "base0": "#839496",
    "base1": "#93a1a1",
    "base2": "#eee8d5",
    "base3": "#fdf6e3",
    "yellow": "#b58900",
    "orange": "#cb4b16",
    "red": "#dc322f",
    "magenta": "#d33682",
    "violet": "#6c71c4",
    "blue": "#268bd2",
    "cyan": "#2aa198",
    "green": "#859900",
}


def setup(settings=None, color_scheme="solarized"):
    """Setup standard logging with RFC 3339 compliance

    Args:
        settings: Optional settings dict (deprecated, use config instead)
        color_scheme: Color scheme to use - "solarized" (default) or "loguru"
    """

    # Remove default handler
    logger.remove()

    # Get logging config
    config = get_logging_config()

    # Configure color scheme
    if color_scheme == "solarized":
        # Solarized color scheme for log levels
        logger.level("TRACE", color=f"<fg {SOLARIZED['base01']}>")  # base01 - gray
        logger.level("DEBUG", color=f"<fg {SOLARIZED['base01']}>")  # base01 - gray
        logger.level("INFO", color=f"<fg {SOLARIZED['blue']}>")  # blue - primary accent
        logger.level("SUCCESS", color=f"<fg {SOLARIZED['green']}>")  # green - success
        logger.level("WARNING", color=f"<fg {SOLARIZED['yellow']}>")  # yellow - attention
        logger.level("ERROR", color=f"<fg {SOLARIZED['orange']}>")  # orange - error
        logger.level("CRITICAL", color=f"<fg {SOLARIZED['red']}>")  # red - critical

        # Solarized format with explicit colors
        console_format = (
            f"<fg {SOLARIZED['green']}>{{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}}</fg {SOLARIZED['green']}> | "
            f"<level>{{level: <8}}</level> | "
            f"<fg {SOLARIZED['cyan']}>{{name}}</fg {SOLARIZED['cyan']}>:"
            f"<fg {SOLARIZED['cyan']}>{{function}}</fg {SOLARIZED['cyan']}>:"
            f"<fg {SOLARIZED['cyan']}>{{line}}</fg {SOLARIZED['cyan']}> - "
            f"<level>{{message}}</level>"
        )
    else:
        # Loguru default colors (don't configure levels, use built-in defaults)
        console_format = "<green>{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

    # Add console handler with RFC 3339 format
    if config.get("console", True):
        logger.add(
            sys.stderr,
            level=config.get("level", "INFO"),
            format=console_format,
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


# Initialize with default setup (Solarized)
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
