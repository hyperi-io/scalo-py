#  Project:   scalo
#  File:      tests/unit/test_secrets_manager_health.py
#  Purpose:   SecretsManager health checks say why a provider is unhealthy, without leaking a secret
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``SecretsManager.health_check`` and ``health_check_sync`` log why a provider's check raised.

A provider whose health check raises is reported ``False``. The manager also logs one warning naming the
provider and the error type, with the message masked, and stays quiet while the same fault repeats.
"""

import logging

import pytest

from scalo.secrets.manager import SecretsManager
from scalo.secrets.providers.file import FileProvider
from scalo.secrets.types import CacheConfig

_MANAGER_LOGGER = "scalo.secrets.manager"

# Built at run time so no source-scanning tool sees a credential in the file.
_PASSWORD = "pw" + "-sentinel-" + "7f3a91"
_TOKEN = "tok" + "-sentinel-" + "c20b64"


class _Unhealthy(FileProvider):
    """A file provider whose health check raises whatever it is told to, or passes when told nothing."""

    def __init__(self) -> None:
        super().__init__()
        self.fault: Exception | None = None

    async def health_check_async(self) -> bool:
        return self.health_check_sync()

    def health_check_sync(self) -> bool:
        if self.fault is not None:
            raise self.fault
        return True


def _manager(provider: _Unhealthy) -> SecretsManager:
    return SecretsManager(
        providers={"openbao": provider},
        cache_config=CacheConfig(enabled=False),
    )


def _health_records(caplog: pytest.LogCaptureFixture, level: int) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _MANAGER_LOGGER and r.levelno == level]


@pytest.fixture(autouse=True)
def _capture_manager_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_MANAGER_LOGGER)


class TestFaultIsLogged:
    def test_sync_logs_one_warning_naming_provider_and_error_type(self, caplog):
        provider = _Unhealthy()
        provider.fault = ConnectionRefusedError("vault.internal:8200 refused the connection")

        result = _manager(provider).health_check_sync()

        assert result["openbao"] is False
        warnings = _health_records(caplog, logging.WARNING)
        assert len(warnings) == 1, f"expected one warning, got {[r.getMessage() for r in warnings]}"
        message = warnings[0].getMessage()
        assert "openbao" in message
        assert "ConnectionRefusedError" in message
        assert "vault.internal:8200 refused the connection" in message

    async def test_async_logs_one_warning_naming_provider_and_error_type(self, caplog):
        provider = _Unhealthy()
        provider.fault = TimeoutError("no answer in 30s")

        result = await _manager(provider).health_check()

        assert result["openbao"] is False
        warnings = _health_records(caplog, logging.WARNING)
        assert len(warnings) == 1, f"expected one warning, got {[r.getMessage() for r in warnings]}"
        message = warnings[0].getMessage()
        assert "openbao" in message
        assert "TimeoutError" in message
        assert "no answer in 30s" in message

    def test_a_healthy_provider_beside_a_faulty_one_is_still_reported(self, caplog):
        faulty = _Unhealthy()
        faulty.fault = OSError("unreachable")
        manager = SecretsManager(
            providers={"openbao": faulty, "file": FileProvider()},
            cache_config=CacheConfig(enabled=False),
        )

        assert manager.health_check_sync() == {"file": True, "openbao": False}
        warnings = _health_records(caplog, logging.WARNING)
        assert len(warnings) == 1
        assert "openbao" in warnings[0].getMessage()


class TestMessageIsMasked:
    @staticmethod
    def _leaky_fault() -> OSError:
        return OSError(f"GET https://svc:{_PASSWORD}@vault.internal:8200/v1/sys/health failed, token={_TOKEN}")

    @staticmethod
    def _assert_masked(caplog: pytest.LogCaptureFixture) -> None:
        warnings = _health_records(caplog, logging.WARNING)
        assert len(warnings) == 1
        everything = " ".join([warnings[0].getMessage(), str(warnings[0].args), caplog.text])
        assert _PASSWORD not in everything, "a URL password reached the log"
        assert _TOKEN not in everything, "a token reached the log"
        assert "REDACTED" in warnings[0].getMessage()
        assert "vault.internal:8200" in warnings[0].getMessage(), "masking removed the host that says where it failed"

    def test_sync(self, caplog):
        provider = _Unhealthy()
        provider.fault = self._leaky_fault()

        _manager(provider).health_check_sync()

        self._assert_masked(caplog)

    async def test_async(self, caplog):
        provider = _Unhealthy()
        provider.fault = self._leaky_fault()

        await _manager(provider).health_check()

        self._assert_masked(caplog)


class TestUnmaskableMessageIsWithheld:
    def test_a_scrubber_fault_logs_no_message_and_still_reports_false(self, caplog, monkeypatch):
        def _broken():
            raise RuntimeError("scrubber rules failed to load")

        monkeypatch.setattr("scalo.secrets.manager._fault_scrubber", _broken)
        provider = _Unhealthy()
        provider.fault = OSError(f"token={_TOKEN}")

        result = _manager(provider).health_check_sync()

        assert result["openbao"] is False
        warnings = _health_records(caplog, logging.WARNING)
        assert len(warnings) == 1
        assert _TOKEN not in warnings[0].getMessage()
        assert "withheld" in warnings[0].getMessage()
        assert "OSError" in warnings[0].getMessage()


class TestRepeatedFaultDoesNotFloodTheLog:
    """A readiness probe calls this every few seconds, so one outage is one line."""

    def test_same_error_type_logs_once(self, caplog):
        provider = _Unhealthy()
        provider.fault = ConnectionRefusedError("refused")
        manager = _manager(provider)

        for _ in range(5):
            assert manager.health_check_sync()["openbao"] is False

        assert len(_health_records(caplog, logging.WARNING)) == 1

    async def test_same_error_type_logs_once_on_the_async_path(self, caplog):
        provider = _Unhealthy()
        provider.fault = ConnectionRefusedError("refused")
        manager = _manager(provider)

        for _ in range(5):
            assert (await manager.health_check())["openbao"] is False

        assert len(_health_records(caplog, logging.WARNING)) == 1

    def test_a_different_error_type_is_logged_again(self, caplog):
        provider = _Unhealthy()
        manager = _manager(provider)

        provider.fault = ConnectionRefusedError("refused")
        manager.health_check_sync()
        provider.fault = PermissionError("token expired")
        manager.health_check_sync()

        messages = [r.getMessage() for r in _health_records(caplog, logging.WARNING)]
        assert len(messages) == 2
        assert "ConnectionRefusedError" in messages[0]
        assert "PermissionError" in messages[1]

    def test_recovery_is_logged_once_and_a_later_fault_warns_again(self, caplog):
        provider = _Unhealthy()
        manager = _manager(provider)

        provider.fault = ConnectionRefusedError("refused")
        manager.health_check_sync()
        provider.fault = None
        assert manager.health_check_sync()["openbao"] is True
        assert manager.health_check_sync()["openbao"] is True
        provider.fault = ConnectionRefusedError("refused again")
        manager.health_check_sync()

        assert len(_health_records(caplog, logging.WARNING)) == 2
        recoveries = _health_records(caplog, logging.INFO)
        assert len(recoveries) == 1
        assert "openbao" in recoveries[0].getMessage()
