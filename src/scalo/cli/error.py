# Project:   scalo
# File:      cli/error.py
# Purpose:   CLI error types for services
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""CLI error types for service applications.

Mirrors the error hierarchy from scalo-rs's cli::error module.
Each variant maps to a specific lifecycle failure mode.
"""

__all__ = [
    "CliError",
    "ConfigError",
    "InvalidArgumentError",
    "LoggerError",
    "ServiceError",
]


class CliError(Exception):
    """Base error for CLI operations."""


class ConfigError(CliError):
    """Configuration loading or validation failed."""


class LoggerError(CliError):
    """Logger initialisation failed."""


class ServiceError(CliError):
    """Service runtime error."""


class InvalidArgumentError(CliError):
    """Invalid CLI argument."""
