#  Project:      hyperi-pylib
#  File:         sink.py
#  Purpose:      SinkMetrics group -- for DFE apps with a downstream
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
SinkMetrics -- composable metric group for DFE apps with downstream sinks.

Mirrors rustlib's dfe_groups::SinkMetrics. Tracks sink write latency,
errors, bytes sent, and in-flight insert count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager

# Tuned defaults matching rustlib
DEFAULT_SINK_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class SinkMetrics:
    """
    Sink metrics for DFE apps writing to downstream systems.

    Registers:
        {ns}_sink_duration_seconds histogram (labels: backend)
        {ns}_sink_errors_total counter (labels: backend)
        {ns}_bytes_sent_total counter (labels: format)
        {ns}_concurrent_inserts gauge
    """

    def __init__(
        self,
        mgr: MetricsManager,
        sink_duration_buckets: tuple[float, ...] | None = None,
    ) -> None:
        """
        Register all sink metrics.

        Args:
            mgr: MetricsManager instance
            sink_duration_buckets: Custom histogram buckets for sink write duration
        """
        buckets = sink_duration_buckets or DEFAULT_SINK_DURATION_BUCKETS

        self._sink_duration: Any = mgr.histogram(
            "sink_duration_seconds",
            "Sink write latency",
            labels=["backend"],
            buckets=tuple(buckets),
        )
        self._sink_errors: Any = mgr.counter("sink_errors_total", "Sink write errors", labels=["backend"])
        self._bytes_sent: Any = mgr.counter("bytes_sent_total", "Bytes sent to sink", labels=["format"])
        self._concurrent_inserts: Any = mgr.gauge("concurrent_inserts", "In-flight insert/write count")

    def record_duration(self, backend: str, duration_seconds: float) -> None:
        """Record a sink write duration for a specific backend."""
        self._sink_duration.labels(backend=backend).observe(duration_seconds)

    def record_error(self, backend: str, count: int = 1) -> None:
        """Increment sink error counter for a specific backend."""
        self._sink_errors.labels(backend=backend).inc(count)

    def record_bytes_sent(self, fmt: str, nbytes: int) -> None:
        """Increment bytes sent counter with format label."""
        self._bytes_sent.labels(format=fmt).inc(nbytes)

    def set_concurrent_inserts(self, count: int) -> None:
        """Set the number of in-flight insert operations."""
        self._concurrent_inserts.set(count)
