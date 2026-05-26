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

Matches the cardinality cap described in the DFE Metrics Standard:
  max_label_cardinality default = 50
"""

import threading
from collections import defaultdict


class CardinalityTracker:
    """Tracks unique label combinations per metric and warns on high cardinality.

    High cardinality labels (user IDs, request paths, IPs) cause Prometheus
    scrape explosion. This tracker logs a warning (once per metric) when unique
    label combinations exceed the threshold.

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
        """
        self._max_cardinality = max_cardinality
        self._seen: dict[str, set[tuple[tuple[str, str], ...]]] = defaultdict(set)
        self._warned: set[str] = set()
        self._lock = threading.Lock()

    def track(self, metric_name: str, labels: dict[str, str]) -> None:
        """Track a label combination for a metric.

        Adds the label combination to the set of seen combinations for the metric.
        If the count exceeds the threshold and this metric has not yet been warned
        about, a single WARNING is logged via hyperi_pylib.logger.

        Args:
            metric_name: The full metric name (e.g. "dfe_loader_requests_total").
            labels: The label key-value pairs for this observation.
        """
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._seen[metric_name].add(label_key)
            count = len(self._seen[metric_name])
            if count > self._max_cardinality and metric_name not in self._warned:
                self._warned.add(metric_name)
                # Import inside the method to avoid circular imports at module load time.
                from hyperi_pylib.logger import logger

                logger.warning(
                    "High cardinality detected: metric={metric} unique_combinations={unique_combinations} threshold={threshold}",
                    metric=metric_name,
                    unique_combinations=count,
                    threshold=self._max_cardinality,
                )

    def get_cardinality(self, metric_name: str) -> int:
        """Return the current number of unique label combinations for a metric.

        Args:
            metric_name: The metric name to query.

        Returns:
            Number of unique label combinations seen so far. Returns 0 if the
            metric has never been tracked.
        """
        with self._lock:
            return len(self._seen.get(metric_name, set()))

    def reset(self) -> None:
        """Reset all tracking state.

        Clears both the seen combinations and the set of already-warned metrics.
        After reset, all cardinality counts return to zero and warnings will be
        emitted again if thresholds are re-exceeded.
        """
        with self._lock:
            self._seen.clear()
            self._warned.clear()
