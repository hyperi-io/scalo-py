"""
Structured logging with auto-configuration on import.

Auto-configured with production defaults:
- RFC 3339 timestamps
- Solarized colors (terminal) / ASCII-only (containers)
- Sensitive data masking
- stderr output, INFO level

Usage:
    from hyperi_pylib import logger
    logger.info("started")
    logger.error("failed", database="prod", retry=3)

ENV overrides:
    LOG_LEVEL=DEBUG
    LOG_FORMAT=json
    LOG_OUTPUT=stdout
    HYPERI_LIB_NO_LOGGER_CONFIG=1  # Disable auto-config

See docs/LOGGING.md for examples and configuration details.
"""

import os
import sys

from loguru import logger as _logger

from .filters import RateLimitFilter, get_sensitive_filter
from .scrub import Scrubber as _Scrubber
from .scrub_resolver import resolve_scrubber


def _get_logging_config():
    """Lazy import of get_logging_config to avoid circular dependency.

    The config module imports logger for debug logging, and logger imports
    config for get_logging_config. Using lazy import breaks the cycle.
    """
    from ..config import get_logging_config

    return get_logging_config()


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
    "WARNING": "⚠️ ",  # WARN - Non-blocking issue (extra space: variation selector eats one)
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
    for emoji in EMOJI_TO_TEXT:
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


def _is_ci_environment() -> bool:
    """Detect if running in a CI environment (GitHub Actions, GitLab CI, etc).

    Returns:
        True if running in a CI environment, False otherwise
    """
    return (
        os.getenv("CI") == "true"
        or os.getenv("GITHUB_ACTIONS") == "true"
        or os.getenv("GITLAB_CI") == "true"
        or os.getenv("JENKINS_URL") is not None
        or os.getenv("CIRCLECI") == "true"
        or os.getenv("TRAVIS") == "true"
    )


def _is_github_actions() -> bool:
    """Detect if running in GitHub Actions specifically.

    Returns:
        True if running in GitHub Actions, False otherwise
    """
    return os.getenv("GITHUB_ACTIONS") == "true"


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
    # CI environments are non-interactive
    if _is_ci_environment():
        return False

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

    return "UTF-8" in locale.upper() or "UTF8" in locale.upper()


# Map loguru level names (uppercase per loguru convention) to the
# attribute names on ScrubConfig.log_levels (lowercase per the spec).
_LEVEL_NAME_TO_GATE = {
    "TRACE": "trace",
    "DEBUG": "debug",
    "INFO": "info",
    "SUCCESS": "info",  # loguru's SUCCESS is INFO-grade
    "WARNING": "warn",
    "ERROR": "error",
    "CRITICAL": "error",  # critical maps to error gate
}


def _scrub_level_enabled(level_name: str, log_levels) -> bool:
    """Return True if scrubbing is enabled for this loguru level."""
    attr = _LEVEL_NAME_TO_GATE.get(level_name.upper(), "info")
    return bool(getattr(log_levels, attr, True))


def _add_emoji_to_record(
    use_emojis: bool,
    convert_to_text: bool = False,
    allow_all: bool = False,
    mask_sensitive: bool = True,
    masking_level: str = "simple",
    rate_limit_filter: RateLimitFilter | None = None,
    scrubber: _Scrubber | None = None,
):
    """Create a filter function that adds emojis or converts them to text.

    Args:
        use_emojis: Whether to add emojis to log records
        convert_to_text: Convert emojis to ASCII text (for machine-readable logs)
        allow_all: Allow all emojis without filtering (pass-through user emojis)
        mask_sensitive: Apply sensitive data masking (default: True)
        masking_level: legacy filter selector. ``"simple"`` uses the
            field-name regex; ``"advanced"`` / ``"advanced-ner"`` emit
            a deprecation warning and degrade to the field-name path
            because NLP/NER scrubbing has been dropped from scope.
            For PII-value detection use ``scrubber=`` with
            :func:`logger.scrub.build_scrubber`.
        rate_limit_filter: Optional RateLimitFilter instance for suppressing repeated messages
        scrubber: Optional :class:`Scrubber` instance to use instead of
            building one from ``mask_sensitive``/``masking_level``.
            When provided, takes precedence over the legacy args.
            Per spec §5.6, the scrubber's ``config.log_levels`` gate
            controls which log levels get scrubbed.

    Returns:
        Filter function for loguru
    """
    # Build a Scrubber. Either explicit (preferred) or legacy.
    if scrubber is None:
        sensitive_filter = get_sensitive_filter(level=masking_level) if mask_sensitive else None
        # Map loguru level names to ScrubConfig.log_levels attribute names.
        # Legacy path doesn't honour log-level gating (no log_levels
        # config in the legacy SensitiveDataFilter).
        log_levels = None
    else:
        sensitive_filter = None
        # Pull log-level gate from the scrubber's config if it's a
        # LayeredScrubber; otherwise default to all-on.
        log_levels = getattr(getattr(scrubber, "config", None), "log_levels", None)

    def _scrub_str(text: str, level_name: str) -> str:
        """Run the active scrubbing path against a single string."""
        if scrubber is not None:
            if log_levels is None or _scrub_level_enabled(level_name, log_levels):
                return scrubber.scrub(text)
            return text
        if sensitive_filter is not None:
            return sensitive_filter._mask_sensitive_string(text)
        return text

    def _scrub_extra(extra: dict, level_name: str) -> None:
        """Mutate loguru ``record['extra']`` (logger.bind() context) in place."""
        if sensitive_filter is not None:
            masked = sensitive_filter._mask_sensitive_dict(extra)
            extra.clear()
            extra.update(masked)
            return
        if scrubber is not None and (log_levels is None or _scrub_level_enabled(level_name, log_levels)):
            for k, v in list(extra.items()):
                if isinstance(v, str):
                    extra[k] = scrubber.scrub(v)

    def _scrub_exception_chain(exc: BaseException | None, level_name: str) -> None:
        """Walk exc chain via __cause__/__context__ and scrub string args in place."""
        seen: set[int] = set()
        current = exc
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if current.args:
                current.args = tuple(_scrub_str(a, level_name) if isinstance(a, str) else a for a in current.args)
            current = current.__cause__ or current.__context__

    def filter_func(record):
        """Add emoji to record or convert emojis to text based on settings."""
        # Apply rate limiting first (before any message modification)
        # This ensures the rate limit key uses the original message
        if rate_limit_filter is not None and not rate_limit_filter(record):
            return False  # Suppress this message

        level_name = record["level"].name

        # Apply scrubbing. New path: use Scrubber if provided.
        # Legacy path: fall back to SensitiveDataFilter._mask_sensitive_string.
        if isinstance(record["message"], str):
            record["message"] = _scrub_str(record["message"], level_name)

        # Scrub bind() context dict (logger.bind(api_key=...))
        if record.get("extra"):
            _scrub_extra(record["extra"], level_name)

        # Scrub exception chain args (traceback values logged via logger.exception)
        exc_info = record.get("exception")
        if exc_info is not None and getattr(exc_info, "value", None) is not None:
            _scrub_exception_chain(exc_info.value, level_name)

        # Then handle emojis
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


def _github_actions_sink(message):
    """Sink that outputs GitHub Actions workflow commands for log messages.

    Maps log levels to GitHub Actions commands:
    - DEBUG -> ::debug::
    - INFO/SUCCESS -> plain output
    - WARNING -> ::warning::
    - ERROR/CRITICAL -> ::error::

    See: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions
    """
    record = message.record
    level = record["level"].name
    text = str(message).strip()

    # Map log levels to GitHub Actions commands
    if level == "DEBUG":
        print(f"::debug::{text}", file=sys.stderr)
    elif level == "WARNING":
        print(f"::warning::{text}", file=sys.stderr)
    elif level in ("ERROR", "CRITICAL"):
        # Include file/line info if available for annotations
        file_info = ""
        if record.get("file"):
            file_info = f"file={record['file'].path}"
            if record.get("line"):
                file_info += f",line={record['line']}"
        if file_info:
            print(f"::error {file_info}::{text}", file=sys.stderr)
        else:
            print(f"::error::{text}", file=sys.stderr)
    else:
        # INFO, SUCCESS, TRACE - plain output
        print(text, file=sys.stderr)


def _get_log_format(is_file: bool, color_scheme: str = "solarized", ci_mode: bool = False) -> str:
    """Get log format string based on output type.

    Args:
        is_file: True if logging to file (ASCII-only), False for console
        color_scheme: Color scheme to use ("solarized" or "loguru")
        ci_mode: True to use CI-compatible format (no colors, simple prefix)

    Returns:
        Format string for loguru
    """
    # File logging: Plain ASCII only (CHARS-POLICY.md requirement)
    if is_file:
        return "{time:YYYY-MM-DDTHH:mm:ss.SSSZZ} [{level: <8}] {name}:{function}:{line} - {message}"

    # CI mode: Simple format without ANSI colors for GitHub Actions/GitLab CI
    # Uses prefix format that integrates with CI log parsing
    if ci_mode:
        return "[{level: <8}] {name}:{function}:{line} - {message}"

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


def setup(
    settings=None,
    color_scheme="solarized",
    use_emojis=None,
    allow_all_emojis=False,
    mask_sensitive=None,
    masking_level=None,
    rate_limit_sec=None,
    rate_limit_similar=False,
    ci_mode=None,
    scrubber=None,
    scrub_config=None,
):
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
        mask_sensitive: Mask sensitive data in logs (default: True)
            - None (default): Read from config (logging.mask_sensitive_data)
            - True: Enable masking of passwords, tokens, API keys, etc.
            - False: Disable masking (NOT recommended for production)
        masking_level: legacy selector for the field-name filter
            - None (default): Read from config (logging.masking_level)
            - "simple": Fast regex on field names (this is the only
              path; ships in core)
            - "advanced" / "advanced-ner": deprecated. NLP/NER
              scrubbing was dropped from scope. These selectors emit
              a one-shot deprecation warning and degrade to ``"simple"``.

            For PII-value detection (emails, phones, credit cards,
            national IDs) use the ``scrubber=`` argument with a
            :class:`Scrubber` from
            :func:`hyperi_pylib.logger.scrub.build_scrubber`.
        rate_limit_sec: Rate limit period in seconds for repeated messages
            - None (default): No rate limiting (read from config: logging.rate_limit_sec)
            - 0: Disable rate limiting
            - 30: Suppress identical messages within 30 seconds (recommended)
        rate_limit_similar: Normalise numbers/UUIDs/IPs for similar message matching
            - False (default): Only suppress exact duplicate messages
            - True: Treat messages differing only in numbers/IDs as similar
              e.g., "Failed order 123" and "Failed order 456" are grouped together
        ci_mode: CI mode for GitHub Actions / GitLab CI compatible output
            - None (default): Auto-detect from environment (GITHUB_ACTIONS, CI, etc.)
            - True: Force CI mode - use workflow commands (::error::, ::warning::, etc.)
            - False: Force normal mode - standard console output
    """

    # Remove default handler
    logger.remove()

    # Get logging config (lazy import to avoid circular dependency)
    config = _get_logging_config()

    # Fire-and-forget mode by default -- sinks run on a background thread, so
    # logger.info() returns in ~us even with slow disk/network sinks. Override
    # with HYPERI_LOG_ENQUEUE=0 for sync semantics (audit logging, unit tests
    # that assert on captured output, etc.).
    enqueue = os.environ.get("HYPERI_LOG_ENQUEUE", "1") != "0"

    # LOG_FORMAT: explicit selector for the console sink format.
    # Accepted values: "json" (one JSON object per line via loguru
    # serialize=True), "console" / "text" / "" (default human-readable
    # console with colours in TTY, plain ASCII in files / CI). The env
    # var beats the config value beats the auto-detected default.
    log_format = (os.environ.get("LOG_FORMAT") or config.get("format") or "").strip().lower()
    serialize_console = log_format == "json"

    # CI mode: Auto-detect from environment or config, can be overridden by parameter
    # Priority: parameter > config > auto-detect
    if ci_mode is None:
        ci_mode = config.get("ci_mode")  # Check config first
    if ci_mode is None:
        ci_mode = _is_ci_environment()  # Auto-detect from environment

    # Use GitHub Actions workflow commands if in GitHub Actions
    use_github_actions_commands = ci_mode and _is_github_actions()

    # Auto-detect terminal type if not specified
    # Default: permitted emojis ONLY for interactive terminals
    # Non-interactive (Docker/K8s/daemon) = ASCII-only (CRITICAL for log aggregators)
    # CI mode = ASCII-only (no emojis)
    if use_emojis is None:
        use_emojis = not ci_mode and _is_interactive_console()

    # If allow_all_emojis is True but use_emojis is False, warn and disable
    if allow_all_emojis and not use_emojis:
        allow_all_emojis = False  # Can't allow all if emojis disabled

    # Build a Scrubber per spec §2.3. The resolver honours (in order):
    # explicit `scrubber=` arg -> explicit `scrub_config=` arg -> legacy
    # `mask_sensitive` / `masking_level` args -> new `logging.scrub.*`
    # config keys -> legacy `logging.mask_sensitive_data` /
    # `logging.masking_level` config keys (with deprecation warning) ->
    # defaults. See logger/scrub_resolver.py.
    resolved_scrubber = resolve_scrubber(
        scrubber=scrubber,
        scrub_config=scrub_config,
        mask_sensitive=mask_sensitive,
        masking_level=masking_level,
        config_dict=config,
    )

    # Sensitive data masking (default: enabled). Retained for backwards
    # compatibility -- _add_emoji_to_record will prefer `resolved_scrubber`
    # but we keep these flags wired to honour the legacy call signature.
    if mask_sensitive is None:
        mask_sensitive = config.get("mask_sensitive_data", True)
    if masking_level is None:
        masking_level = config.get("masking_level", "advanced-ner")

    # Rate limiting (default: disabled)
    # Read from config if not explicitly set
    if rate_limit_sec is None:
        rate_limit_sec = config.get("rate_limit_sec", 0)

    # Create rate limit filter if enabled (shared across all handlers)
    rate_limit_filter = None
    if rate_limit_sec and rate_limit_sec > 0:
        rate_limit_filter = RateLimitFilter(
            period_sec=rate_limit_sec,
            normalise_numbers=rate_limit_similar,
        )

    # Configure color scheme (skip if CI mode - no colors)
    if not ci_mode and color_scheme == "solarized":
        # Solarized color scheme for log levels
        logger.level("TRACE", color=f"<fg {SOLARIZED['base01']}>")  # base01 - gray
        logger.level("DEBUG", color=f"<fg {SOLARIZED['base01']}>")  # base01 - gray
        logger.level("INFO", color=f"<fg {SOLARIZED['blue']}>")  # blue - primary accent
        logger.level("SUCCESS", color=f"<fg {SOLARIZED['green']}>")  # green - success
        logger.level("WARNING", color=f"<fg {SOLARIZED['yellow']}>")  # yellow - attention
        logger.level("ERROR", color=f"<fg {SOLARIZED['orange']}>")  # orange - error
        logger.level("CRITICAL", color=f"<fg {SOLARIZED['red']}>")  # red - critical

    # Add console handler
    if config.get("console", True):
        if use_github_actions_commands:
            # GitHub Actions: Use custom sink for workflow commands (::error::, ::warning::, etc.)
            console_format = _get_log_format(is_file=False, ci_mode=True)
            logger.add(
                _github_actions_sink,
                level=config.get("level", "INFO"),
                format=console_format,
                colorize=False,
                enqueue=enqueue,
                filter=_add_emoji_to_record(
                    False,  # No emojis in CI
                    convert_to_text=True,
                    allow_all=False,
                    mask_sensitive=mask_sensitive,
                    masking_level=masking_level,
                    rate_limit_filter=rate_limit_filter,
                    scrubber=resolved_scrubber,
                ),
            )
        elif ci_mode:
            # Other CI (GitLab, Jenkins, etc.): Simple format without colors
            console_format = _get_log_format(is_file=False, ci_mode=True)
            logger.add(
                sys.stderr,
                level=config.get("level", "INFO"),
                format=console_format,
                colorize=False,
                serialize=serialize_console,
                enqueue=enqueue,
                filter=_add_emoji_to_record(
                    False,  # No emojis in CI
                    convert_to_text=True,
                    allow_all=False,
                    mask_sensitive=mask_sensitive,
                    masking_level=masking_level,
                    rate_limit_filter=rate_limit_filter,
                    scrubber=resolved_scrubber,
                ),
            )
        else:
            # Normal console: Colors and optional emojis (or JSON when LOG_FORMAT=json)
            console_format = _get_log_format(is_file=False, color_scheme=color_scheme)
            logger.add(
                sys.stderr,
                level=config.get("level", "INFO"),
                format=console_format,
                colorize=not serialize_console,
                serialize=serialize_console,
                enqueue=enqueue,
                filter=_add_emoji_to_record(
                    use_emojis,
                    allow_all=allow_all_emojis,
                    mask_sensitive=mask_sensitive,
                    masking_level=masking_level,
                    rate_limit_filter=rate_limit_filter,
                    scrubber=resolved_scrubber,
                ),
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
            encoding="utf-8",
            enqueue=enqueue,
            filter=_add_emoji_to_record(
                False,
                convert_to_text=True,
                allow_all=False,
                mask_sensitive=mask_sensitive,
                masking_level=masking_level,
                rate_limit_filter=rate_limit_filter,
                scrubber=resolved_scrubber,
            ),  # Convert emojis to text for machine-readable logs
        )

    return logger


# NOTE: get_logger() removed - just use 'from hyperi_pylib.logger import logger' instead
# Loguru's logger is a singleton and uses module context for naming automatically

# ============================================================================
# Smart Auto-Configuration (Zero-Config Pattern)
# ============================================================================
# Only auto-configure if explicitly requested.
# Opt-in: set HYPERI_LIB_AUTO_LOGGER_CONFIG=1 (keeps HYPERI_LIB_NO_LOGGER_CONFIG as override)


def _env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes")


if _env_flag("HYPERI_LIB_AUTO_LOGGER_CONFIG") and not _env_flag("HYPERI_LIB_NO_LOGGER_CONFIG"):
    # Initialize with smart defaults (auto-detects terminal, RFC 3339, emojis)
    setup()


# Standard logging functions for convenience
def info(msg, **kwargs):
    logger.info(msg, **kwargs)


def warning(msg, **kwargs):
    logger.warning(msg, **kwargs)


def error(msg, **kwargs):
    logger.error(msg, **kwargs)


def success(msg, **kwargs):
    logger.success(msg, **kwargs)


def debug(msg, **kwargs):
    logger.debug(msg, **kwargs)


def log(msg: str, color: str | None = None, level: str = "INFO"):
    level = level.upper()
    if color:
        hex_color = SOLARIZED.get(color, color)
        colored_msg = f"<fg {hex_color}>{msg}</fg {hex_color}>"
        logger.opt(colors=True).log(level, colored_msg)
    else:
        logger.log(level, msg)


# Export for direct usage
__all__ = [
    "EMOJI_TO_TEXT",
    "LOG_LEVEL_EMOJIS",
    "RateLimitFilter",
    "debug",
    "emojis_to_text",
    "error",
    "info",
    "log",
    "logger",
    "setup",
    "strip_emojis",
    "success",
    "warning",
]
