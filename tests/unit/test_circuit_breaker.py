#  Project:      hyperi-pylib
#  File:         tests/unit/test_circuit_breaker.py
#  Purpose:      Tests for circuit breaker matching rustlib state machine
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for circuit breaker — Closed/Open/HalfOpen state machine."""

import asyncio
import threading
import time

import pytest

from hyperi_pylib.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError, CircuitState


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig defaults and custom values."""

    def test_default_values(self):
        """Default config has sensible production values."""
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.reset_timeout == 30.0
        assert cfg.half_open_max_calls == 1

    def test_custom_values(self):
        """Custom config values are stored correctly."""
        cfg = CircuitBreakerConfig(failure_threshold=3, reset_timeout=10.0, half_open_max_calls=2)
        assert cfg.failure_threshold == 3
        assert cfg.reset_timeout == 10.0
        assert cfg.half_open_max_calls == 2


class TestCircuitBreakerInitialState:
    """Test initial state and properties."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker("test-service")
        assert cb.state == CircuitState.CLOSED

    def test_name_property(self):
        """Name property returns the configured name."""
        cb = CircuitBreaker("my-downstream")
        assert cb.name == "my-downstream"

    def test_call_permitted_when_closed(self):
        """Calls are permitted in CLOSED state."""
        cb = CircuitBreaker("test")
        assert cb.is_call_permitted() is True


class TestClosedToOpenTransition:
    """Test CLOSED -> OPEN transition at failure threshold."""

    def test_stays_closed_under_threshold(self):
        """Remains CLOSED when failures are below threshold."""
        cfg = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("test", cfg)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_call_permitted() is True

    def test_opens_at_threshold(self):
        """Transitions to OPEN when consecutive failures reach threshold."""
        cfg = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", cfg)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_call_not_permitted_when_open(self):
        """Calls are rejected in OPEN state."""
        cfg = CircuitBreakerConfig(failure_threshold=2, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.is_call_permitted() is False

    def test_success_resets_failure_count(self):
        """A success in CLOSED state resets consecutive failure count."""
        cfg = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # After success, failures reset — two more failures shouldn't open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED


class TestOpenToHalfOpenTransition:
    """Test OPEN -> HALF_OPEN auto-transition after timeout."""

    def test_auto_transitions_after_timeout(self):
        """State auto-transitions from OPEN to HALF_OPEN after reset_timeout."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

    def test_stays_open_before_timeout(self):
        """Stays OPEN before reset_timeout elapses."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_call_permitted_in_half_open(self):
        """Calls are permitted in HALF_OPEN state (up to max_calls)."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_call_permitted() is True


class TestHalfOpenTransitions:
    """Test HALF_OPEN -> CLOSED and HALF_OPEN -> OPEN transitions."""

    def test_half_open_to_closed_on_success(self):
        """Transitions from HALF_OPEN to CLOSED on success."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Transitions from HALF_OPEN to OPEN immediately on failure."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=0.01)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_failure_count_reset_after_half_open_success(self):
        """Failure count is reset when transitioning HALF_OPEN -> CLOSED."""
        cfg = CircuitBreakerConfig(failure_threshold=2, reset_timeout=0.01)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        # One failure should NOT open (threshold is 2)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED


class TestReset:
    """Test manual reset."""

    def test_reset_from_open(self):
        """Reset forces circuit from OPEN back to CLOSED."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_call_permitted() is True

    def test_reset_clears_failure_count(self):
        """Reset clears the consecutive failure count."""
        cfg = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        cb.record_failure()
        cb.reset()
        # Two more failures should not open (threshold is 3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED


class TestSyncContextManager:
    """Test synchronous context manager usage."""

    def test_context_manager_records_success(self):
        """Successful block records success."""
        cb = CircuitBreaker("test")
        with cb:
            pass  # No exception
        assert cb.state == CircuitState.CLOSED

    def test_context_manager_records_failure(self):
        """Exception in block records failure and re-raises."""
        cfg = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", cfg)
        with pytest.raises(ValueError, match="boom"), cb:
            raise ValueError("boom")
        assert cb.state == CircuitState.OPEN

    def test_context_manager_rejects_when_open(self):
        """Context manager raises CircuitBreakerError when circuit is OPEN."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerError), cb:
            pass  # Should never reach here


class TestAsyncContextManager:
    """Test asynchronous context manager usage."""

    @pytest.mark.asyncio
    async def test_async_context_manager_records_success(self):
        """Successful async block records success."""
        cb = CircuitBreaker("test")
        async with cb:
            pass
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_async_context_manager_records_failure(self):
        """Exception in async block records failure and re-raises."""
        cfg = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", cfg)
        with pytest.raises(ValueError, match="boom"):
            async with cb:
                raise ValueError("boom")
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_async_context_manager_rejects_when_open(self):
        """Async context manager raises CircuitBreakerError when OPEN."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        cb.record_failure()
        with pytest.raises(CircuitBreakerError):
            async with cb:
                pass


class TestCircuitBreakerError:
    """Test CircuitBreakerError carries useful context."""

    def test_error_message_includes_name(self):
        """Error message references the circuit breaker name."""
        cfg = CircuitBreakerConfig(failure_threshold=1, reset_timeout=60.0)
        cb = CircuitBreaker("payments-api", cfg)
        cb.record_failure()
        with pytest.raises(CircuitBreakerError, match="payments-api"), cb:
            pass


class TestThreadSafety:
    """Test concurrent access from multiple threads."""

    def test_concurrent_failures(self):
        """Multiple threads recording failures concurrently is safe."""
        cfg = CircuitBreakerConfig(failure_threshold=100, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        barrier = threading.Barrier(10)

        def record_failures():
            barrier.wait()
            for _ in range(10):
                cb.record_failure()

        threads = [threading.Thread(target=record_failures) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 10 threads * 10 failures = 100, should hit threshold
        assert cb.state == CircuitState.OPEN

    def test_concurrent_mixed_operations(self):
        """Mixed success/failure/state reads from multiple threads is safe."""
        cfg = CircuitBreakerConfig(failure_threshold=50, reset_timeout=60.0)
        cb = CircuitBreaker("test", cfg)
        errors: list[Exception] = []

        def worker(op: str):
            try:
                for _ in range(100):
                    if op == "fail":
                        cb.record_failure()
                    elif op == "success":
                        cb.record_success()
                    elif op == "read":
                        _ = cb.state
                        _ = cb.is_call_permitted()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=("fail",)),
            threading.Thread(target=worker, args=("success",)),
            threading.Thread(target=worker, args=("read",)),
            threading.Thread(target=worker, args=("read",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should have occurred
        assert errors == []
