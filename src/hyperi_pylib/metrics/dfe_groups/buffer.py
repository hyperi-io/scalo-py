#  Project:      hyperi-pylib
#  File:         buffer.py
#  Purpose:      BufferMetrics group -- for receiver, loader, archiver
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
BufferMetrics -- composable metric group for buffered DFE apps.

Mirrors rustlib's dfe_groups::BufferMetrics. Tracks buffer occupancy,
flush operations, and flush triggers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager

# Tuned defaults matching rustlib
DEFAULT_FLUSH_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0)


class BufferMetrics:
    """
    Buffer metrics for DFE apps with internal buffering.

    Registers:
        {ns}_buffer_bytes gauge
        {ns}_buffer_records gauge
        {ns}_buffer_flush_total counter
        {ns}_buffer_flush_duration_seconds histogram
        {ns}_buffer_flush_trigger_total counter (labels: trigger)
    """

    def __init__(
        self,
        mgr: MetricsManager,
        flush_duration_buckets: tuple[float, ...] | None = None,
    ) -> None:
        """
        Register all buffer metrics.

        Args:
            mgr: MetricsManager instance
            flush_duration_buckets: Custom histogram buckets for flush duration
        """
        buckets = flush_duration_buckets or DEFAULT_FLUSH_DURATION_BUCKETS

        self._buffer_bytes: Any = mgr.gauge("buffer_bytes", "Current buffer size in bytes")
        self._buffer_records: Any = mgr.gauge("buffer_records", "Current buffered record count")
        self._buffer_flush_total: Any = mgr.counter("buffer_flush_total", "Total flush operations")
        self._buffer_flush_duration: Any = mgr.histogram(
            "buffer_flush_duration_seconds",
            "Flush operation latency",
            buckets=tuple(buckets),
        )
        self._buffer_flush_trigger: Any = mgr.counter(
            "buffer_flush_trigger_total",
            "Flush trigger reason",
            labels=["trigger"],
        )

    def set_buffer_state(self, bytes_val: int, records: int) -> None:
        """Set current buffer occupancy gauges."""
        self._buffer_bytes.set(bytes_val)
        self._buffer_records.set(records)

    def record_flush(self, duration_seconds: float, trigger: str) -> None:
        """
        Record a buffer flush event.

        Args:
            duration_seconds: Time taken to flush
            trigger: Flush trigger reason (size, age, eviction, records)
        """
        self._buffer_flush_total.inc()
        self._buffer_flush_duration.observe(duration_seconds)
        self._buffer_flush_trigger.labels(trigger=trigger).inc()
