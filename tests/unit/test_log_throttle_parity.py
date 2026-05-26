#  Project:      hyperi-pylib
#  File:         test_log_throttle_parity.py
#  Purpose:      Verify RateLimitFilter behaviour matches rustlib's log throttle pattern
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Parity tests for log throttle alignment with hyperi-rustlib.

These tests verify that hyperi-pylib's RateLimitFilter behaviour matches
hyperi-rustlib's log throttle implementation per the unified spec.

Rustlib pattern: identical (or normalised) messages within a window are suppressed;
the next emission after the window appends a "(suppressed N similar)" summary.
"""

import time

from hyperi_pylib.logger.filters import RateLimitFilter


def _make_record(message: str, level_no: int = 20, name: str = "test.logger") -> dict:
    """Build a minimal Loguru-style record dict."""

    class _Level:
        def __init__(self, no: int) -> None:
            self.no = no

    return {"message": message, "level": _Level(level_no), "name": name}


class TestDeduplicationWithinWindow:
    """Identical messages within the period are suppressed -- parity with rustlib throttle."""

    def test_first_emission_always_passes(self):
        """First occurrence of any message is never throttled."""
        f = RateLimitFilter(period_sec=30)
        assert f(_make_record("Connection refused")) is True

    def test_second_identical_message_suppressed(self):
        """Second identical message within the window is suppressed."""
        f = RateLimitFilter(period_sec=30)
        f(_make_record("Connection refused"))
        assert f(_make_record("Connection refused")) is False

    def test_many_identical_messages_all_suppressed(self):
        """All subsequent messages within the window are suppressed, not just the second."""
        f = RateLimitFilter(period_sec=30)
        results = [f(_make_record("DB timeout")) for _ in range(10)]
        # First passes, rest suppressed
        assert results[0] is True
        assert all(r is False for r in results[1:])

    def test_suppressed_count_increments_for_each_dropped(self):
        """Suppressed count tracks every dropped message, matching rustlib's counter."""
        f = RateLimitFilter(period_sec=30)
        msg = "Kafka lag exceeded threshold"
        for _ in range(6):
            f(_make_record(msg))
        # 1 passed, 5 suppressed
        assert f.get_suppressed_count(name="test.logger", level=20, message=msg) == 5


class TestSummaryAppend:
    """Suppressed count is appended to the next emission -- parity with rustlib summary field."""

    def test_summary_appended_after_window_expires(self):
        """After window expiry, the resumed message includes suppression count."""
        f = RateLimitFilter(period_sec=0.1, summary_enabled=True)
        msg = "Retrying upstream call"

        # First emission
        f(_make_record(msg))

        # Suppress 3 within window
        for _ in range(3):
            f(_make_record(msg))

        # Expire window, next emission should carry summary
        time.sleep(0.15)
        resume = _make_record(msg)
        assert f(resume) is True
        assert "(suppressed 3 similar)" in resume["message"]

    def test_summary_format_matches_rustlib(self):
        """Summary text format: '<original> (suppressed N similar)'."""
        f = RateLimitFilter(period_sec=0.1, summary_enabled=True)
        msg = "Health check failed"

        f(_make_record(msg))
        for _ in range(7):
            f(_make_record(msg))

        time.sleep(0.15)
        resume = _make_record(msg)
        f(resume)
        assert resume["message"] == f"{msg} (suppressed 7 similar)"

    def test_summary_count_resets_after_emission(self):
        """Suppressed count resets to zero after a summary is emitted."""
        f = RateLimitFilter(period_sec=0.1, summary_enabled=True)
        msg = "Cache miss"

        # First window: 1 pass + 2 suppressed
        f(_make_record(msg))
        f(_make_record(msg))
        f(_make_record(msg))

        # Second window: resume, count resets
        time.sleep(0.15)
        resume = _make_record(msg)
        f(resume)  # emits with "(suppressed 2 similar)"

        # Third window: no suppressions yet, count should be 0
        assert f.get_suppressed_count(name="test.logger", level=20, message=msg) == 0

    def test_summary_disabled_leaves_message_unchanged(self):
        """When summary_enabled=False, resumed message is not modified."""
        f = RateLimitFilter(period_sec=0.1, summary_enabled=False)
        msg = "Worker stalled"

        f(_make_record(msg))
        for _ in range(4):
            f(_make_record(msg))

        time.sleep(0.15)
        resume = _make_record(msg)
        f(resume)
        assert resume["message"] == msg
        assert "suppressed" not in resume["message"]

    def test_no_summary_when_nothing_suppressed(self):
        """No summary appended when there were no suppressions in the previous window."""
        f = RateLimitFilter(period_sec=0.1, summary_enabled=True)
        msg = "Heartbeat OK"

        f(_make_record(msg))
        # No suppressions -- window expires cleanly
        time.sleep(0.15)

        resume = _make_record(msg)
        f(resume)
        assert resume["message"] == msg


class TestPatternNormalisation:
    """Variable parts of messages are normalised -- parity with rustlib's normalise_numbers."""

    def test_large_numbers_normalised(self):
        """Messages differing only in large numbers (4+ digits) are treated as identical."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=True)
        assert f(_make_record("Processed batch 10001")) is True
        assert f(_make_record("Processed batch 99999")) is False

    def test_uuids_normalised(self):
        """Messages differing only in UUIDs are treated as identical."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=True)
        r1 = "Request 550e8400-e29b-41d4-a716-446655440000 failed"
        r2 = "Request a1b2c3d4-e5f6-7890-abcd-ef1234567890 failed"
        assert f(_make_record(r1)) is True
        assert f(_make_record(r2)) is False

    def test_ip_addresses_normalised(self):
        """Messages differing only in IP addresses are treated as identical."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=True)
        assert f(_make_record("Blocked connection from 192.168.1.10")) is True
        assert f(_make_record("Blocked connection from 10.20.30.40")) is False

    def test_iso_timestamps_normalised(self):
        """Messages differing only in ISO timestamps are treated as identical."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=True)
        assert f(_make_record("Event occurred at 2024-01-15T10:30:00.000Z")) is True
        assert f(_make_record("Event occurred at 2025-06-20T23:59:59.999Z")) is False

    def test_hex_strings_normalised(self):
        """Messages differing only in hex strings (8+ chars) are treated as identical."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=True)
        assert f(_make_record("Checksum mismatch: deadbeef1234abcd")) is True
        assert f(_make_record("Checksum mismatch: cafebabe87654321")) is False

    def test_mixed_variable_parts_normalised(self):
        """Messages with multiple variable parts (ID + IP) are still grouped."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=True)
        assert f(_make_record("Order 12345 from 192.168.0.1 rejected")) is True
        assert f(_make_record("Order 99999 from 10.0.0.5 rejected")) is False

    def test_normalisation_disabled_treats_different_numbers_as_different(self):
        """Without normalise_numbers, each distinct message is a separate key."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=False)
        assert f(_make_record("Failed for order 12345")) is True
        assert f(_make_record("Failed for order 67890")) is True

    def test_normalisation_disabled_same_message_still_suppressed(self):
        """Without normalise_numbers, exact duplicates are still suppressed."""
        f = RateLimitFilter(period_sec=30, normalise_numbers=False)
        msg = "Exact duplicate message"
        assert f(_make_record(msg)) is True
        assert f(_make_record(msg)) is False


class TestDifferentMessagesPassThrough:
    """Unrelated messages are not throttled by each other -- independent tracking."""

    def test_distinct_messages_each_pass_independently(self):
        """Five distinct messages all pass through even with a tight window."""
        f = RateLimitFilter(period_sec=30)
        messages = [
            "Connection refused",
            "Timeout waiting for lock",
            "Schema validation failed",
            "Queue depth exceeded",
            "Certificate expiring soon",
        ]
        results = [f(_make_record(m)) for m in messages]
        assert all(r is True for r in results)

    def test_throttle_on_one_does_not_affect_another(self):
        """Suppression of one message does not suppress a different message."""
        f = RateLimitFilter(period_sec=30)
        msg_a = "Service A unhealthy"
        msg_b = "Service B unhealthy"

        f(_make_record(msg_a))  # msg_a: first pass
        f(_make_record(msg_a))  # msg_a: suppressed

        # msg_b is unrelated -- must still pass
        assert f(_make_record(msg_b)) is True

    def test_same_text_different_level_tracked_independently(self):
        """Same message text at different log levels are separate throttle keys."""
        f = RateLimitFilter(period_sec=30)
        msg = "Disk usage high"
        assert f(_make_record(msg, level_no=20)) is True  # INFO
        assert f(_make_record(msg, level_no=40)) is True  # ERROR

    def test_same_text_different_logger_tracked_independently(self):
        """Same message from different logger names are separate throttle keys."""
        f = RateLimitFilter(period_sec=30)
        msg = "Pool exhausted"
        assert f(_make_record(msg, name="module.alpha")) is True
        assert f(_make_record(msg, name="module.beta")) is True


class TestWindowExpiry:
    """After the period, the same message is allowed again -- window semantics."""

    def test_message_allowed_after_window_expires(self):
        """Same message passes again once the period has elapsed."""
        f = RateLimitFilter(period_sec=0.1)
        msg = "Upstream timeout"

        assert f(_make_record(msg)) is True
        assert f(_make_record(msg)) is False  # suppressed within window

        time.sleep(0.15)
        assert f(_make_record(msg)) is True  # window expired, passes again

    def test_suppression_resumes_after_resumed_emission(self):
        """After resuming post-expiry, further messages within the new window are suppressed."""
        f = RateLimitFilter(period_sec=0.1)
        msg = "Write buffer full"

        f(_make_record(msg))  # first pass

        time.sleep(0.15)
        f(_make_record(msg))  # resumed after expiry

        # Now within a new window -- must suppress again
        assert f(_make_record(msg)) is False

    def test_window_boundary_is_per_message(self):
        """Each message key has its own independent expiry timer."""
        f = RateLimitFilter(period_sec=0.1)
        msg_a = "Alpha event"
        msg_b = "Beta event"

        f(_make_record(msg_a))
        time.sleep(0.08)  # Not yet expired for msg_a
        f(_make_record(msg_b))  # msg_b starts its own timer

        time.sleep(0.07)  # msg_a expired (~0.15s total), msg_b has ~0.07s left

        assert f(_make_record(msg_a)) is True  # msg_a window expired
        assert f(_make_record(msg_b)) is False  # msg_b window still active

    def test_multiple_expiry_cycles_work_correctly(self):
        """Filter correctly handles multiple pass/suppress cycles over time."""
        f = RateLimitFilter(period_sec=0.1)
        msg = "Metric collection lag"
        passes = []

        for cycle in range(3):
            # Each cycle: one pass, then suppress, then expire
            r = _make_record(msg)
            passes.append(f(r))  # should pass

            suppress = _make_record(msg)
            f(suppress)  # should suppress

            if cycle < 2:
                time.sleep(0.15)  # expire before next cycle

        assert all(p is True for p in passes)

    def test_reset_restores_first_emission_behaviour(self):
        """After reset(), the filter behaves as if newly created."""
        f = RateLimitFilter(period_sec=30)
        msg = "Index rebuild started"

        f(_make_record(msg))
        assert f(_make_record(msg)) is False  # suppressed

        f.reset()

        # After reset, message should pass again
        assert f(_make_record(msg)) is True
