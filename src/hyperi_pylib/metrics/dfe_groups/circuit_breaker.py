#  Project:      hyperi-pylib
#  File:         circuit_breaker.py
#  Purpose:      CircuitBreakerMetrics group for DFE apps
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
CircuitBreakerMetrics -- composable metric group for circuit breaker state.

Mirrors rustlib's dfe_groups::CircuitBreakerMetrics. Tracks circuit breaker
state (closed/open/half_open) and state transitions per target.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager

# Numeric state mapping: closed=0, open=1, half_open=2
_STATE_VALUES: dict[str, int] = {
    "closed": 0,
    "open": 1,
    "half_open": 2,
}


class CircuitBreakerMetrics:
    """
    Circuit breaker metrics for DFE apps.

    Registers:
        {ns}_circuit_breaker_state gauge (labels: target) -- 0=closed, 1=open, 2=half_open
        {ns}_circuit_breaker_transitions_total counter (labels: target, to_state)
    """

    def __init__(self, mgr: MetricsManager) -> None:
        """
        Register circuit breaker metrics.

        Args:
            mgr: MetricsManager instance
        """
        self._state: Any = mgr.gauge(
            "circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            labels=["target"],
        )
        self._transitions: Any = mgr.counter(
            "circuit_breaker_transitions_total",
            "Circuit breaker state transitions",
            labels=["target", "to_state"],
        )

    def set_state(self, target: str, state: str) -> None:
        """
        Set circuit breaker state for a target.

        Args:
            target: Downstream identifier (e.g. "db.events")
            state: One of "closed", "open", "half_open"
        """
        numeric_value = _STATE_VALUES.get(state, 0)
        self._state.labels(target=target).set(numeric_value)

    def record_transition(self, target: str, to_state: str) -> None:
        """
        Record a circuit breaker state transition.

        Args:
            target: Downstream identifier
            to_state: New state (closed, open, half_open)
        """
        self._transitions.labels(target=target, to_state=to_state).inc()
