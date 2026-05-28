#  Project:   hyperi-pylib
#  File:      tests/unit/test_resilience_composition.py
#  Purpose:   Lock in the "breaker OUTSIDE retry" composition order
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""S12 documentation-via-test: the recommended composition for
CircuitBreaker + stamina retry is BREAKER OUTSIDE RETRY. This file
locks in the rationale with concrete examples so a future reader can
see why -- and so accidental inversion in callers shows up loudly."""

from __future__ import annotations

import stamina

from hyperi_pylib.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


def _flaky(threshold: int):
    """Function that fails ``threshold`` times then succeeds."""
    calls = {"n": 0}

    def call():
        calls["n"] += 1
        if calls["n"] <= threshold:
            raise ConnectionError("upstream down")
        return "ok"

    return call, calls


_FAST = {"wait_initial": 0.001, "wait_max": 0.005, "wait_jitter": 0.001}


def test_breaker_outside_retry_one_failure_counts_as_one():
    """Recommended order: breaker counts the whole retry budget as ONE
    failure if every attempt fails. The breaker's failure_threshold
    correctly tracks "outage events", not "retry exhaustion events"."""
    cb = CircuitBreaker("outer", CircuitBreakerConfig(failure_threshold=2, reset_timeout=30.0))
    call, _ = _flaky(threshold=99)  # always fails

    for _ in range(2):  # two logical calls
        try:
            with cb:
                for attempt in stamina.retry_context(on=ConnectionError, attempts=2, **_FAST):
                    with attempt:
                        call()
        except Exception:
            pass

    # 2 logical calls failed -> breaker now OPEN (threshold=2)
    assert cb.state == CircuitState.OPEN
    assert cb._consecutive_failures == 2


def test_retry_outside_breaker_burns_retries_on_open_circuit():
    """Anti-pattern: retry outside breaker. Once the circuit opens,
    each retry attempt is rejected by the breaker -- still uses the
    retry budget. Documenting why this composition is wrong."""
    cb = CircuitBreaker("inner", CircuitBreakerConfig(failure_threshold=1, reset_timeout=30.0))
    cb.record_failure()  # open the breaker pre-test
    assert cb.state == CircuitState.OPEN

    rejections = {"n": 0}
    try:
        for attempt in stamina.retry_context(on=Exception, attempts=3, **_FAST):
            with attempt:
                rejections["n"] += 1
                with cb:
                    pass  # would have called downstream
    except Exception:
        pass
    # Each of N retry attempts hit the OPEN breaker.
    # Antipattern documented: retries wasted learning the circuit is open.
    assert rejections["n"] == 3


def test_breaker_outside_retry_eventual_success():
    """Recommended order: retries succeed within one breaker entry,
    breaker records SUCCESS (resets failure count)."""
    cb = CircuitBreaker("outer", CircuitBreakerConfig(failure_threshold=2, reset_timeout=30.0))
    cb.record_failure()  # one prior failure (under threshold)
    assert cb._consecutive_failures == 1

    call, calls = _flaky(threshold=1)  # fails once, then succeeds

    with cb:
        for attempt in stamina.retry_context(on=ConnectionError, attempts=3, **_FAST):
            with attempt:
                result = call()
                assert result == "ok"

    assert calls["n"] == 2  # one retry, second succeeded
    # Breaker saw the OVERALL success -> consecutive_failures reset to 0
    assert cb._consecutive_failures == 0
    assert cb.state == CircuitState.CLOSED
