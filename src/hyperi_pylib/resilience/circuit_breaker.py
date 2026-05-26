#  Project:      hyperi-pylib
#  File:         src/hyperi_pylib/resilience/circuit_breaker.py
#  Purpose:      Circuit breaker matching rustlib Closed/Open/HalfOpen state machine
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Circuit breaker matching rustlib ``src/resilience/circuit_breaker.rs``.

State machine:
    CLOSED -> OPEN:      consecutive_failures >= failure_threshold
    OPEN -> HALF_OPEN:   reset_timeout elapsed since last failure
    HALF_OPEN -> CLOSED: record_success() called
    HALF_OPEN -> OPEN:   record_failure() called

Thread-safe via ``threading.Lock`` -- safe for concurrent access from
multiple threads or async tasks.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import StrEnum


class CircuitState(StrEnum):
    """Circuit breaker states matching rustlib."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker thresholds and timeouts."""

    failure_threshold: int = 5
    """Consecutive failures before opening the circuit."""

    reset_timeout: float = 30.0
    """Seconds to wait in OPEN before trying HALF_OPEN."""

    half_open_max_calls: int = 1
    """Number of probe calls allowed in HALF_OPEN state."""


class CircuitBreakerError(Exception):
    """Raised when a call is rejected by an open circuit."""


class CircuitBreaker:
    """
    Circuit breaker with Closed/Open/HalfOpen state machine.

    Usage as context manager::

        cb = CircuitBreaker("payments", CircuitBreakerConfig(failure_threshold=3))

        with cb:
            response = call_downstream()

        # or async
        async with cb:
            response = await call_downstream()
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    @property
    def name(self) -> str:
        """Name identifying this circuit breaker instance."""
        return self._name

    @property
    def state(self) -> CircuitState:
        """
        Current circuit state.

        Auto-transitions OPEN -> HALF_OPEN when reset_timeout has elapsed.
        """
        with self._lock:
            return self._evaluate_state()

    def is_call_permitted(self) -> bool:
        """Advisory check; does NOT reserve a slot.

        TOCTOU-prone in HALF_OPEN under concurrency. Use ``with breaker:``
        or :meth:`try_acquire_probe` for atomic admission.
        """
        with self._lock:
            current = self._evaluate_state()
            if current == CircuitState.CLOSED:
                return True
            if current == CircuitState.HALF_OPEN:
                return self._half_open_calls < self._config.half_open_max_calls
            return False

    def try_acquire_probe(self) -> bool:
        """Atomically reserve a HALF_OPEN probe slot.

        On True the caller MUST eventually call :meth:`record_success` or
        :meth:`record_failure`. CLOSED returns True (no slot accounting);
        OPEN returns False.
        """
        with self._lock:
            current = self._evaluate_state()
            if current == CircuitState.CLOSED:
                return True
            if current == CircuitState.OPEN:
                return False
            # HALF_OPEN
            if self._half_open_calls >= self._config.half_open_max_calls:
                return False
            self._half_open_calls += 1
            return True

    def record_success(self) -> None:
        """
        Record a successful call.

        CLOSED: resets consecutive failure count.
        HALF_OPEN: transitions to CLOSED, resets failure count.
        """
        with self._lock:
            current = self._evaluate_state()
            if current == CircuitState.CLOSED:
                self._consecutive_failures = 0
            elif current == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0
                self._half_open_calls = 0

    def record_failure(self) -> None:
        """
        Record a failed call.

        CLOSED: increments failure count; opens circuit at threshold.
        HALF_OPEN: transitions to OPEN immediately.
        """
        with self._lock:
            current = self._evaluate_state()
            if current == CircuitState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._config.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_failure_time = time.monotonic()
            elif current == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                self._half_open_calls = 0

    def reset(self) -> None:
        """Force the circuit back to CLOSED, clearing all counters."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_calls = 0

    # -- Sync context manager --

    def __enter__(self) -> CircuitBreaker:
        with self._lock:
            current = self._evaluate_state()
            if current == CircuitState.OPEN:
                raise CircuitBreakerError(f"Circuit breaker '{self._name}' is OPEN -- call rejected")
            if current == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._config.half_open_max_calls:
                    raise CircuitBreakerError(f"Circuit breaker '{self._name}' is HALF_OPEN -- max probe calls reached")
                self._half_open_calls += 1
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> bool:
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        # Never swallow the exception
        return False

    # -- Async context manager --

    async def __aenter__(self) -> CircuitBreaker:
        # Delegate to sync -- lock acquisition is fast, no I/O
        return self.__enter__()

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)

    # -- Internal --

    def _evaluate_state(self) -> CircuitState:
        """
        Evaluate and potentially transition state.

        Must be called with ``self._lock`` held.
        """
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._config.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state
