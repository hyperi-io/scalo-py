#  Project:      hyperi-pylib
#  File:         backpressure.py
#  Purpose:      BackpressureMetrics group for DFE apps
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
BackpressureMetrics -- composable metric group for backpressure tracking.

Mirrors rustlib's dfe_groups::BackpressureMetrics. Tracks backpressure
activation events and cumulative pause duration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager


class BackpressureMetrics:
    """
    Backpressure metrics for DFE apps.

    Registers:
        {ns}_backpressure_events_total counter
        {ns}_backpressure_duration_seconds_total counter
    """

    def __init__(self, mgr: MetricsManager) -> None:
        """
        Register backpressure metrics.

        Args:
            mgr: MetricsManager instance
        """
        self._events: Any = mgr.counter("backpressure_events_total", "Backpressure activation events")
        self._duration: Any = mgr.counter("backpressure_duration_seconds_total", "Cumulative backpressure pause time")

    def record_event(self) -> None:
        """Record a backpressure activation event."""
        self._events.inc()

    def record_duration(self, duration_seconds: float) -> None:
        """Add to cumulative backpressure pause time."""
        self._duration.inc(duration_seconds)
