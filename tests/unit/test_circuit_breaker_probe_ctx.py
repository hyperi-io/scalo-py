#  Project:   hyperi-pylib
#  File:      tests/unit/test_circuit_breaker_probe_ctx.py
#  Purpose:   Verify CircuitBreaker.probe() context manager releases on exception
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""S4 regression: the probe() context manager must release the slot
on exit even when the body raises -- prevents probe-slot leaks on
caller crash."""

from __future__ import annotations

import pytest

from hyperi_pylib.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


def _open_breaker(threshold: int = 1) -> CircuitBreaker:
    """Helper: trip a breaker to OPEN by recording threshold failures."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=threshold, reset_timeout=0.05))
    for _ in range(threshold):
        cb.record_failure()
    return cb


def _half_open(threshold: int = 1) -> CircuitBreaker:
    """Helper: get a breaker to HALF_OPEN."""
    import time

    cb = _open_breaker(threshold)
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)  # wait past reset_timeout
    assert cb.state == CircuitState.HALF_OPEN
    return cb


def test_probe_success_records_success_and_closes_circuit():
    cb = _half_open()
    with cb.probe() as acquired:
        assert acquired is True
    assert cb.state == CircuitState.CLOSED


def test_probe_exception_records_failure_and_reopens():
    cb = _half_open()
    with pytest.raises(ValueError), cb.probe() as acquired:
        assert acquired is True
        raise ValueError("downstream failed")
    # HALF_OPEN + record_failure -> OPEN
    assert cb.state == CircuitState.OPEN


def test_probe_when_open_yields_false():
    cb = _open_breaker()
    # State is OPEN, before reset_timeout elapses
    with cb.probe() as acquired:
        assert acquired is False
        # body still runs; caller branches on flag
    # State unchanged
    assert cb.state == CircuitState.OPEN


def test_probe_slot_released_on_exception_no_leak():
    """Two probe slots, first raises, second should still be available."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.05, half_open_max_calls=2))
    cb.record_failure()
    import time

    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN

    # First probe raises -> should record failure -> OPEN
    with pytest.raises(RuntimeError), cb.probe():
        raise RuntimeError("first probe failed")
    assert cb.state == CircuitState.OPEN

    # Slot accounting was released (record_failure resets the counter
    # as part of OPEN transition), so no leaked counter remains.
    # We can't easily inspect _half_open_calls from outside, but the
    # state transition itself is the canonical signal: HALF_OPEN +
    # failure -> OPEN with clean state.
    assert cb._half_open_calls == 0


def test_probe_closed_circuit_just_records_success():
    """CLOSED state -> probe() acquires (no slot accounting) -> on success,
    consecutive_failures resets to 0."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))
    # accumulate a few failures (still under threshold)
    cb.record_failure()
    cb.record_failure()
    assert cb._consecutive_failures == 2

    with cb.probe() as acquired:
        assert acquired is True

    # Success in CLOSED state resets the counter
    assert cb._consecutive_failures == 0
