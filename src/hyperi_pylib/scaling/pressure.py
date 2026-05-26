#  Project:      hyperi-pylib
#  File:         src/hyperi_pylib/scaling/pressure.py
#  Purpose:      Weighted composite scaling pressure with gate logic
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Scaling pressure calculator matching rustlib ``src/scaling/pressure.rs``.

Produces a 0-100 composite score from weighted component saturations.
Gate logic (evaluated in order):

1. Circuit open  -> return 0.0  (scaling won't help)
2. Memory >= gate threshold -> return 100.0  (scale before OOM)
3. Otherwise -> weighted sum * 100

Thread-safe via ``threading.Lock`` -- multiple async tasks may update
components concurrently.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ScalingPressureConfig:
    """Scaling pressure weights + thresholds. Validates at construction:

    - each weight in ``[0.0, 1.0]``
    - weights sum to ``1.0`` (tolerance 0.001)
    - ``memory_gate_threshold`` in ``(0.0, 1.0]``

    Invalid -> ``ValueError`` at startup, not silent nonsense at runtime.
    """

    memory_weight: float = 0.25
    queue_depth_weight: float = 0.30
    latency_weight: float = 0.25
    error_rate_weight: float = 0.15
    custom_weight: float = 0.05
    memory_gate_threshold: float = 0.85

    def __post_init__(self) -> None:
        weights = {
            "memory_weight": self.memory_weight,
            "queue_depth_weight": self.queue_depth_weight,
            "latency_weight": self.latency_weight,
            "error_rate_weight": self.error_rate_weight,
            "custom_weight": self.custom_weight,
        }
        for name, value in weights.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0]; got {value}")
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"weights must sum to 1.0 (got {total:.4f}); weights: {weights}")
        if not 0.0 < self.memory_gate_threshold <= 1.0:
            raise ValueError(f"memory_gate_threshold must be in (0.0, 1.0]; got {self.memory_gate_threshold}")


@dataclass(slots=True, frozen=True)
class PressureSnapshot:
    """Immutable point-in-time snapshot of scaling pressure state."""

    overall: float
    memory: float
    queue: float
    latency: float
    error: float
    circuit_open: bool


# Component name -> internal slot mapping
_COMPONENT_MAP: dict[str, str] = {
    "memory": "memory",
    "queue": "queue",
    "queue_depth": "queue",
    "latency": "latency",
    "error": "error",
    "error_rate": "error",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp a value to [low, high] range."""
    if value < low:
        return low
    if value > high:
        return high
    return value


class ScalingPressure:
    """
    Weighted composite scaling pressure calculator for KEDA autoscaling.

    Matches rustlib's gate logic: circuit open -> 0, memory gate -> 100,
    otherwise weighted sum of components * 100.
    """

    def __init__(self, config: ScalingPressureConfig | None = None) -> None:
        self._config = config or ScalingPressureConfig()
        self._lock = threading.Lock()

        # Component saturations (0.0 - 1.0)
        self._memory: float = 0.0
        self._queue: float = 0.0
        self._latency: float = 0.0
        self._error: float = 0.0
        self._custom: float = 0.0

        self._circuit_open: bool = False

        # Optional metrics gauge (set via register_gauge)
        self._gauge: Any = None

    def set_component(self, name: str, saturation: float) -> None:
        """
        Set a component's saturation value (0.0-1.0).

        Component mapping:
        - "memory" -> memory_weight
        - "queue" or "queue_depth" -> queue_depth_weight
        - "latency" -> latency_weight
        - "error" or "error_rate" -> error_rate_weight
        - anything else -> custom_weight

        Args:
            name: Component name
            saturation: Saturation value (clamped to 0.0-1.0)
        """
        clamped = _clamp(saturation)
        slot = _COMPONENT_MAP.get(name)

        with self._lock:
            if slot == "memory":
                self._memory = clamped
            elif slot == "queue":
                self._queue = clamped
            elif slot == "latency":
                self._latency = clamped
            elif slot == "error":
                self._error = clamped
            else:
                # Unmapped names go to custom
                self._custom = clamped

    def set_memory(self, used_bytes: int, limit_bytes: int) -> None:
        """
        Convenience method: calculate memory saturation from used/limit bytes.

        Args:
            used_bytes: Current memory usage in bytes
            limit_bytes: Memory limit in bytes (0 treated as no limit)
        """
        if limit_bytes <= 0:
            saturation = 0.0
        else:
            saturation = used_bytes / limit_bytes
        self.set_component("memory", saturation)

    def set_circuit_open(self, is_open: bool) -> None:
        """
        Set circuit breaker state.

        When circuit is open, calculate() always returns 0.0 because
        scaling won't help a tripped circuit.

        Args:
            is_open: True if circuit breaker is open
        """
        with self._lock:
            self._circuit_open = is_open

    def calculate(self) -> float:
        """
        Calculate composite scaling pressure (0-100).

        Gate logic (evaluated in order):
        1. Circuit open -> 0.0
        2. Memory >= gate threshold -> 100.0
        3. Weighted sum of components * 100

        Returns:
            Pressure score from 0.0 to 100.0
        """
        with self._lock:
            # Gate 1: circuit open -> 0 (scaling won't help)
            if self._circuit_open:
                result = 0.0
                self._update_gauge(result)
                return result

            # Gate 2: memory above threshold -> 100 (scale before OOM)
            if self._memory >= self._config.memory_gate_threshold:
                result = 100.0
                self._update_gauge(result)
                return result

            # Weighted sum; final clamp guards against FP drift
            cfg = self._config
            weighted = (
                self._memory * cfg.memory_weight
                + self._queue * cfg.queue_depth_weight
                + self._latency * cfg.latency_weight
                + self._error * cfg.error_rate_weight
                + self._custom * cfg.custom_weight
            )
            result = _clamp(weighted * 100.0, low=0.0, high=100.0)
            self._update_gauge(result)
            return result

    def snapshot(self) -> PressureSnapshot:
        """
        Take a frozen point-in-time snapshot of pressure state.

        Returns:
            Immutable PressureSnapshot dataclass
        """
        with self._lock:
            # Calculate overall within the lock to get consistent state
            if self._circuit_open:
                overall = 0.0
            elif self._memory >= self._config.memory_gate_threshold:
                overall = 100.0
            else:
                cfg = self._config
                weighted = (
                    self._memory * cfg.memory_weight
                    + self._queue * cfg.queue_depth_weight
                    + self._latency * cfg.latency_weight
                    + self._error * cfg.error_rate_weight
                    + self._custom * cfg.custom_weight
                )
                overall = weighted * 100.0

            return PressureSnapshot(
                overall=overall,
                memory=self._memory,
                queue=self._queue,
                latency=self._latency,
                error=self._error,
                circuit_open=self._circuit_open,
            )

    def register_gauge(self, metrics_manager: Any) -> None:
        """
        Register a scaling_pressure gauge on a MetricsManager.

        The gauge is updated automatically on each calculate() call.

        Args:
            metrics_manager: A MetricsManager instance from hyperi_pylib.metrics
        """
        self._gauge = metrics_manager.gauge("scaling_pressure", "Composite scaling pressure score (0-100)")

    def _update_gauge(self, value: float) -> None:
        """Update the registered gauge if one exists."""
        if self._gauge is not None:
            self._gauge.set(value)
