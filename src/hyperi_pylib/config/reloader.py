#  Project:      hyperi-pylib
#  File:         reloader.py
#  Purpose:      Config reload wrapper with polling, callbacks, and SIGHUP handling
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Config Reloader -- wraps Dynaconf reload with polling and callbacks.

Mirrors rustlib's SharedConfig/ConfigReloader pattern. Provides:
- Periodic polling (configurable interval, 0 = disabled)
- on_reload callback after successful reload
- Optional validation before applying reload
- SIGHUP handler for immediate reload trigger (Unix only)
- Reload counters (success/error) for metrics integration
"""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReloaderConfig:
    """Configuration for the ConfigReloader.

    Attributes:
        poll_interval: Seconds between reload polls. 0 or negative disables polling.
        enable_sighup: Register SIGHUP handler for immediate reload (Unix only).
    """

    poll_interval: float = 5.0
    enable_sighup: bool = True


class ConfigReloader:
    """Watch for config changes and call callbacks on reload.

    Wraps Dynaconf's settings.reload() with periodic polling, validation,
    and callback support. Tracks success/error counts for metrics integration.
    """

    def __init__(
        self,
        config: ReloaderConfig | None = None,
        on_reload: Callable[[Any], None] | None = None,
        validate_fn: Callable[[Any], bool] | None = None,
    ) -> None:
        self._config = config or ReloaderConfig()
        self._on_reload = on_reload
        self._validate_fn = validate_fn
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._reload_count_success = 0
        self._reload_count_error = 0

    async def start(self) -> None:
        """Start the polling loop (async). Only polls if interval > 0."""
        if self._config.poll_interval <= 0:
            return
        self._running = True
        if self._config.enable_sighup:
            self._register_sighup()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def reload_now(self) -> bool:
        """Trigger an immediate reload. Returns True on success."""
        from hyperi_pylib.config import settings

        try:
            settings.reload()

            if self._validate_fn is not None and not self._validate_fn(settings):
                self._reload_count_error += 1
                logger.warning("Config reload validation failed")
                return False

            if self._on_reload is not None:
                self._on_reload(settings)

            self._reload_count_success += 1
            return True
        except Exception:
            self._reload_count_error += 1
            logger.exception("Config reload failed")
            return False

    @property
    def reload_count_success(self) -> int:
        """Number of successful reloads."""
        return self._reload_count_success

    @property
    def reload_count_error(self) -> int:
        """Number of failed reloads."""
        return self._reload_count_error

    async def _poll_loop(self) -> None:
        """Background polling task."""
        while self._running:
            await asyncio.sleep(self._config.poll_interval)
            if self._running:
                self.reload_now()

    def _register_sighup(self) -> None:
        """Register SIGHUP handler for manual reload trigger.

        No-op if enable_sighup is False or SIGHUP is unavailable (Windows).
        """
        if not self._config.enable_sighup:
            return
        try:
            signal.signal(signal.SIGHUP, lambda *_: self.reload_now())
        except (OSError, AttributeError):
            # SIGHUP not available on Windows or in some restricted environments
            pass
