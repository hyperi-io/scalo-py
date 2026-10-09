"""Unit tests for scalo.resilience.ReconnectingResilience.

Uses an injectable fake clock so back-off never really sleeps and never races a
wall clock.
"""

import pytest

from scalo.logger import logger
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


@pytest.fixture
def records():
    """Every record logged while the test runs."""
    seen: list[dict] = []
    sink_id = logger.add(lambda message: seen.append(message.record), level="DEBUG")
    yield seen
    logger.remove(sink_id)


def _logged(records: list[dict], message: str) -> dict:
    return next(record for record in records if record["message"] == message)


def _always_down(calls: list[int]):
    def op():
        calls.append(1)
        raise ConnectionError("down")

    return op


def test_a_zero_budget_reports_the_one_attempt_it_made(records):
    """No budget still makes the first call: the message and the log say one, not zero."""
    calls: list[int] = []
    r = _build(FakeClock(), config=ResilienceConfig(budget_seconds=0.0))

    with pytest.raises(ServiceUnavailable) as ei:
        r.run(_always_down(calls))

    assert len(calls) == 1
    assert str(ei.value) == "Test unreachable after 0s (1 attempt): down"
    assert _logged(records, "Test unavailable after resilience budget exhausted")["extra"]["attempts"] == 1


def test_an_exhausted_budget_reports_every_attempt_it_made(records):
    """The first call and each retry inside the budget all count."""
    calls: list[int] = []
    r = _build(
        FakeClock(),
        config=ResilienceConfig(wait_initial=1.0, wait_max=1.0, budget_seconds=3.0),
    )

    with pytest.raises(ServiceUnavailable) as ei:
        r.run(_always_down(calls))

    assert len(calls) == 4
    assert str(ei.value) == "Test unreachable after 3s (4 attempts): down"
    assert _logged(records, "Test unavailable after resilience budget exhausted")["extra"]["attempts"] == 4


def test_a_recovery_reports_every_attempt_it_took(records):
    """Two failures then a success is three attempts."""
    calls: list[int] = []

    def op():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("down")
        return "ok"

    assert _build(FakeClock()).run(op) == "ok"
    assert len(calls) == 3
    assert _logged(records, "Test recovered")["extra"]["attempts"] == 3


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
