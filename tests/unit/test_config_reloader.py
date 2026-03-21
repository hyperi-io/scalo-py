#  Project:      hyperi-pylib
#  File:         test_config_reloader.py
#  Purpose:      Tests for ConfigReloader — config reload with polling and callbacks
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for ConfigReloader."""

import asyncio
import signal
import sys

import pytest

from hyperi_pylib.config.reloader import ConfigReloader, ReloaderConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CallTracker:
    """Track callback invocations with the settings object passed."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, settings: object) -> None:
        self.calls.append(settings)

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ---------------------------------------------------------------------------
# reload_now() — callback behaviour
# ---------------------------------------------------------------------------


class TestReloadNowCallback:
    """reload_now() calls on_reload callback after successful reload."""

    def test_on_reload_called_on_success(self) -> None:
        tracker = CallTracker()
        reloader = ConfigReloader(on_reload=tracker)

        result = reloader.reload_now()

        assert result is True
        assert tracker.call_count == 1

    def test_on_reload_receives_settings_object(self) -> None:
        from hyperi_pylib.config import settings

        tracker = CallTracker()
        reloader = ConfigReloader(on_reload=tracker)
        reloader.reload_now()

        assert tracker.calls[0] is settings

    def test_no_callback_still_succeeds(self) -> None:
        reloader = ConfigReloader()
        result = reloader.reload_now()
        assert result is True


# ---------------------------------------------------------------------------
# reload_now() — validation function
# ---------------------------------------------------------------------------


class TestReloadNowValidation:
    """reload_now() respects validate_fn — returns False on validation failure."""

    def test_validation_pass_triggers_callback(self) -> None:
        tracker = CallTracker()
        reloader = ConfigReloader(
            on_reload=tracker,
            validate_fn=lambda _s: True,
        )

        result = reloader.reload_now()

        assert result is True
        assert tracker.call_count == 1

    def test_validation_fail_blocks_callback(self) -> None:
        tracker = CallTracker()
        reloader = ConfigReloader(
            on_reload=tracker,
            validate_fn=lambda _s: False,
        )

        result = reloader.reload_now()

        assert result is False
        assert tracker.call_count == 0

    def test_validation_fail_increments_error_counter(self) -> None:
        reloader = ConfigReloader(validate_fn=lambda _s: False)
        reloader.reload_now()

        assert reloader.reload_count_error == 1
        assert reloader.reload_count_success == 0


# ---------------------------------------------------------------------------
# reload_now() — exception handling
# ---------------------------------------------------------------------------


class TestReloadNowExceptions:
    """reload_now() handles exceptions gracefully without crashing."""

    def test_callback_exception_returns_false(self) -> None:
        def bad_callback(_s: object) -> None:
            raise RuntimeError("callback exploded")

        reloader = ConfigReloader(on_reload=bad_callback)
        result = reloader.reload_now()

        assert result is False
        assert reloader.reload_count_error == 1

    def test_validate_exception_returns_false(self) -> None:
        def bad_validate(_s: object) -> bool:
            raise ValueError("validation exploded")

        reloader = ConfigReloader(validate_fn=bad_validate)
        result = reloader.reload_now()

        assert result is False
        assert reloader.reload_count_error == 1


# ---------------------------------------------------------------------------
# Reload counters
# ---------------------------------------------------------------------------


class TestReloadCounters:
    """Reload counters track success and error counts."""

    def test_initial_counters_are_zero(self) -> None:
        reloader = ConfigReloader()
        assert reloader.reload_count_success == 0
        assert reloader.reload_count_error == 0

    def test_success_counter_increments(self) -> None:
        reloader = ConfigReloader()
        reloader.reload_now()
        reloader.reload_now()
        reloader.reload_now()

        assert reloader.reload_count_success == 3
        assert reloader.reload_count_error == 0

    def test_error_counter_increments(self) -> None:
        reloader = ConfigReloader(validate_fn=lambda _s: False)
        reloader.reload_now()
        reloader.reload_now()

        assert reloader.reload_count_error == 2
        assert reloader.reload_count_success == 0

    def test_mixed_success_and_error(self) -> None:
        call_count = 0

        def alternating_validate(_s: object) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count % 2 == 1

        reloader = ConfigReloader(validate_fn=alternating_validate)
        reloader.reload_now()  # pass (call 1)
        reloader.reload_now()  # fail (call 2)
        reloader.reload_now()  # pass (call 3)

        assert reloader.reload_count_success == 2
        assert reloader.reload_count_error == 1


# ---------------------------------------------------------------------------
# start() / stop() — async lifecycle
# ---------------------------------------------------------------------------


class TestAsyncLifecycle:
    """start() and stop() manage the async polling loop."""

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        tracker = CallTracker()
        config = ReloaderConfig(poll_interval=0.05)
        reloader = ConfigReloader(config=config, on_reload=tracker)

        await reloader.start()
        # Let at least one poll cycle run
        await asyncio.sleep(0.15)
        await reloader.stop()

        assert tracker.call_count >= 1

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        config = ReloaderConfig(poll_interval=0.05)
        reloader = ConfigReloader(config=config)

        await reloader.start()
        await asyncio.sleep(0.1)
        await reloader.stop()
        # Second stop should not raise
        await reloader.stop()

    @pytest.mark.asyncio
    async def test_poll_interval_zero_disables_polling(self) -> None:
        tracker = CallTracker()
        config = ReloaderConfig(poll_interval=0.0)
        reloader = ConfigReloader(config=config, on_reload=tracker)

        await reloader.start()
        await asyncio.sleep(0.1)
        await reloader.stop()

        # No polling should have occurred
        assert tracker.call_count == 0

    @pytest.mark.asyncio
    async def test_negative_poll_interval_disables_polling(self) -> None:
        tracker = CallTracker()
        config = ReloaderConfig(poll_interval=-1.0)
        reloader = ConfigReloader(config=config, on_reload=tracker)

        await reloader.start()
        await asyncio.sleep(0.1)
        await reloader.stop()

        assert tracker.call_count == 0


# ---------------------------------------------------------------------------
# SIGHUP registration
# ---------------------------------------------------------------------------


class TestSighupRegistration:
    """SIGHUP registration doesn't crash on platforms without SIGHUP."""

    def test_sighup_registration_no_crash(self) -> None:
        config = ReloaderConfig(enable_sighup=True)
        reloader = ConfigReloader(config=config)

        # _register_sighup should not raise on any platform
        reloader._register_sighup()

    def test_sighup_disabled_skips_registration(self) -> None:
        config = ReloaderConfig(enable_sighup=False)
        reloader = ConfigReloader(config=config)

        # Should be a no-op
        reloader._register_sighup()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="SIGHUP not available on Windows",
    )
    def test_sighup_triggers_reload(self) -> None:
        tracker = CallTracker()
        config = ReloaderConfig(enable_sighup=True)
        reloader = ConfigReloader(config=config, on_reload=tracker)
        reloader._register_sighup()

        # Send SIGHUP to ourselves
        import os

        os.kill(os.getpid(), signal.SIGHUP)

        assert tracker.call_count == 1
        assert reloader.reload_count_success == 1


# ---------------------------------------------------------------------------
# ReloaderConfig defaults
# ---------------------------------------------------------------------------


class TestReloaderConfig:
    """ReloaderConfig has sensible defaults."""

    def test_defaults(self) -> None:
        config = ReloaderConfig()
        assert config.poll_interval == 5.0
        assert config.enable_sighup is True

    def test_custom_values(self) -> None:
        config = ReloaderConfig(poll_interval=10.0, enable_sighup=False)
        assert config.poll_interval == 10.0
        assert config.enable_sighup is False
