#  Project:      hyperi-pylib
#  File:         test_cardinality.py
#  Purpose:      Tests for label cardinality validation
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for CardinalityTracker — warns when metric labels exceed cardinality threshold."""

import threading

import pytest
from loguru import logger


@pytest.fixture
def tracker():
    """Fresh CardinalityTracker with default threshold (50)."""
    from hyperi_pylib.metrics.cardinality import CardinalityTracker

    return CardinalityTracker()


@pytest.fixture
def low_threshold_tracker():
    """CardinalityTracker with a low threshold (3) for easier triggering in tests."""
    from hyperi_pylib.metrics.cardinality import CardinalityTracker

    return CardinalityTracker(max_cardinality=3)


class TestCardinalityTrackerBasic:
    """Basic tracking behaviour below and above threshold."""

    def test_import(self):
        """CardinalityTracker can be imported from the metrics package."""
        from hyperi_pylib.metrics.cardinality import CardinalityTracker

        assert CardinalityTracker is not None

    def test_initial_cardinality_is_zero(self, tracker):
        """A freshly created tracker reports zero cardinality for any metric."""
        assert tracker.get_cardinality("my_metric_total") == 0

    def test_tracking_single_label_combination(self, tracker):
        """Tracking one label combination increments cardinality to 1."""
        tracker.track("requests_total", {"method": "GET", "status": "200"})
        assert tracker.get_cardinality("requests_total") == 1

    def test_same_label_combination_not_duplicated(self, tracker):
        """Tracking the same label combination multiple times counts as one unique entry."""
        labels = {"method": "GET", "status": "200"}
        tracker.track("requests_total", labels)
        tracker.track("requests_total", labels)
        tracker.track("requests_total", labels)
        assert tracker.get_cardinality("requests_total") == 1

    def test_different_label_combinations_counted_separately(self, tracker):
        """Each unique combination of label values is counted separately."""
        tracker.track("requests_total", {"method": "GET"})
        tracker.track("requests_total", {"method": "POST"})
        tracker.track("requests_total", {"method": "PUT"})
        assert tracker.get_cardinality("requests_total") == 3

    def test_different_metrics_tracked_independently(self, tracker):
        """Cardinality for different metric names is tracked independently."""
        tracker.track("metric_a_total", {"label": "val1"})
        tracker.track("metric_a_total", {"label": "val2"})
        tracker.track("metric_b_total", {"label": "val1"})

        assert tracker.get_cardinality("metric_a_total") == 2
        assert tracker.get_cardinality("metric_b_total") == 1

    def test_label_order_does_not_affect_identity(self, tracker):
        """Label dicts with the same keys/values in different order are the same combination."""
        tracker.track("requests_total", {"method": "GET", "status": "200"})
        tracker.track("requests_total", {"status": "200", "method": "GET"})
        assert tracker.get_cardinality("requests_total") == 1

    def test_empty_labels_tracked(self, tracker):
        """An empty labels dict is a valid single combination."""
        tracker.track("uptime_seconds", {})
        assert tracker.get_cardinality("uptime_seconds") == 1


class TestCardinalityWarning:
    """Warning emission when threshold is exceeded."""

    def test_no_warning_below_threshold(self, low_threshold_tracker, capfd):
        """No warning is emitted when unique combinations stay at or below threshold."""
        messages: list[str] = []

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(3):  # exactly at threshold, not over
                low_threshold_tracker.track("requests_total", {"user_id": str(i)})
        finally:
            logger.remove(sink_id)

        warning_messages = [m for m in messages if "High cardinality" in m]
        assert warning_messages == []

    def test_warning_emitted_when_threshold_exceeded(self, low_threshold_tracker):
        """A warning is logged when unique combinations exceed the threshold."""
        messages: list[str] = []

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(4):  # one over threshold of 3
                low_threshold_tracker.track("requests_total", {"user_id": str(i)})
        finally:
            logger.remove(sink_id)

        warning_messages = [m for m in messages if "High cardinality" in m]
        assert len(warning_messages) == 1

    def test_warning_contains_metric_name(self, low_threshold_tracker):
        """The warning message includes the metric name."""
        messages: list[str] = []

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(4):
                low_threshold_tracker.track("my_metric_total", {"id": str(i)})
        finally:
            logger.remove(sink_id)

        warning_text = " ".join(messages)
        assert "my_metric_total" in warning_text

    def test_warning_contains_threshold(self, low_threshold_tracker):
        """The warning message includes the configured threshold value."""
        messages: list[str] = []

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(4):
                low_threshold_tracker.track("requests_total", {"id": str(i)})
        finally:
            logger.remove(sink_id)

        warning_text = " ".join(messages)
        assert "3" in warning_text  # threshold is 3

    def test_warning_not_repeated_for_same_metric(self, low_threshold_tracker):
        """Once a metric has triggered a warning, further additions do not re-warn."""
        messages: list[str] = []

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(10):  # well over threshold
                low_threshold_tracker.track("requests_total", {"user_id": str(i)})
        finally:
            logger.remove(sink_id)

        warning_messages = [m for m in messages if "High cardinality" in m]
        assert len(warning_messages) == 1

    def test_warning_per_metric_not_shared(self, low_threshold_tracker):
        """Each metric gets its own independent warning — exceeding threshold on metric_a
        does not suppress the warning for metric_b."""
        messages: list[str] = []

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(4):
                low_threshold_tracker.track("metric_a_total", {"id": str(i)})
            for i in range(4):
                low_threshold_tracker.track("metric_b_total", {"id": str(i)})
        finally:
            logger.remove(sink_id)

        warning_messages = [m for m in messages if "High cardinality" in m]
        # One warning for each of the two metrics
        assert len(warning_messages) == 2


class TestGetCardinality:
    """get_cardinality() return values."""

    def test_unknown_metric_returns_zero(self, tracker):
        """get_cardinality returns 0 for a metric that has never been tracked."""
        assert tracker.get_cardinality("never_tracked_total") == 0

    def test_returns_correct_count_after_tracking(self, tracker):
        """get_cardinality returns exact count of unique label combinations."""
        for i in range(15):
            tracker.track("latency_seconds", {"endpoint": f"/path/{i}"})
        assert tracker.get_cardinality("latency_seconds") == 15

    def test_count_not_affected_by_duplicates(self, tracker):
        """Duplicate label combinations do not inflate the count."""
        tracker.track("latency_seconds", {"endpoint": "/api"})
        tracker.track("latency_seconds", {"endpoint": "/api"})
        tracker.track("latency_seconds", {"endpoint": "/api"})
        assert tracker.get_cardinality("latency_seconds") == 1


class TestReset:
    """reset() clears all state."""

    def test_reset_clears_cardinality(self, tracker):
        """After reset, cardinality for all metrics returns to zero."""
        tracker.track("requests_total", {"method": "GET"})
        tracker.track("requests_total", {"method": "POST"})
        assert tracker.get_cardinality("requests_total") == 2

        tracker.reset()

        assert tracker.get_cardinality("requests_total") == 0

    def test_reset_clears_warned_state(self, low_threshold_tracker):
        """After reset, a previously warned metric will warn again when threshold exceeded."""
        first_warnings: list[str] = []
        second_warnings: list[str] = []

        # Exceed threshold — triggers warning
        sink_id = logger.add(lambda msg: first_warnings.append(msg), level="WARNING")
        try:
            for i in range(4):
                low_threshold_tracker.track("requests_total", {"id": str(i)})
        finally:
            logger.remove(sink_id)

        assert any("High cardinality" in m for m in first_warnings)

        # Reset and exceed again — should warn once more
        low_threshold_tracker.reset()

        sink_id = logger.add(lambda msg: second_warnings.append(msg), level="WARNING")
        try:
            for i in range(4):
                low_threshold_tracker.track("requests_total", {"id": str(i)})
        finally:
            logger.remove(sink_id)

        assert any("High cardinality" in m for m in second_warnings)

    def test_tracking_works_normally_after_reset(self, tracker):
        """Tracking after reset accumulates cardinality from zero."""
        tracker.track("requests_total", {"method": "GET"})
        tracker.reset()
        tracker.track("requests_total", {"method": "POST"})
        assert tracker.get_cardinality("requests_total") == 1


class TestThreadSafety:
    """Thread-safety under concurrent tracking."""

    def test_concurrent_tracking_does_not_corrupt_state(self):
        """Many threads tracking distinct label combinations concurrently all get counted."""
        from hyperi_pylib.metrics.cardinality import CardinalityTracker

        ct = CardinalityTracker(max_cardinality=10000)
        errors: list[Exception] = []

        def add_labels(start: int, count: int) -> None:
            try:
                for i in range(start, start + count):
                    ct.track("concurrent_total", {"id": str(i)})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_labels, args=(i * 100, 100)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Exceptions in threads: {errors}"
        assert ct.get_cardinality("concurrent_total") == 1000

    def test_concurrent_reset_and_track_does_not_raise(self):
        """Concurrent reset and track calls do not raise exceptions."""
        from hyperi_pylib.metrics.cardinality import CardinalityTracker

        ct = CardinalityTracker()
        errors: list[Exception] = []

        def track_many() -> None:
            try:
                for i in range(200):
                    ct.track("requests_total", {"id": str(i)})
            except Exception as exc:
                errors.append(exc)

        def reset_repeatedly() -> None:
            try:
                for _ in range(50):
                    ct.reset()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=track_many),
            threading.Thread(target=track_many),
            threading.Thread(target=reset_repeatedly),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Exceptions in threads: {errors}"


class TestCustomThreshold:
    """Configurable max_cardinality threshold."""

    def test_custom_threshold_respected(self):
        """CardinalityTracker respects a non-default max_cardinality."""
        from hyperi_pylib.metrics.cardinality import CardinalityTracker

        messages: list[str] = []
        ct = CardinalityTracker(max_cardinality=5)

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(5):  # at threshold — no warning
                ct.track("requests_total", {"id": str(i)})

            assert not any("High cardinality" in m for m in messages)

            ct.track("requests_total", {"id": "overflow"})  # one over — triggers warning
        finally:
            logger.remove(sink_id)

        warning_messages = [m for m in messages if "High cardinality" in m]
        assert len(warning_messages) == 1

    def test_default_threshold_is_fifty(self):
        """Default max_cardinality is 50."""
        from hyperi_pylib.metrics.cardinality import CardinalityTracker

        messages: list[str] = []
        ct = CardinalityTracker()

        sink_id = logger.add(lambda msg: messages.append(msg), level="WARNING")
        try:
            for i in range(50):  # at threshold — no warning
                ct.track("requests_total", {"id": str(i)})

            assert not any("High cardinality" in m for m in messages)

            ct.track("requests_total", {"id": "overflow"})  # triggers warning
        finally:
            logger.remove(sink_id)

        warning_messages = [m for m in messages if "High cardinality" in m]
        assert len(warning_messages) == 1
