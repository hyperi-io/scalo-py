#  Project:      hyperi-pylib
#  File:         src/hyperi_pylib/resilience/__init__.py
#  Purpose:      Resilience patterns (circuit breaker, retries, bulkheads)
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Resilience patterns matching rustlib.

Provides circuit breaker with Closed/Open/HalfOpen state machine::

    from hyperi_pylib.resilience import CircuitBreaker, CircuitBreakerConfig

    cb = CircuitBreaker("payments", CircuitBreakerConfig(failure_threshold=3))

    with cb:
        response = call_downstream()
"""

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError, CircuitState

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitState",
]
