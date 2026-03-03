# Project:   hyperi-pylib
# File:      cli/error.py
# Purpose:   CLI error types for DFE services
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""CLI error types for DFE service applications.

Mirrors the error hierarchy from hyperi-rustlib's cli::error module.
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
