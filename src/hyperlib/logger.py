"""
HyperLib Logger - Standard Loguru Interface
Enforces consistent logging usage across ALL /src code with RFC 3339 compliance
Enforces CHARS-POLICY.md for terminal output and log files
"""

import os
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

# CHARS-POLICY.md approved emojis for log levels (terminal output only)
LOG_LEVEL_EMOJIS = {
    "CRITICAL": "💥",  # FATAL - Irrecoverable error
    "ERROR": "❌",  # ERROR - Blocking issue
    "WARNING": "⚠️",  # WARN - Non-blocking issue
    "INFO": "",  # INFO - No emoji
    "SUCCESS": "✅",  # SUCCESS - Everything working
    "DEBUG": "",  # DEBUG - No emoji
    "TRACE": "",  # TRACE - No emoji
}

# Emoji to text replacements for machine-readable logs (CHARS-POLICY.md)
EMOJI_TO_TEXT = {
    "💥": "[FATAL]",
    "❌": "[ERROR]",
    "⚠️": "[WARN]",
    "✅": "[SUCCESS]",
    "🐞": "[BUG]",
    "⏳": "[PENDING]",
    "🚫": "[CANCELLED]",
    "🟢": "[PASS]",
    "🔴": "[FAIL]",
    "🔒": "[SECURITY]",
    "⚡": "[PERFORMANCE]",
    "➤": "->",
    "➔": "=>",
    "✔": "[OK]",
    "⛔": "[BLOCKED]",
    "🔁": "[RETRY]",
}


def strip_emojis(text: str) -> str:
    """Remove all emojis from text (for machine-readable logs).

    Args:
        text: Text that may contain emojis

    Returns:
        Text with emojis removed
    """
    result = text
    for emoji in EMOJI_TO_TEXT.keys():
        result = result.replace(emoji, "")
    return result.strip()


def emojis_to_text(text: str) -> str:
    """Convert emojis to ASCII text equivalents (for machine-readable logs).

    This function converts CHARS-POLICY.md approved emojis to their
    ASCII text equivalents for use in log files and machine-readable output.

    Args:
        text: Text that may contain emojis

    Returns:
        Text with emojis replaced by ASCII equivalents

    Example:
        >>> emojis_to_text("✅ Success")
        "[SUCCESS] Success"
        >>> emojis_to_text("❌ Failed to connect")
        "[ERROR] Failed to connect"
    """
    result = text
    for emoji, replacement in EMOJI_TO_TEXT.items():
        result = result.replace(emoji, replacement)
    return result


def _is_interactive_console() -> bool:
    """Detect if console is interactive (NOT Docker/K8s/daemon).

    Interactive consoles (developer terminals) may use emojis.
    Non-interactive consoles (Docker/K8s/daemons) must use ASCII-only.

    Checks:
    1. Output is a TTY (not a pipe/file/container stdout)
    2. TERM is not 'dumb' or unset
    3. LANG/LC_ALL environment variables for UTF-8

    Returns:
        True if interactive terminal that supports emojis, False otherwise
    """
    # Check if output is a TTY (Docker/K8s stdout is NOT a TTY)
    if not sys.stderr.isatty():
        return False  # Non-interactive (container, pipe, file)

    # Check TERM environment variable
    term = os.getenv("TERM", "")
    if term == "dumb" or not term:
        return False  # Non-interactive or basic terminal

    # Check for UTF-8 locale
    lang = os.getenv("LANG", "")
    lc_all = os.getenv("LC_ALL", "")
    locale = lc_all or lang

    if "UTF-8" in locale.upper() or "UTF8" in locale.upper():
        return True  # Interactive + UTF-8 = emojis OK

    # Default to False for safety (ASCII-only for non-interactive)
    return False


def _add_emoji_to_record(use_emojis: bool, convert_to_text: bool = False, allow_all: bool = False):
    """Create a filter function that adds emojis or converts them to text.

    Args:
        use_emojis: Whether to add emojis to log records
        convert_to_text: Convert emojis to ASCII text (for machine-readable logs)
        allow_all: Allow all emojis without filtering (pass-through user emojis)

    Returns:
        Filter function for loguru
    """

    def filter_func(record):
        """Add emoji to record or convert emojis to text based on settings."""
        if use_emojis:
            if allow_all:
                # Allow all emojis - pass through unchanged, just add level emoji
                emoji = LOG_LEVEL_EMOJIS.get(record["level"].name, "")
                if emoji:
                    record["message"] = f"{emoji} {record['message']}"
                # User emojis in message pass through unchanged
            else:
                # Filtered mode - only add CHARS-POLICY approved emojis
                emoji = LOG_LEVEL_EMOJIS.get(record["level"].name, "")
                if emoji:
                    record["message"] = f"{emoji} {record['message']}"
                # Note: We don't strip user emojis, but we don't add non-approved ones
        elif convert_to_text:
            # Convert any emojis in message to ASCII text
            record["message"] = emojis_to_text(record["message"])
        return True

    return filter_func


def _get_log_format(is_file: bool, color_scheme: str = "solarized") -> str:
    """Get log format string based on output type.

    Args:
        is_file: True if logging to file (ASCII-only), False for console
        color_scheme: Color scheme to use ("solarized" or "loguru")

    Returns:
        Format string for loguru
    """
    # File logging: Plain ASCII only (CHARS-POLICY.md requirement)
    if is_file:
        return "{time:YYYY-MM-DDTHH:mm:ss.SSSZZ} [{level: <8}] {name}:{function}:{line} - {message}"

    # Console logging with colors
    if color_scheme == "solarized":
        return (
            f"<fg {SOLARIZED['green']}>{{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}}</fg {SOLARIZED['green']}> | "
            f"<level>{{level: <8}}</level> | "
            f"<fg {SOLARIZED['cyan']}>{{name}}</fg {SOLARIZED['cyan']}>:"
            f"<fg {SOLARIZED['cyan']}>{{function}}</fg {SOLARIZED['cyan']}>:"
            f"<fg {SOLARIZED['cyan']}>{{line}}</fg {SOLARIZED['cyan']}> - "
            f"<level>{{message}}</level>"
        )
    else:
        return (
            "<green>{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )


def setup(settings=None, color_scheme="solarized", use_emojis=None, allow_all_emojis=False):
    """Setup standard logging with RFC 3339 compliance and CHARS-POLICY.md enforcement

    Args:
        settings: Optional settings dict (deprecated, use config instead)
        color_scheme: Color scheme to use - "solarized" (default) or "loguru"
        use_emojis: Emoji policy:
            - None (default): Auto-detect terminal Unicode support, use CHARS-POLICY approved emojis
            - True: Force permitted emojis on (CHARS-POLICY.md approved only)
            - False: No emojis (ASCII-only)
        allow_all_emojis: Allow all emojis without filtering (off by default, requires use_emojis=True)
            When True, user-provided emojis in log messages pass through unchanged.
            When False, only CHARS-POLICY.md approved emojis are added by logger.
    """

    # Remove default handler
    logger.remove()

    # Get logging config
    config = get_logging_config()

    # Auto-detect terminal type if not specified
    # Default: permitted emojis ONLY for interactive terminals
    # Non-interactive (Docker/K8s/daemon) = ASCII-only (CRITICAL for log aggregators)
    if use_emojis is None:
        use_emojis = _is_interactive_console()

    # If allow_all_emojis is True but use_emojis is False, warn and disable
    if allow_all_emojis and not use_emojis:
        allow_all_emojis = False  # Can't allow all if emojis disabled

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

    # Add console handler with RFC 3339 format and emoji support
    if config.get("console", True):
        console_format = _get_log_format(is_file=False, color_scheme=color_scheme)

        logger.add(
            sys.stderr,
            level=config.get("level", "INFO"),
            format=console_format,
            colorize=True,
            filter=_add_emoji_to_record(use_emojis, allow_all=allow_all_emojis),
        )

    # Add file handler if specified (ALWAYS ASCII-only per CHARS-POLICY.md)
    log_file = config.get("file")
    if log_file:
        file_format = _get_log_format(is_file=True, color_scheme=color_scheme)
        logger.add(
            log_file,
            level=config.get("level", "INFO"),
            format=file_format,
            rotation="10 MB",
            retention="7 days",
            filter=_add_emoji_to_record(
                False, convert_to_text=True, allow_all=False
            ),  # Convert emojis to text for machine-readable logs
        )

    return logger


# NOTE: get_logger() removed - just use 'from hyperlib.logger import logger' instead
# Loguru's logger is a singleton and uses module context for naming automatically

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
__all__ = [
    "logger",
    "setup",
    "info",
    "warning",
    "error",
    "success",
    "debug",
    "strip_emojis",
    "emojis_to_text",
    "LOG_LEVEL_EMOJIS",
    "EMOJI_TO_TEXT",
]
