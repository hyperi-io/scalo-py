#  Project:      hyperi-pylib
#  File:         consumer.py
#  Purpose:      ConsumerMetrics group -- for Kafka consumer DFE apps
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
ConsumerMetrics -- composable metric group for Kafka consumer DFE apps.

Mirrors rustlib's dfe_groups::ConsumerMetrics. Tracks consumer lag,
partition assignment, rebalances, poll timing, and offset commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager

# Tuned defaults matching rustlib
DEFAULT_POLL_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0)


class ConsumerMetrics:
    """
    Kafka consumer metrics for DFE apps.

    Registers:
        {ns}_consumer_lag gauge (labels: topic, partition)
        {ns}_consumer_partitions_assigned gauge
        {ns}_consumer_rebalance_total counter
        {ns}_consumer_poll_duration_seconds histogram
        {ns}_offsets_committed_total counter
    """

    def __init__(
        self,
        mgr: MetricsManager,
        poll_duration_buckets: tuple[float, ...] | None = None,
    ) -> None:
        """
        Register all consumer metrics.

        Args:
            mgr: MetricsManager instance
            poll_duration_buckets: Custom histogram buckets for poll duration
        """
        buckets = poll_duration_buckets or DEFAULT_POLL_DURATION_BUCKETS

        self._consumer_lag: Any = mgr.gauge(
            "consumer_lag", "Consumer offset lag per partition", labels=["topic", "partition"]
        )
        self._partitions_assigned: Any = mgr.gauge("consumer_partitions_assigned", "Current assigned partition count")
        self._rebalance_total: Any = mgr.counter("consumer_rebalance_total", "Consumer group rebalances")
        self._poll_duration: Any = mgr.histogram(
            "consumer_poll_duration_seconds",
            "Time per poll/recv call",
            buckets=tuple(buckets),
        )
        self._offsets_committed: Any = mgr.counter("offsets_committed_total", "Kafka offsets committed")

    def set_lag(self, topic: str, partition: int, lag: int) -> None:
        """Set consumer lag for a specific topic-partition."""
        self._consumer_lag.labels(topic=topic, partition=str(partition)).set(lag)

    def set_partitions_assigned(self, count: int) -> None:
        """Set the number of partitions currently assigned."""
        self._partitions_assigned.set(count)

    def record_rebalance(self) -> None:
        """Increment the rebalance counter."""
        self._rebalance_total.inc()

    def record_poll_duration(self, duration_seconds: float) -> None:
        """Record a poll/recv call duration."""
        self._poll_duration.observe(duration_seconds)

    def record_offsets_committed(self, count: int = 1) -> None:
        """Increment offsets committed counter."""
        self._offsets_committed.inc(count)
