"""Structured logging with auto-configuration on import.

Auto-configured with production defaults:
- RFC 3339 timestamps
- JSON lines when stderr is not a TTY, human-readable text when it is
- Keyword fields rendered in every format (``key=value`` in text)
- Colour only on a TTY unless configured otherwise
- Sensitive data masking
- stderr output, INFO level

Usage:
    from scalo import logger
    logger.info("started")
    logger.error("failed", database="prod", retry=3)

ENV overrides:
    LOG_LEVEL=DEBUG
    LOG_FORMAT=json     # json, text, auto
    LOG_COLOR=false     # also NO_COLOR=1
    NO_LOGGER_CONFIG=1  # Disable auto-config

See docs/core-pillars/LOGGING.md for examples and configuration details.
"""

import contextlib
import inspect
import json
import logging
import math
import os
import sys
import traceback
from collections.abc import Callable
from datetime import UTC

from loguru import logger as _logger

from scalo._env_compat import control_flag, control_var

from .filters import MASK_VALUE, SENSITIVE_FIELDS, RateLimitFilter, SensitiveDataFilter, get_sensitive_filter
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
    if not _stream_is_tty(sys.stderr):
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


class _Fields(dict):
    """A record's keyword fields, as loguru's ``record["extra"]`` once the scrub filter has run.

    Its items are the scrubbed fields as JSON-native data, so every reader sees
    plain data and an enqueued record pickles whatever the caller passed. The
    text formats render it with the ``{extra:fields}`` and ``{extra:exception}``
    format specs.

    Attributes:
        exception_text: The record's traceback, formatted and scrubbed; empty when none was logged.
        scrubbed_by: Identity of the scrubber that produced it, so a second sink skips the work.
    """

    __slots__ = ("exception_text", "scrubbed_by")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.exception_text = ""
        self.scrubbed_by = 0

    def __format__(self, spec: str) -> str:
        if spec == "fields":
            return _render_fields(self)
        if spec == "exception":
            text = getattr(self, "exception_text", "")
            return f"\n{text}" if text else ""
        return super().__format__(spec)


# Containers nested deeper than this inside a field render as a placeholder.
_MAX_FIELD_DEPTH = 32

# Strings a record scrubs inside its field containers; each costs ~0.15 ms on the caller's thread.
_FIELD_SCRUB_BUDGET = 64

_ELIDED = "<elided>"

# Field names one filter remembers scrubbed results for before it starts over.
_KEY_CACHE_SIZE = 4096

# JSON leaves C1 controls and U+2028/U+2029 raw under ensure_ascii=False, and line splitters break on them.
_LINE_BREAK_ESCAPES = str.maketrans({code: f"\\u{code:04x}" for code in (*range(0x80, 0xA0), 0x2028, 0x2029)})


def _unprintable(value) -> str:
    """Return the placeholder for a value that could not be rendered."""
    return f"<unprintable {type(value).__name__}>"


def _finite(value: float) -> float | str:
    """Return ``value``, or its name as a string when it is NaN or infinite, which strict JSON parsers reject."""
    if math.isfinite(value):
        return value
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


class _FieldWalker:
    """Convert one record's fields to scrubbed JSON-native data, never raising.

    A sensitive key, or the name in a ``(name, value)`` pair, masks its value.
    Keys and strings are scrubbed, any other object is rendered with ``str()``
    and scrubbed, and a non-finite float becomes a string. Inside containers,
    a cycle, nesting past :data:`_MAX_FIELD_DEPTH` and anything past the
    :data:`_FIELD_SCRUB_BUDGET` render as placeholders; top-level fields are
    never elided.
    """

    __slots__ = ("_budget", "_path", "_scrub", "_scrub_key", "_sensitive")

    def __init__(self, scrub: Callable[[str], str], scrub_key: Callable[[str], str], sensitive: set[str]) -> None:
        self._scrub = scrub
        self._scrub_key = scrub_key
        self._sensitive = sensitive
        self._budget = _FIELD_SCRUB_BUDGET
        self._path: set[int] = set()

    def fields(self, extra: dict) -> dict:
        """Return the scrubbed copy of a record's top-level fields."""
        output = {}
        for key, value in extra.items():
            name, sensitive = self._key(key, nested=False)
            output[name] = MASK_VALUE if sensitive else self._value(value, 0)
        return output

    def _charge(self, nested: bool) -> bool:
        """Charge one string to the budget when it sits inside a container; False once it is spent."""
        if not nested:
            return True
        if self._budget <= 0:
            return False
        self._budget -= 1
        return True

    def _text(self, text: str, nested: bool) -> str:
        """Scrub one string value."""
        return self._scrub(text) if self._charge(nested) else _ELIDED

    def _key(self, key, *, nested: bool) -> tuple[str, bool]:
        """Return a key's scrubbed text and whether it names a sensitive field."""
        try:
            raw = key if isinstance(key, str) else str(key)
        except Exception:
            return _unprintable(key), False
        sensitive = raw.lower() in self._sensitive
        try:
            return (self._scrub_key(raw) if self._charge(nested) else _ELIDED), sensitive
        except Exception:
            return _unprintable(key), sensitive

    def _value(self, value, depth: int):
        """Return one value as scrubbed JSON-native data, or a placeholder when it cannot be rendered."""
        try:
            if value is None or isinstance(value, (bool, int)):
                return value
            if isinstance(value, float):
                return _finite(value)
            if isinstance(value, str):
                return self._text(value, depth > 0)
            if isinstance(value, (dict, list, tuple)):
                return self._container(value, depth)
            return self._text(str(value), depth > 0)
        except Exception:
            return _unprintable(value)

    def _container(self, value: dict | list | tuple, depth: int) -> dict | list | str:
        if depth >= _MAX_FIELD_DEPTH:
            return "<depth limit>"
        marker = id(value)
        if marker in self._path:
            return "<cycle>"
        self._path.add(marker)
        try:
            if isinstance(value, dict):
                return self._mapping(value, depth + 1)
            return self._sequence(value, depth + 1)
        finally:
            self._path.discard(marker)

    def _mapping(self, value: dict, depth: int) -> dict:
        output = {}
        for index, (key, item) in enumerate(value.items()):
            if self._budget <= 0:
                output[_ELIDED] = f"{len(value) - index} more entries"
                break
            name, sensitive = self._key(key, nested=True)
            output[name] = MASK_VALUE if sensitive else self._value(item, depth)
        return output

    def _sequence(self, value: list | tuple, depth: int) -> list:
        if len(value) == 2 and self._names_a_secret(value[0]):
            return [self._value(value[0], depth), MASK_VALUE]
        output = []
        for index, item in enumerate(value):
            if self._budget <= 0:
                output.append(f"<elided: {len(value) - index} more items>")
                break
            output.append(self._value(item, depth))
        return output

    def _names_a_secret(self, item) -> bool:
        """Return True when ``item`` is a sensitive name, as in an ``(authorization, value)`` header pair."""
        if isinstance(item, bytes):
            item = item.decode("latin-1")
        return isinstance(item, str) and item.lower() in self._sensitive


def _render_exception(exception) -> str:
    """Format a loguru record's exception as the stdlib prints it, without the trailing newline."""
    exc_type, value, tb = exception
    return "".join(traceback.format_exception(exc_type, value, tb)).rstrip("\n")


def _render_field_value(value) -> str:
    """Render one field key or value for a text line, quoting it when it would not parse back."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    # A space, `=` or `"` would split the pair; a control or separator character would break the line.
    if not text or not text.isprintable() or any(char in ' ="' for char in text):
        return json.dumps(text, ensure_ascii=False).translate(_LINE_BREAK_ESCAPES)
    return text


def _render_fields(fields: dict) -> str:
    """Render fields as `` key=value`` pairs, each with a leading space; empty renders nothing."""
    return "".join(f" {_render_field_value(key)}={_render_field_value(value)}" for key, value in fields.items())


def _utc_rfc3339(moment) -> str:
    """Format an aware datetime as RFC 3339 UTC with microseconds and a ``Z`` suffix."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_line(record) -> str:
    """Render one record as a flat JSON object followed by a newline.

    Keys: ``timestamp``, ``level``, ``target`` (the logger name), ``function``,
    ``line_number``, ``message`` and ``fields`` (an object, empty when the
    record has none), plus ``exception`` when a traceback was logged.
    """
    extra = record["extra"]
    entry = {
        "timestamp": _utc_rfc3339(record["time"]),
        "level": record["level"].name,
        "target": record["name"],
        "function": record["function"],
        "line_number": record["line"],
        "message": record["message"],
        "fields": extra,
    }
    exception_text = getattr(extra, "exception_text", "")
    if exception_text:
        entry["exception"] = exception_text
    return json.dumps(entry, default=str, ensure_ascii=False).translate(_LINE_BREAK_ESCAPES) + "\n"


def _fixed_format(template: str) -> Callable[[dict], str]:
    """Return a loguru format callable for ``template``.

    loguru appends its own ``{exception}``, rendered from the live exception and
    never scrubbed, to a format given as a string, and appends nothing to a
    callable, so every scalo sink formats through one.
    """

    def format_record(_record: dict) -> str:
        return template

    return format_record


class _JsonSink:
    """Stream sink writing one :func:`_json_line` per record.

    The filter has already formatted and scrubbed the traceback onto the
    record's fields, so the handler's own format text is empty and unused.
    """

    def __init__(self, stream) -> None:
        self._stream = stream

    def write(self, message) -> None:
        """Write the record carried by ``message`` as one JSON line."""
        self._stream.write(_json_line(message.record))

    def flush(self) -> None:
        """Flush the underlying stream."""
        self._stream.flush()


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
            Per spec Section 5.6, the scrubber's ``config.log_levels`` gate
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

    def _scrub_exception_chain(exc: BaseException | None, level_name: str) -> None:
        """Scrub the string args of ``exc``, its causes, contexts and group members, in place."""
        seen: set[int] = set()
        pending = [exc]
        while pending:
            current = pending.pop()
            if current is None or id(current) in seen:
                continue
            seen.add(id(current))
            # A type with read-only args keeps them; the rendered traceback is scrubbed regardless.
            with contextlib.suppress(AttributeError, TypeError):
                current.args = tuple(_scrub_str(a, level_name) if isinstance(a, str) else a for a in current.args)
            pending.extend((current.__cause__, current.__context__))
            if isinstance(current, BaseExceptionGroup):
                pending.extend(current.exceptions)

    def _scrubbed_traceback(exception, level_name: str) -> str:
        """Return the record's traceback formatted and scrubbed, or a placeholder if that fails."""
        try:
            _scrub_exception_chain(exception.value, level_name)
            return _scrub_str(_render_exception(exception), level_name)
        except Exception as exc:
            return f"<traceback not logged: {type(exc).__name__} while rendering it>"

    # Every sink setup() adds shares one scrubber, so the first sink's filter does the work for all.
    scrubbed_by = id(scrubber if scrubber is not None else sensitive_filter)

    # Field names repeat from call to call; a cached result holds only while the sensitive-name set is unchanged.
    key_cache: dict[tuple[str, str], str] = {}
    key_cache_names: set[str] = set()

    def _scrub_key(text: str, level_name: str, sensitive_keys: set[str]) -> str:
        """Scrub a field name, reusing the result for a name already seen."""
        if sensitive_keys != key_cache_names or len(key_cache) >= _KEY_CACHE_SIZE:
            key_cache.clear()
            key_cache_names.clear()
            key_cache_names.update(sensitive_keys)
        cached = key_cache.get((text, level_name))
        if cached is None:
            cached = _scrub_str(text, level_name)
            key_cache[(text, level_name)] = cached
        return cached

    def _scrub_record(record) -> None:
        """Scrub the message, traceback and fields, swapping ``extra`` for a :class:`_Fields`.

        Key-based redaction runs whatever the backend and log-level gate; value
        scrubbing follows the gate. A part that cannot be scrubbed is replaced
        by a placeholder, because a filter that raises makes loguru print the
        raw record to stderr.
        """
        extra = record["extra"]
        if isinstance(extra, _Fields) and getattr(extra, "scrubbed_by", 0) == scrubbed_by:
            return

        level_name = record["level"].name
        try:
            record["message"] = _scrub_str(record["message"], level_name)
        except Exception as exc:
            record["message"] = f"<message not logged: {type(exc).__name__} while scrubbing it>"

        fields = _Fields()
        if record["exception"] is not None:
            fields.exception_text = _scrubbed_traceback(record["exception"], level_name)
        try:
            sensitive_keys = SENSITIVE_FIELDS | SensitiveDataFilter._custom_fields
            walker = _FieldWalker(
                lambda text: _scrub_str(text, level_name),
                lambda text: _scrub_key(text, level_name, sensitive_keys),
                sensitive_keys,
            )
            fields.update(walker.fields(extra))
        except Exception as exc:
            fields.clear()
            fields["<fields not logged>"] = type(exc).__name__
        fields.scrubbed_by = scrubbed_by
        record["extra"] = fields

    def filter_func(record):
        """Scrub the record, then add emoji to it or convert emojis to text."""
        # Rate limiting keys on the message as the caller wrote it.
        if rate_limit_filter is not None and not rate_limit_filter(record):
            return False

        _scrub_record(record)

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


def _get_log_format(is_file: bool, color_scheme: str = "solarized", ci_mode: bool = False) -> Callable[[dict], str]:
    """Get the loguru format for a text sink.

    Every format ends with the record's keyword fields as `` key=value`` pairs,
    then its scrubbed traceback on the following lines. The record must have
    passed :func:`_add_emoji_to_record`, which supplies both through the
    ``{extra:fields}`` and ``{extra:exception}`` format specs.

    Args:
        is_file: True if logging to file (ASCII-only), False for console
        color_scheme: Color scheme to use ("solarized" or "loguru")
        ci_mode: True to use CI-compatible format (no colors, simple prefix)

    Returns:
        Format callable for loguru
    """
    tail = "{extra:fields}{extra:exception}\n"

    # File logging: Plain ASCII only (CHARS-POLICY.md requirement)
    if is_file:
        return _fixed_format(
            "{time:YYYY-MM-DDTHH:mm:ss.SSSZZ} [{level: <8}] {name}:{function}:{line} - {message}" + tail
        )

    # CI mode: Simple format without ANSI colors for GitHub Actions/GitLab CI
    # Uses prefix format that integrates with CI log parsing
    if ci_mode:
        return _fixed_format("[{level: <8}] {name}:{function}:{line} - {message}" + tail)

    # Console logging with colors
    if color_scheme == "solarized":
        return _fixed_format(
            f"<fg {SOLARIZED['green']}>{{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}}</fg {SOLARIZED['green']}> | "
            f"<level>{{level: <8}}</level> | "
            f"<fg {SOLARIZED['cyan']}>{{name}}</fg {SOLARIZED['cyan']}>:"
            f"<fg {SOLARIZED['cyan']}>{{function}}</fg {SOLARIZED['cyan']}>:"
            f"<fg {SOLARIZED['cyan']}>{{line}}</fg {SOLARIZED['cyan']}> - "
            f"<level>{{message}}</level>" + tail
        )
    return _fixed_format(
        "<green>{time:YYYY-MM-DDTHH:mm:ss.SSSZZ}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>" + tail
    )


# AWS SDK and HTTP client loggers. At DEBUG botocore writes request params and
# response bodies, a Secrets Manager SecretString included; at INFO httpx writes
# every request URL whole, so a presigned URL's signature goes out with it.
_CAPPED_LIBRARY_LOGGERS = ("boto3", "botocore", "s3transfer", "urllib3", "httpx", "httpcore")


def _cap_library_loggers() -> None:
    """Raise each capped library logger to WARNING; never lower one."""
    for name in _CAPPED_LIBRARY_LOGGERS:
        library_logger = logging.getLogger(name)
        if library_logger.level < logging.WARNING:
            library_logger.setLevel(logging.WARNING)


# Loggers that attach a handler of their own, which writes each record unscrubbed; uvicorn's also stop propagating.
_SELF_HANDLING_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "detect-secrets")

# Attributes every LogRecord carries; anything else on a record came from the caller's ``extra=``.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}

# uvicorn's ``color_message`` repeats the message with ANSI escapes and its ``%`` arguments unformatted.
_DROPPED_RECORD_ATTRS = _STANDARD_RECORD_ATTRS | {"color_message"}


class _InterceptHandler(logging.Handler):
    """Stdlib logging handler that re-emits each record through loguru.

    The record keeps its level, call site, traceback and ``extra=`` fields, so
    it reaches the same sinks, format and scrubbing as a direct loguru call.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Re-emit ``record`` through loguru."""
        try:
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Step out of the logging package so the reported call site is the caller's.
            frame, depth = inspect.currentframe(), 0
            while frame is not None:
                filename = frame.f_code.co_filename
                is_frozen_import = "importlib" in filename and "_bootstrap" in filename
                if depth > 0 and filename != logging.__file__ and not is_frozen_import:
                    break
                frame = frame.f_back
                depth += 1

            message = record.getMessage()
            if record.stack_info:
                message = f"{message}\n{record.stack_info}"
            has_exception = bool(record.exc_info) and record.exc_info[0] is not None
            fields = {key: value for key, value in record.__dict__.items() if key not in _DROPPED_RECORD_ATTRS}
            logger.bind(**fields).opt(depth=depth, exception=record.exc_info if has_exception else None).log(
                level, message
            )
        except Exception:
            self.handleError(record)


def _route_stdlib_logging(enabled: bool, level) -> None:
    """Make the root logger's only handler an :class:`_InterceptHandler`, or remove it.

    Replacing the root handlers, and emptying the self-handling loggers, keeps
    each record from being written twice: once by a stdlib handler, once by loguru.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if enabled or isinstance(handler, _InterceptHandler):
            root.removeHandler(handler)
    if not enabled:
        return

    root.addHandler(_InterceptHandler())
    if isinstance(level, int):
        root.setLevel(level)
    else:
        try:
            root.setLevel(logger.level(str(level).upper()).no)
        except ValueError:
            root.setLevel(logging.NOTSET)
    for name in _SELF_HANDLING_LOGGERS:
        library_logger = logging.getLogger(name)
        library_logger.handlers.clear()
        library_logger.propagate = True


# LOG_FORMAT values: ``pretty`` and ``human`` match scalo-rs's parser, ``console`` is scalo-py only.
_LOG_FORMATS = {
    "": "auto",
    "auto": "auto",
    "json": "json",
    "text": "text",
    "console": "text",
    "pretty": "text",
    "human": "text",
}


def _stream_is_tty(stream) -> bool:
    """Return True if ``stream`` reports itself as a terminal."""
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except ValueError:
        # A closed stream raises rather than answering.
        return False


def _format_candidates(log_format, config) -> tuple:
    """Return the format selectors in precedence order: caller, ``LOG_FORMAT``, config."""
    return (log_format, os.environ.get("LOG_FORMAT"), config.get("format"))


def _resolve_console_format(log_format, config, *, is_tty: bool, ci_mode: bool) -> str:
    """Resolve the console sink format to ``"json"`` or ``"text"``.

    The first concrete selector wins: caller, then ``LOG_FORMAT``, then config.
    ``auto``, blank and unrecognised selectors defer to the next one. With none
    concrete, a set ``OTEL_EXPORTER_OTLP_ENDPOINT`` gives json, a CI run gives
    text, and otherwise a TTY gets text and anything else json.

    Args:
        log_format: Caller-resolved selector, or None.
        config: Logging config dict; its ``format`` key is read.
        is_tty: Whether the console stream is a terminal.
        ci_mode: Whether CI output mode is active.

    Returns:
        ``"json"`` or ``"text"``.
    """
    for candidate in _format_candidates(log_format, config):
        resolved = _LOG_FORMATS.get(str(candidate or "").strip().lower())
        if resolved in ("json", "text"):
            return resolved
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return "json"
    if ci_mode:
        return "text"
    return "text" if is_tty else "json"


def _unrecognised_format(log_format, config) -> str | None:
    """Return the first unrecognised format selector consulted before a concrete one won, if any."""
    for candidate in _format_candidates(log_format, config):
        resolved = _LOG_FORMATS.get(str(candidate or "").strip().lower())
        if resolved is None:
            return candidate
        if resolved != "auto":
            return None
    return None


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
    metrics=None,
    level=None,
    log_format=None,
    otel_tracing=True,
    service_name=None,
    intercept_stdlib=None,
):
    """Set up standard logging with RFC 3339 compliance and CHARS-POLICY.md enforcement.

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
            :func:`scalo.logger.scrub.build_scrubber`.
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
        scrubber: A ready-built :class:`Scrubber`; outranks every other scrub
            argument and config key.
        scrub_config: A :class:`ScrubConfig` to build the scrubber from;
            outranks ``mask_sensitive``, ``masking_level`` and config.
        metrics: Optional ``MetricsManager`` for the scrub layers.
            - None (default): scrub metrics stay no-op
            - A manager: the scrub layers emit the metrics named in the
              parity manifest (matches, redactions, errors, skipped,
              duration, pattern version)

            The scrub config carries ``metrics_enabled`` and
            ``metrics_type_cardinality_cap``, but nothing could honour them
            until there was a way to hand a manager in::

                from scalo.metrics import create_metrics
                metrics = create_metrics("my-app")
                logger.setup(metrics=metrics)
        level: Explicit log level, already resolved by the caller.
            ``get_logging_config()`` reads the process-wide Dynaconf instance,
            which never sees a config file passed to
            ``get_config(additional_files=...)``. A caller that HAS loaded such
            a file -- ``ServiceApp``, via ``--config`` -- passes the resolved
            level here instead of hoping the two agree.
        log_format: Format selector resolved by the caller: "json", "text"
            (aliases "console", "pretty", "human") or "auto". Same reasoning
            as ``level``. "auto" or None defers to ``LOG_FORMAT``, then to
            ``logging.format``; with none concrete, the console logs JSON
            when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, text in CI, text on
            a TTY and JSON otherwise. An unrecognised value is treated as
            "auto" and reported with a warning once the sinks are up.
        otel_tracing: Compose OTLP span export in (default True), so an app that
            calls this and nothing else gets distributed tracing -- matching
            scalo-rs, which wires spans at logger setup. Set False for a context
            that must not start an exporter thread. Switching it off in config
            (``otel_tracing.enabled: false`` or a blank endpoint) is the normal
            way to opt out; this argument is for callers that cannot reach it.
        service_name: ``service.name`` for the span resource. Without it the
            attribute is left unset rather than defaulted, because a package-name
            default would report every service in the fleet as "scalo".
        intercept_stdlib: Route stdlib ``logging`` records through these sinks.
            - None (default): Read from config (``logging.intercept_stdlib``,
              default True)
            - True: The root logger's handlers are replaced by one that
              re-emits through loguru, the root level follows ``level``, and
              the ``uvicorn`` and ``detect-secrets`` loggers lose their own
              handlers and propagate.
              Each stdlib record then gets the same format, ``extra=`` fields
              and scrubbing as a loguru call.
            - False: stdlib logging is left alone, and a handler a previous
              call installed is removed.

    The stdlib ``boto3``, ``botocore``, ``s3transfer``, ``urllib3``, ``httpx``
    and ``httpcore`` loggers are raised to WARNING whatever ``level`` is,
    because botocore writes secret values to DEBUG and httpx writes every
    request URL, signed query string included, to INFO. An app that needs
    their output sets the level itself after this call.

    Raises:
        RuntimeError: The console sink is on and ``sys.stderr`` is None.
    """
    # Remove default handler
    logger.remove()

    _cap_library_loggers()

    # Get logging config (lazy import to avoid circular dependency)
    config = _get_logging_config()

    if config.get("console", True) and sys.stderr is None:
        raise RuntimeError(
            "The console log sink needs sys.stderr, which is None in this process; "
            "set logging.console: false or give the process a stderr"
        )

    # A caller-resolved level outranks the config it was resolved from: it has
    # already folded in --verbose/--quiet and the CLI flag.
    resolved_level = level or config.get("level", "INFO")

    # Fire-and-forget mode by default -- sinks run on a background thread, so
    # logger.info() returns in ~us even with slow disk/network sinks. Override
    # with <PREFIX>_LOG_ENQUEUE=0 for sync semantics (audit logging, unit tests
    # that assert on captured output, etc.).
    enqueue = control_var("LOG_ENQUEUE", default="1") != "0"

    # CI mode: Auto-detect from environment or config, can be overridden by parameter
    # Priority: parameter > config > auto-detect
    if ci_mode is None:
        ci_mode = config.get("ci_mode")  # Check config first
    if ci_mode is None:
        ci_mode = _is_ci_environment()  # Auto-detect from environment

    console_is_tty = _stream_is_tty(sys.stderr)
    resolved_format = _resolve_console_format(log_format, config, is_tty=console_is_tty, ci_mode=bool(ci_mode))
    unrecognised_format = _unrecognised_format(log_format, config)

    # get_logging_config() resolves LOG_COLOR, NO_COLOR and logging.color, defaulting to the TTY check.
    use_color = bool(config.get("color", console_is_tty))

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

    # Build a Scrubber per spec Section 2.3. The resolver honours (in order):
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
        metrics=metrics,
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
        if resolved_format == "json":
            # One flat JSON object per line; emojis become ASCII tokens for the aggregator.
            logger.add(
                _JsonSink(sys.stderr),
                level=resolved_level,
                format=_fixed_format(""),
                colorize=False,
                # loguru still renders its own traceback, which no scalo sink
                # writes; diagnose would add a repr of every local to that work.
                diagnose=False,
                enqueue=enqueue,
                filter=_add_emoji_to_record(
                    False,
                    convert_to_text=True,
                    allow_all=False,
                    mask_sensitive=mask_sensitive,
                    masking_level=masking_level,
                    rate_limit_filter=rate_limit_filter,
                    scrubber=resolved_scrubber,
                ),
            )
        elif use_github_actions_commands:
            # GitHub Actions: Use custom sink for workflow commands (::error::, ::warning::, etc.)
            console_format = _get_log_format(is_file=False, ci_mode=True)
            logger.add(
                _github_actions_sink,
                level=resolved_level,
                format=console_format,
                colorize=False,
                diagnose=False,  # see note above: diagnose values bypass scrub
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
                level=resolved_level,
                format=console_format,
                colorize=False,
                diagnose=False,  # see note above: diagnose values bypass scrub
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
            # Human-readable console: colour per use_color, optional emojis.
            console_format = _get_log_format(is_file=False, color_scheme=color_scheme)
            logger.add(
                sys.stderr,
                level=resolved_level,
                format=console_format,
                colorize=use_color,
                diagnose=False,  # see note above: diagnose values bypass scrub
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
            level=resolved_level,
            format=file_format,
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8",
            diagnose=False,  # see note above: diagnose values bypass scrub
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

    if intercept_stdlib is None:
        intercept_stdlib = config.get("intercept_stdlib", True)
    _route_stdlib_logging(bool(intercept_stdlib), resolved_level)

    if unrecognised_format is not None:
        logger.warning(
            "Unrecognised log format, using auto",
            log_format=unrecognised_format,
            accepted="json, text, console, pretty, human, auto",
        )

    # Span export last, so whatever it reports goes through the sinks just built.
    # Telemetry failures degrade telemetry and never stop a service starting, so
    # this cannot raise past here.
    if otel_tracing:
        try:
            from ..otel_tracing import setup_tracing

            setup_tracing(service_name=service_name)
        except Exception as exc:
            logger.warning(f"OTLP span export unavailable, continuing without it: {exc}")

    return logger


# NOTE: get_logger() removed - just use 'from scalo.logger import logger' instead
# Loguru's logger is a singleton and uses module context for naming automatically

# ============================================================================
# Smart Auto-Configuration (Zero-Config Pattern)
# ============================================================================
# Only auto-configure if explicitly requested.
# Opt-in: set <PREFIX>_AUTO_LOGGER_CONFIG=1 (keeps <PREFIX>_NO_LOGGER_CONFIG as
# override); with no env prefix both names are bare.

if control_flag("AUTO_LOGGER_CONFIG") and not control_flag("NO_LOGGER_CONFIG"):
    # Smart defaults (auto-detects terminal, RFC 3339, emojis), but no span
    # export: this runs on `import scalo.logger`, and importing a library must
    # not start an exporter thread. A service gets tracing from its own
    # setup() call, which is where scalo-rs composes it too.
    setup(otel_tracing=False)


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
