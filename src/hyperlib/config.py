"""
HyperLib Config - Standard Dynaconf Interface
Enforces consistent configuration usage across ALL /src code
"""

import os
from pathlib import Path

from dynaconf import Dynaconf

# Initialize container-aware dynaconf configuration
current_file = Path(__file__)
if "/src/hyperlib/" in str(current_file):
    # Development: use container simulation
    project_root = current_file.parent.parent.parent
    container_root = project_root / "container"
else:
    # Production: use actual container paths
    container_root = Path("/")

config_dir = container_root / "app" / "config"

# Configurable environment variable prefix and app name
# Set HYPERLIB_ENV_PREFIX to override (e.g., HYPERLIB_ENV_PREFIX=MYAPP)
# Default: APP (e.g., APP_LOG_LEVEL, APP_DATABASE_URL)
ENV_PREFIX = os.getenv("HYPERLIB_ENV_PREFIX", "APP")

# Set HYPERLIB_APP_NAME for app-specific config directories
# Default: "app" (generic name)
APP_NAME = os.getenv("HYPERLIB_APP_NAME", "app")

settings = Dynaconf(
    envvar_prefix=ENV_PREFIX,  # Environment variables use {ENV_PREFIX}_ prefix
    settings_files=[
        str(config_dir / "config.yaml"),  # Override config (4th priority)
        str(config_dir / APP_NAME / "default.yaml"),  # App-specific default config (5th priority)
    ],
    load_dotenv=True,  # Load .env file (3rd priority)
    environments=False,  # Single config approach
    # PRECEDENCE: CLI → ENV → .env → config override → default → hardcoded
)


def get_settings():
    """Get standard dynaconf settings object"""
    return settings


def setup():
    """Setup configuration (for compatibility)"""
    return settings


# Standard configuration access functions
def get_api_config():
    """Get API configuration"""
    api_config = settings.get("api", {})
    return {
        "max_retries": api_config.get("max_retries", 3),
        "retry_delay": api_config.get("retry_delay", 5),
        "timeout": api_config.get("timeout", 120),
    }


def get_logging_config():
    """Get container-aware logging configuration with K8s standard env vars.

    Supports standard K8s/cloud-native logging environment variables:
    - LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - LOG_FORMAT: Output format (json, text, console, logfmt)
    - LOG_OUTPUT: Destination (stdout, stderr, file)
    - LOG_COLOR / NO_COLOR: Color control for output
    - LOG_TIMESTAMP_FORMAT: Timestamp format (iso8601, rfc3339, unix, epoch)
    - LOG_CALLER: Include source location (true/false)
    - LOG_STACKTRACE_LEVEL: Minimum level for stack traces (ERROR, CRITICAL)

    Environment Variable Prefix:
    - Default: APP_ (e.g., APP_LOGGING__LEVEL)
    - Configurable via: HYPERLIB_ENV_PREFIX (e.g., HYPERLIB_ENV_PREFIX=MYAPP)

    Priority order (CLI → ENV → .env → config → default → hardcoded):
    1. Standard environment variables (LOG_*)
    2. Dynaconf prefixed variables ({ENV_PREFIX}_LOGGING__*)
    3. Config file (logging.*)
    4. Hardcoded defaults
    """
    import os
    import sys

    logging_config = settings.get("logging", {})

    # LOG_LEVEL: Standard log level
    log_level = os.getenv("LOG_LEVEL")
    if not log_level:
        log_level = logging_config.get("level", "INFO")

    # LOG_FORMAT: Output format (json, text, console, logfmt)
    log_format = os.getenv("LOG_FORMAT")
    if not log_format:
        log_format = logging_config.get("format", "console")

    # LOG_OUTPUT: Destination (stdout, stderr, file)
    log_output = os.getenv("LOG_OUTPUT")
    if not log_output:
        log_output = logging_config.get("output", "stderr")

    # LOG_COLOR / NO_COLOR: Color control
    # NO_COLOR is a standard env var: https://no-color.org/
    log_color = os.getenv("LOG_COLOR")
    no_color = os.getenv("NO_COLOR")
    if log_color is not None:
        use_color = log_color.lower() in ("true", "1", "yes")
    elif no_color is not None:
        use_color = False  # NO_COLOR disables colors
    elif not sys.stderr.isatty():
        use_color = False  # Disable colors when not a TTY (K8s containers)
    else:
        use_color = logging_config.get("color", True)

    # LOG_TIMESTAMP_FORMAT: Timestamp format
    timestamp_format = os.getenv("LOG_TIMESTAMP_FORMAT")
    if not timestamp_format:
        timestamp_format = logging_config.get("timestamp_format", "rfc3339")

    # LOG_CALLER: Include source location
    log_caller = os.getenv("LOG_CALLER")
    if log_caller is not None:
        include_caller = log_caller.lower() in ("true", "1", "yes")
    else:
        include_caller = logging_config.get("caller", True)

    # LOG_STACKTRACE_LEVEL: Minimum level for stack traces
    stacktrace_level = os.getenv("LOG_STACKTRACE_LEVEL")
    if not stacktrace_level:
        stacktrace_level = logging_config.get("stacktrace_level", "ERROR")

    # Get container-aware log file path
    log_file = logging_config.get("file")
    if log_file and not log_file.startswith("/"):
        # Relative path - make it container-aware
        log_file = str(container_root / "var" / "log" / APP_NAME / log_file)

    return {
        "level": log_level,
        "format": log_format,
        "output": log_output,
        "color": use_color,
        "timestamp_format": timestamp_format,
        "caller": include_caller,
        "stacktrace_level": stacktrace_level,
        "console": logging_config.get("console", True),
        "file": log_file,
    }


# Export for direct access
__all__ = ["settings", "get_settings", "setup", "get_api_config", "get_logging_config", "ENV_PREFIX", "APP_NAME"]
