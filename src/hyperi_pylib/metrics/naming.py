#  Project:      hyperi-pylib
#  File:         naming.py
#  Purpose:      DFE metric naming validation matching rustlib conventions
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
DFE metric naming validation.

Enforces the naming convention: dfe_{app}_{metric_name}[_{unit}]

Counters must end in _total.
Histograms/durations should end in _seconds, _bytes, or _ratio.
All DFE metrics should be prefixed with dfe_{app}_.

Validation is non-blocking — returns warnings but does not raise.
"""

from ..logger import logger


def validate_metric_name(name: str, metric_type: str) -> list[str]:
    """
    Validate metric name follows Prometheus/DFE naming conventions.

    Args:
        name: Full metric name
        metric_type: One of "counter", "gauge", "histogram"

    Returns:
        List of warning strings. Empty list means valid.
    """
    warnings: list[str] = []

    if not name:
        warnings.append("Metric name is empty")
        return warnings

    if metric_type == "counter" and not name.endswith("_total"):
        warnings.append(f"Counter '{name}' should end with '_total' suffix")

    if metric_type == "histogram":
        valid_suffixes = ("_seconds", "_bytes", "_ratio")
        if not any(name.endswith(s) for s in valid_suffixes):
            warnings.append(f"Histogram '{name}' should end with a unit suffix (_seconds, _bytes, or _ratio)")

    for w in warnings:
        logger.debug(f"Metric naming warning: {w}")

    return warnings


def validate_dfe_prefix(name: str, app: str) -> list[str]:
    """
    Validate metric name has correct dfe_{app}_ prefix.

    Args:
        name: Full metric name
        app: App identifier (e.g. "loader", "receiver"). Empty string for platform metrics.

    Returns:
        List of warning strings. Empty list means valid.
    """
    warnings: list[str] = []

    if not name:
        warnings.append("Metric name is empty")
        return warnings

    if app:
        expected_prefix = f"dfe_{app}_"
    else:
        expected_prefix = "dfe_"

    if not name.startswith(expected_prefix):
        warnings.append(f"Metric '{name}' should start with '{expected_prefix}'")

    for w in warnings:
        logger.debug(f"Metric prefix warning: {w}")

    return warnings
