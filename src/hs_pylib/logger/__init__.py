"""hs-pylib Logger Module - Re-exports from logger.py for backward compatibility."""

from .logger import (
    _is_ci_environment,
    _is_github_actions,
    debug,
    emojis_to_text,
    error,
    info,
    log,
    logger,
    setup,
    strip_emojis,
    success,
    warning,
)

# Public API names (without underscore prefix)
is_ci_environment = _is_ci_environment
is_github_actions = _is_github_actions

__all__ = [
    "debug",
    "emojis_to_text",
    "error",
    "info",
    "is_ci_environment",
    "is_github_actions",
    "log",
    "logger",
    "setup",
    "strip_emojis",
    "success",
    "warning",
]
