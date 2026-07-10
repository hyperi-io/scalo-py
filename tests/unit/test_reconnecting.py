"""Unit tests for scalo.resilience.ReconnectingResilience.

Uses an injectable fake clock so back-off never really sleeps and never races a
wall clock.
"""

import pytest

from scalo.resilience import (
    OutageState,
    ReconnectingResilience,
    ResilienceConfig,
    ServiceUnavailable,
)


class FakeClock:
    """Injectable clock: sleep advances a virtual monotonic clock."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _build(clock, *, config=None, reconnect=None, on_connect_failure=None):
    return ReconnectingResilience(
        config or ResilienceConfig(wait_initial=0.5, wait_max=2.0, budget_seconds=10.0),
        name="Test",
        is_transient=lambda e: isinstance(e, ConnectionError),
        is_reconnectable=lambda e: isinstance(e, ConnectionError),
        reconnect=reconnect or (lambda: None),
        on_connect_failure=on_connect_failure,
        sleep=clock.sleep,
        now=clock.now,
    )


def test_success_first_try_is_healthy():
    r = _build(FakeClock())
    assert r.run(lambda: 42) == 42
    assert r.state is OutageState.HEALTHY
    assert r.healthy


def test_non_transient_error_reraises_immediately():
    r = _build(FakeClock())

    def op():
        raise ValueError("logic error, not a connection outage")

    with pytest.raises(ValueError):
        r.run(op)
    assert r.state is OutageState.HEALTHY  # untouched by a non-transient error


def test_transient_outage_reconnects_and_recovers():
    clock = FakeClock()
    counts = {"op": 0, "reconnect": 0}

    def op():
        counts["op"] += 1
        if counts["op"] < 3:
            raise ConnectionError("down")
        return "ok"

    def reconnect():
        counts["reconnect"] += 1

    r = _build(clock, reconnect=reconnect)
    assert r.run(op) == "ok"
    assert counts["op"] == 3
    assert counts["reconnect"] == 2  # pool rebuilt before each retry
    assert r.state is OutageState.HEALTHY


def test_budget_exhausted_raises_unavailable_and_marks_dead():
    r = _build(
        FakeClock(),
        config=ResilienceConfig(wait_initial=1.0, wait_max=1.0, budget_seconds=3.0),
    )

    def always_down():
        raise ConnectionError("down")

    with pytest.raises(ServiceUnavailable) as ei:
        r.run(always_down)
    assert ei.value.waking is False
    assert r.state is OutageState.DEAD


def test_warm_up_hook_flags_waking_and_extends_budget():
    clock = FakeClock()
    cfg = ResilienceConfig(wait_initial=1.0, wait_max=1.0, budget_seconds=2.0, waking_budget_seconds=6.0)

    def op():
        # keeps failing until t >= 4.0: past the 2s plain budget, inside the 6s
        # waking budget - so it only survives BECAUSE the wake extended the budget.
        if clock.now() < 4.0:
            raise ConnectionError("cold start")
        return "warm"

    r = _build(clock, config=cfg, on_connect_failure=lambda: True)
    assert r.run(op) == "warm"


def test_disabled_config_passes_through_raw():
    r = _build(FakeClock(), config=ResilienceConfig(enabled=False))

    def op():
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        r.run(op)  # disabled: no retry, the raw error surfaces
