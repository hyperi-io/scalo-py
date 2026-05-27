#  Project:   hyperi-pylib
#  File:      tests/unit/test_harness_silent_timeout.py
#  Purpose:   smart_run must enforce timeouts even when child is silent
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""smart_run must terminate silent children at activity/total timeout."""

from __future__ import annotations

import sys
import time

from hyperi_pylib.harness.harness import (
    ActivityIndicator,
    SmartTimeoutMonitor,
    TerminationReason,
)


def test_silent_child_terminates_near_activity_timeout(tmp_path):
    """A 3s silent child with activity_timeout=1 must terminate around
    1s (NO_ACTIVITY), NOT run to natural completion."""
    monitor = SmartTimeoutMonitor(activity_timeout=1, total_timeout=10)

    t0 = time.monotonic()
    result = monitor.run_with_smart_timeout(
        command=[sys.executable, "-c", "import time; time.sleep(3)"],
        activity_indicators=ActivityIndicator(),
    )
    elapsed = time.monotonic() - t0

    assert result.termination_reason == TerminationReason.NO_ACTIVITY, (
        f"expected NO_ACTIVITY, got {result.termination_reason}; elapsed={elapsed:.2f}"
    )
    assert 0.8 < elapsed < 2.5, f"elapsed {elapsed:.2f}s outside expected window"


def test_silent_child_terminates_near_total_timeout(tmp_path):
    """If total_timeout fires before activity_timeout (total=1, activity=10),
    we get TOTAL_EXECUTION near total deadline."""
    monitor = SmartTimeoutMonitor(activity_timeout=10, total_timeout=1)

    t0 = time.monotonic()
    result = monitor.run_with_smart_timeout(
        command=[sys.executable, "-c", "import time; time.sleep(5)"],
        activity_indicators=ActivityIndicator(),
    )
    elapsed = time.monotonic() - t0

    assert result.termination_reason == TerminationReason.TOTAL_EXECUTION
    assert 0.8 < elapsed < 2.5, f"elapsed {elapsed:.2f}s outside expected window"


def test_chatty_child_completes_normally():
    """Sanity: a child producing output regularly is NOT killed by
    activity_timeout, even when it runs longer than activity_timeout
    in elapsed terms."""
    monitor = SmartTimeoutMonitor(activity_timeout=0.5, total_timeout=10.0)

    # Print every 100ms for 1s total -- each print resets the activity clock
    script = "import time; [print(f'tick {i}', flush=True) or time.sleep(0.1) for i in range(10)]"
    result = monitor.run_with_smart_timeout(
        command=[sys.executable, "-c", script],
        activity_indicators=ActivityIndicator(),
    )

    assert result.termination_reason == TerminationReason.COMPLETED
    assert result.return_code == 0
    assert "tick 0" in result.final_output
    assert "tick 9" in result.final_output


def test_activity_timeout_resets_on_each_line():
    """A child that prints once after 0.3s, then sleeps silently for
    1.5s, with activity_timeout=0.8: first 0.3s of silence are under
    budget; the print resets the clock; then 1.5s silence > 0.8s ->
    NO_ACTIVITY."""
    monitor = SmartTimeoutMonitor(activity_timeout=0.8, total_timeout=10.0)

    script = "import time, sys; time.sleep(0.3); print('hello', flush=True); time.sleep(1.5)"
    t0 = time.monotonic()
    result = monitor.run_with_smart_timeout(
        command=[sys.executable, "-c", script],
        activity_indicators=ActivityIndicator(),
    )
    elapsed = time.monotonic() - t0

    assert result.termination_reason == TerminationReason.NO_ACTIVITY
    # Should fire at ~0.3 (print) + 0.8 (activity budget) = ~1.1s
    assert 0.9 < elapsed < 2.0, f"elapsed {elapsed:.2f}s outside expected window"
    assert "hello" in result.final_output
