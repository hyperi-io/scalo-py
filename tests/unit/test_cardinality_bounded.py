#  Project:   hyperi-pylib
#  File:      tests/unit/test_cardinality_bounded.py
#  Purpose:   Verify CardinalityTracker bounds memory via LRU eviction
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""S5 regression: tracker must not grow unbounded over long-running
processes. Per-metric storage capped at 2 * max_cardinality with LRU
eviction of oldest entries."""

from __future__ import annotations

import pytest
from loguru import logger

from hyperi_pylib.metrics.cardinality import CardinalityTracker


def test_warning_still_fires_above_threshold():
    """loguru warning fires once when count first exceeds threshold,
    even after subsequent tracks beyond the LRU cap."""
    tracker = CardinalityTracker(max_cardinality=3)
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        for i in range(5):  # 5 > threshold 3
            tracker.track("metric_a", {"user": f"u{i}"})
    finally:
        logger.remove(sink_id)
    warnings = [m for m in messages if "High cardinality" in m]
    assert len(warnings) == 1


def test_lru_cap_keeps_memory_bounded():
    """At max_cardinality=10 the LRU cap is 20. Inserting 100 unique
    labels should leave at most 20 in the per-metric bucket."""
    tracker = CardinalityTracker(max_cardinality=10)
    for i in range(100):
        tracker.track("metric_b", {"user": f"u{i}"})

    assert tracker.get_cardinality("metric_b") == 20  # capped at 2*10


def test_lru_evicts_oldest_first():
    tracker = CardinalityTracker(max_cardinality=2)
    # lru_cap = 4
    tracker.track("m", {"k": "a"})  # bucket: [a]
    tracker.track("m", {"k": "b"})  # bucket: [a, b]
    tracker.track("m", {"k": "c"})  # bucket: [a, b, c]
    tracker.track("m", {"k": "d"})  # bucket: [a, b, c, d] (at cap)
    tracker.track("m", {"k": "e"})  # evicts 'a' -> [b, c, d, e]

    # touch 'b' to keep it warm; would otherwise be evicted next
    tracker.track("m", {"k": "b"})  # -> [c, d, e, b]
    tracker.track("m", {"k": "f"})  # evicts 'c' -> [d, e, b, f]

    bucket = tracker._seen["m"]
    keys = [k[0][1] for k in bucket]
    assert keys == ["d", "e", "b", "f"]


def test_per_metric_buckets_independent():
    tracker = CardinalityTracker(max_cardinality=2)
    for i in range(20):
        tracker.track("m1", {"x": f"v{i}"})
    for i in range(2):
        tracker.track("m2", {"y": f"v{i}"})

    assert tracker.get_cardinality("m1") == 4  # capped
    assert tracker.get_cardinality("m2") == 2  # under cap


def test_reset_clears_all():
    tracker = CardinalityTracker(max_cardinality=5)
    for i in range(50):
        tracker.track("m", {"x": f"v{i}"})
    assert tracker.get_cardinality("m") == 10

    tracker.reset()
    assert tracker.get_cardinality("m") == 0
