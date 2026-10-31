#  Project:   scalo
#  File:      tests/unit/test_secrets_health_log.py
#  Purpose:   HealthLog writes one warning per outage and one INFO on recovery, with the reason masked
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``HealthLog`` is the one place every provider's health transitions are logged.

The aws, gcp, azure and openbao providers hand it a probe, and the kubernetes provider hands it a reason. GCP
and Azure have no offline backend that answers a health check, so a probe that a test flips between failing and
passing stands in for the backend here, and the recovery line is proved on that.
"""

import asyncio
import logging
import threading

import pytest

from scalo.secrets.providers.base import HealthLog

_LOGGER = "scalo.test.health"

# Built at run time so no source-scanning tool sees a credential in the file.
_PASSWORD = "pw" + "-sentinel-" + "7f3a91"
_TOKEN = "tok" + "-sentinel-" + "c20b64"


@pytest.fixture(autouse=True)
def _capture(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER)


@pytest.fixture
def health() -> HealthLog:
    return HealthLog(logging.getLogger(_LOGGER), "demo")


def _logged(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno == level]


class _Probe:
    """A backend a test switches between failing and passing."""

    def __init__(self) -> None:
        self.failure: str | BaseException | None = None

    def sync(self) -> str | None:
        if isinstance(self.failure, BaseException):
            raise self.failure
        return self.failure

    async def asynchronous(self) -> str | None:
        return self.sync()


class TestTransitions:
    def test_a_failure_that_repeats_logs_once_and_the_first_pass_logs_the_recovery(self, health, caplog):
        for _ in range(3):
            assert health.record("refused") is False
        assert health.record(None) is True
        assert health.record(None) is True

        assert _logged(caplog, logging.WARNING) == ["Health check of provider demo failed: refused"]
        assert _logged(caplog, logging.INFO) == ["Health check of provider demo passes again"]

    def test_a_provider_that_starts_healthy_logs_nothing(self, health, caplog):
        assert health.record(None) is True
        assert health.record(None) is True

        assert [r for r in caplog.records if r.name == _LOGGER] == []

    def test_each_outage_logs_its_own_warning(self, health, caplog):
        health.record("first")
        health.record(None)
        health.record("second")

        assert [m.rsplit(": ", 1)[1] for m in _logged(caplog, logging.WARNING)] == ["first", "second"]

    def test_an_exception_reads_as_its_type_and_message(self, health, caplog):
        health.record(ConnectionRefusedError("vault.internal:8200 refused"))

        assert _logged(caplog, logging.WARNING)[0].endswith(": ConnectionRefusedError: vault.internal:8200 refused")

    def test_an_exception_with_no_message_reads_as_its_type(self, health, caplog):
        health.record(TimeoutError())

        assert _logged(caplog, logging.WARNING)[0].endswith(": TimeoutError")

    async def test_the_async_record_makes_the_same_transitions(self, health, caplog):
        results = [
            await health.arecord("refused"),
            await health.arecord("refused"),
            await health.arecord(None),
            await health.arecord(None),
        ]

        assert results == [False, False, True, True]
        assert _logged(caplog, logging.WARNING) == ["Health check of provider demo failed: refused"]
        assert len(_logged(caplog, logging.INFO)) == 1


class _HeldScrubber:
    """A scrubber whose scrub stays in flight until the test releases it."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def scrub(self, text: str) -> str:
        self.entered.set()
        self.release.wait(30)
        return text


class TestCancelledWhileMasking:
    """A readiness check runs under a timeout, and masking runs on a worker thread that outlives a cancel."""

    async def test_the_next_failed_check_announces_the_outage(self, health, caplog, monkeypatch):
        held = _HeldScrubber()
        monkeypatch.setattr("scalo.secrets.providers.base._fault_scrubber", lambda: held)

        check = asyncio.create_task(health.arecord("refused"))
        await asyncio.to_thread(held.entered.wait)
        check.cancel()
        held.release.set()
        with pytest.raises(asyncio.CancelledError):
            await check
        assert _logged(caplog, logging.WARNING) == []
        monkeypatch.undo()

        assert await health.arecord("refused") is False
        assert await health.arecord("refused") is False
        assert _logged(caplog, logging.WARNING) == ["Health check of provider demo failed: refused"]


class TestRun:
    def test_a_probe_that_raises_is_a_failure_and_one_that_returns_nothing_passes(self, health, caplog):
        probe = _Probe()

        probe.failure = OSError("unreachable")
        assert health.run(probe.sync) is False
        assert health.run(probe.sync) is False
        probe.failure = None
        assert health.run(probe.sync) is True

        assert len(_logged(caplog, logging.WARNING)) == 1
        assert "OSError: unreachable" in _logged(caplog, logging.WARNING)[0]
        assert len(_logged(caplog, logging.INFO)) == 1

    def test_a_probe_that_returns_a_reason_is_a_failure(self, health, caplog):
        probe = _Probe()
        probe.failure = "answered 503 (sealed)"

        assert health.run(probe.sync) is False
        assert _logged(caplog, logging.WARNING) == ["Health check of provider demo failed: answered 503 (sealed)"]

    async def test_the_async_probe_does_the_same(self, health, caplog):
        probe = _Probe()

        probe.failure = OSError("unreachable")
        assert await health.arun(probe.asynchronous) is False
        assert await health.arun(probe.asynchronous) is False
        probe.failure = None
        assert await health.arun(probe.asynchronous) is True
        assert await health.arun(probe.asynchronous) is True

        assert len(_logged(caplog, logging.WARNING)) == 1
        assert len(_logged(caplog, logging.INFO)) == 1

    async def test_a_cancelled_probe_is_not_a_failure(self, health, caplog):
        probe = _Probe()
        probe.failure = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await health.arun(probe.asynchronous)

        assert [r for r in caplog.records if r.name == _LOGGER] == []


class TestReasonIsMasked:
    @staticmethod
    def _leaky() -> OSError:
        return OSError(f"GET https://svc:{_PASSWORD}@vault.internal:8200/v1/sys/health failed, token={_TOKEN}")

    @staticmethod
    def _assert_masked(caplog: pytest.LogCaptureFixture) -> None:
        warnings = _logged(caplog, logging.WARNING)
        assert len(warnings) == 1
        assert _PASSWORD not in caplog.text, "a URL password reached the log"
        assert _TOKEN not in caplog.text, "a token reached the log"
        assert "REDACTED" in warnings[0]
        assert "vault.internal:8200" in warnings[0], "masking removed the host that says where it failed"

    def test_a_raised_fault(self, health, caplog):
        health.record(self._leaky())

        self._assert_masked(caplog)

    def test_a_reason_given_as_text(self, health, caplog):
        health.record(str(self._leaky()))

        self._assert_masked(caplog)

    async def test_on_the_async_path(self, health, caplog):
        await health.arecord(self._leaky())

        self._assert_masked(caplog)
