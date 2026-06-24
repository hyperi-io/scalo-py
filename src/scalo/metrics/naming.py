#  Project:      scalo
#  File:         naming.py
#  Purpose:      Metric naming validation matching scalo-rs conventions
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Metric naming validation.

Enforces the naming convention: ``{prefix}_{app}_{metric_name}[_{unit}]``,
where ``{prefix}`` is the configurable platform prefix (bare "" by default;
see :func:`scalo.metric_prefix`) and ``{app}`` is optional.

Counters must end in _total.
Histograms/durations should end in _seconds, _bytes, or _ratio.

Validation is non-blocking -- returns warnings but does not raise.
"""

from .._env_compat import metric_prefix
from ..logger import logger


def validate_metric_name(name: str, metric_type: str) -> list[str]:
    """
    Validate metric name follows Prometheus naming conventions.

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


def validate_metric_prefix(name: str, app: str = "", prefix: str | None = None) -> list[str]:
    """
    Validate metric name carries the expected ``{prefix}_{app}_`` prefix.

    Args:
        name: Full metric name
        app: App identifier (e.g. "loader"). Empty string for platform-wide metrics.
        prefix: Platform prefix to expect. Defaults to the active
            :func:`scalo.metric_prefix` (bare "" unless configured), so by
            default only the ``{app}_`` portion (if any) is enforced.

    Returns:
        List of warning strings. Empty list means valid.
    """
    if prefix is None:
        prefix = metric_prefix()

    warnings: list[str] = []

    if not name:
        warnings.append("Metric name is empty")
        return warnings

    parts = [p for p in (prefix, app) if p]
    expected_prefix = "_".join(parts) + "_" if parts else ""

    if expected_prefix and not name.startswith(expected_prefix):
        warnings.append(f"Metric '{name}' should start with '{expected_prefix}'")

    for w in warnings:
        logger.debug(f"Metric prefix warning: {w}")

    return warnings


def validate_dfe_prefix(name: str, app: str) -> list[str]:
    """Deprecated alias for :func:`validate_metric_prefix` (expects a ``dfe_`` prefix).

    Retained for downstream callers migrating from hyperi-pylib; prefer
    ``validate_metric_prefix`` with an explicit ``prefix`` in new code.
    """
    return validate_metric_prefix(name, app, prefix="dfe")
