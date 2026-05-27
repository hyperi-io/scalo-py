#  Project:      hyperi-pylib
#  File:         cardinality.py
#  Purpose:      Label cardinality tracking and high-cardinality warning for Prometheus metrics
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Label cardinality tracking for Prometheus metrics.

High-cardinality labels -- user IDs, request paths, IP addresses -- cause Prometheus
scrape explosion: each unique combination becomes a separate time series. This module
tracks unique label combinations per metric and emits a warning (once per metric)
when the count exceeds a configurable threshold.

The tracker is bounded: each metric's seen-set is capped at
``2 * max_cardinality`` entries via LRU eviction. This keeps memory
usage flat over long-running processes even if the warning is ignored.

Matches the cardinality cap described in the DFE Metrics Standard:
  max_label_cardinality default = 50
"""

import threading
from collections import OrderedDict


class CardinalityTracker:
    """Tracks unique label combinations per metric and warns on high cardinality.

    High cardinality labels (user IDs, request paths, IPs) cause Prometheus
    scrape explosion. This tracker logs a warning (once per metric) when unique
    label combinations exceed the threshold.

    Memory is bounded: the per-metric seen-set is an LRU capped at
    ``2 * max_cardinality`` entries. A long-running process that
    keeps emitting new label combinations will see the oldest entries
    evicted rather than the dict growing without bound.

    Thread-safe: all mutations are protected by a lock.

    Example::

        tracker = CardinalityTracker(max_cardinality=50)
        tracker.track("requests_total", {"method": "GET", "status": "200"})
        tracker.track("requests_total", {"method": "POST", "status": "201"})
        print(tracker.get_cardinality("requests_total"))  # 2
    """

    def __init__(self, max_cardinality: int = 50) -> None:
        """Initialise the tracker.

        Args:
            max_cardinality: Maximum unique label combinations allowed before
                a warning is logged. Defaults to 50 (DFE Metrics Standard default).
                LRU cap on memory is ``2 * max_cardinality`` per metric.
        """
        self._max_cardinality = max_cardinality
        self._lru_cap = max_cardinality * 2
        # OrderedDict gives us O(1) move-to-end + popitem(last=False)
        # for LRU. Value is None; we only care about keys + ordering.
        self._seen: dict[str, OrderedDict[tuple[tuple[str, str], ...], None]] = {}
        self._warned: set[str] = set()
        self._lock = threading.Lock()

    def track(self, metric_name: str, labels: dict[str, str]) -> None:
        """Track a label combination for a metric.

        Adds the label combination to the LRU map for the metric. If the
        count exceeds ``max_cardinality`` and this metric has not yet been
        warned about, a single WARNING is logged via hyperi_pylib.logger.
        If the map exceeds ``2 * max_cardinality`` the oldest entry is
        evicted to keep memory bounded.

        Args:
            metric_name: The full metric name (e.g. "dfe_loader_requests_total").
            labels: The label key-value pairs for this observation.
        """
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            bucket = self._seen.get(metric_name)
            if bucket is None:
                bucket = OrderedDict()
                self._seen[metric_name] = bucket

            if label_key in bucket:
                bucket.move_to_end(label_key)
            else:
                bucket[label_key] = None
                if len(bucket) > self._lru_cap:
                    bucket.popitem(last=False)

            count = len(bucket)
            if count > self._max_cardinality and metric_name not in self._warned:
                self._warned.add(metric_name)
                from hyperi_pylib.logger import logger

                logger.warning(
                    "High cardinality detected: metric={metric} unique_combinations={unique_combinations} threshold={threshold}",
                    metric=metric_name,
                    unique_combinations=count,
                    threshold=self._max_cardinality,
                )

    def get_cardinality(self, metric_name: str) -> int:
        """Number of unique label combinations CURRENTLY held for a metric.

        Note: under LRU eviction this may be less than the lifetime
        count. The warning at ``max_cardinality`` still fires once based
        on observed-at-time count.
        """
        with self._lock:
            bucket = self._seen.get(metric_name)
            return len(bucket) if bucket else 0

    def reset(self) -> None:
        """Reset all tracking state.

        Clears both the seen combinations and the set of already-warned metrics.
        After reset, all cardinality counts return to zero and warnings will be
        emitted again if thresholds are re-exceeded.
        """
        with self._lock:
            self._seen.clear()
            self._warned.clear()
