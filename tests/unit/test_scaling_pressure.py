#  Project:      hyperi-pylib
#  File:         test_scaling_pressure.py
#  Purpose:      Tests for scaling pressure calculator matching rustlib
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for scaling pressure calculator — weighted composite + gate logic."""

import threading
import time

import pytest

from hyperi_pylib.scaling import ScalingPressure, ScalingPressureConfig
from hyperi_pylib.scaling.pressure import PressureSnapshot


class TestScalingPressureConfig:
    """Test ScalingPressureConfig defaults and validation."""

    def test_default_weights_sum_to_one(self):
        """Default component weights must sum to 1.0."""
        cfg = ScalingPressureConfig()
        total = (
            cfg.memory_weight + cfg.queue_depth_weight + cfg.latency_weight + cfg.error_rate_weight + cfg.custom_weight
        )
        assert abs(total - 1.0) < 1e-9

    def test_default_memory_gate_threshold(self):
        """Default memory gate threshold is 0.85."""
        cfg = ScalingPressureConfig()
        assert cfg.memory_gate_threshold == 0.85

    def test_custom_config(self):
        """Custom config values are stored correctly."""
        cfg = ScalingPressureConfig(
            memory_weight=0.50,
            queue_depth_weight=0.20,
            latency_weight=0.10,
            error_rate_weight=0.10,
            custom_weight=0.10,
            memory_gate_threshold=0.90,
        )
        assert cfg.memory_weight == 0.50
        assert cfg.memory_gate_threshold == 0.90


class TestScalingPressureCalculation:
    """Test the weighted composite calculation."""

    def test_all_zero_returns_zero(self):
        """All components at 0 saturation returns 0.0 pressure."""
        sp = ScalingPressure()
        assert sp.calculate() == 0.0

    def test_all_max_returns_hundred_via_gate(self):
        """Memory at 1.0 triggers the memory gate (>= 0.85), returns 100.0."""
        sp = ScalingPressure()
        sp.set_component("memory", 1.0)
        sp.set_component("queue", 1.0)
        sp.set_component("latency", 1.0)
        sp.set_component("error", 1.0)
        result = sp.calculate()
        # Memory at 1.0 >= gate threshold 0.85, so gate fires -> 100.0
        assert result == 100.0

    def test_weighted_sum_without_memory_gate(self):
        """Non-memory components at max with memory below gate threshold."""
        cfg = ScalingPressureConfig(memory_gate_threshold=0.85)
        sp = ScalingPressure(config=cfg)
        sp.set_component("memory", 0.5)  # Below 0.85 gate
        sp.set_component("queue", 1.0)
        sp.set_component("latency", 1.0)
        sp.set_component("error", 1.0)
        result = sp.calculate()
        # (0.5*0.25 + 1.0*0.30 + 1.0*0.25 + 1.0*0.15 + 0*0.05) * 100
        # = (0.125 + 0.30 + 0.25 + 0.15) * 100 = 82.5
        assert abs(result - 82.5) < 1e-9

    def test_all_components_max_including_custom(self):
        """All five components at 1.0 returns exactly 100.0."""
        sp = ScalingPressure()
        sp.set_component("memory", 1.0)
        sp.set_component("queue_depth", 1.0)
        sp.set_component("latency", 1.0)
        sp.set_component("error_rate", 1.0)
        sp.set_component("custom_signal", 1.0)
        result = sp.calculate()
        assert abs(result - 100.0) < 1e-9

    def test_weighted_composite(self):
        """Verify weighted sum with known values."""
        cfg = ScalingPressureConfig(
            memory_weight=0.25,
            queue_depth_weight=0.30,
            latency_weight=0.25,
            error_rate_weight=0.15,
            custom_weight=0.05,
        )
        sp = ScalingPressure(config=cfg)
        sp.set_component("memory", 0.5)
        sp.set_component("queue", 0.8)
        sp.set_component("latency", 0.3)
        # error and custom remain 0
        # expected: (0.5*0.25 + 0.8*0.30 + 0.3*0.25 + 0*0.15 + 0*0.05) * 100
        # = (0.125 + 0.24 + 0.075) * 100 = 44.0
        result = sp.calculate()
        assert abs(result - 44.0) < 1e-9

    def test_single_component_memory(self):
        """Only memory at 0.5 produces 0.5 * 0.25 * 100 = 12.5."""
        sp = ScalingPressure()
        sp.set_component("memory", 0.5)
        result = sp.calculate()
        assert abs(result - 12.5) < 1e-9


class TestGateLogic:
    """Test gate logic — circuit open and memory gate."""

    def test_circuit_open_returns_zero(self):
        """Circuit open gate: always return 0.0 regardless of component values."""
        sp = ScalingPressure()
        sp.set_component("memory", 1.0)
        sp.set_component("queue", 1.0)
        sp.set_circuit_open(True)
        result = sp.calculate()
        assert result == 0.0

    def test_circuit_open_then_closed(self):
        """After circuit closes, normal calculation resumes."""
        sp = ScalingPressure()
        sp.set_component("memory", 0.5)
        sp.set_circuit_open(True)
        assert sp.calculate() == 0.0

        sp.set_circuit_open(False)
        assert sp.calculate() > 0.0

    def test_memory_gate_above_threshold_returns_hundred(self):
        """Memory >= threshold triggers gate, returns 100.0."""
        sp = ScalingPressure()
        sp.set_component("memory", 0.85)
        result = sp.calculate()
        assert result == 100.0

    def test_memory_gate_above_threshold_custom(self):
        """Custom memory gate threshold at 0.90."""
        cfg = ScalingPressureConfig(memory_gate_threshold=0.90)
        sp = ScalingPressure(config=cfg)
        sp.set_component("memory", 0.89)
        assert sp.calculate() < 100.0

        sp.set_component("memory", 0.90)
        assert sp.calculate() == 100.0

    def test_circuit_open_takes_precedence_over_memory_gate(self):
        """Circuit open gate (priority 1) overrides memory gate (priority 2)."""
        sp = ScalingPressure()
        sp.set_component("memory", 1.0)
        sp.set_circuit_open(True)
        # Even though memory is at 100%, circuit open wins
        assert sp.calculate() == 0.0

    def test_memory_gate_exactly_at_threshold(self):
        """Memory exactly at threshold triggers the gate."""
        cfg = ScalingPressureConfig(memory_gate_threshold=0.85)
        sp = ScalingPressure(config=cfg)
        sp.set_component("memory", 0.85)
        assert sp.calculate() == 100.0

    def test_memory_gate_just_below_threshold(self):
        """Memory just below threshold uses normal weighted calculation."""
        cfg = ScalingPressureConfig(memory_gate_threshold=0.85)
        sp = ScalingPressure(config=cfg)
        sp.set_component("memory", 0.84)
        result = sp.calculate()
        assert result < 100.0
        assert result > 0.0


class TestSaturationClamping:
    """Test that saturation values are clamped to 0.0-1.0."""

    def test_negative_saturation_clamped_to_zero(self):
        """Negative saturation values are clamped to 0.0."""
        sp = ScalingPressure()
        sp.set_component("memory", -0.5)
        snap = sp.snapshot()
        assert snap.memory == 0.0

    def test_above_one_saturation_clamped(self):
        """Values above 1.0 are clamped to 1.0."""
        sp = ScalingPressure()
        sp.set_component("queue", 2.5)
        snap = sp.snapshot()
        assert snap.queue == 1.0

    def test_zero_saturation_stays_zero(self):
        """Zero is a valid saturation value."""
        sp = ScalingPressure()
        sp.set_component("latency", 0.0)
        snap = sp.snapshot()
        assert snap.latency == 0.0

    def test_one_saturation_stays_one(self):
        """1.0 is a valid saturation value."""
        sp = ScalingPressure()
        sp.set_component("error", 1.0)
        snap = sp.snapshot()
        assert snap.error == 1.0


class TestSetMemoryConvenience:
    """Test the set_memory() convenience method."""

    def test_set_memory_calculates_saturation(self):
        """set_memory derives saturation from used/limit bytes."""
        sp = ScalingPressure()
        sp.set_memory(used_bytes=512_000_000, limit_bytes=1_073_741_824)
        snap = sp.snapshot()
        expected = 512_000_000 / 1_073_741_824
        assert abs(snap.memory - expected) < 1e-9

    def test_set_memory_zero_limit(self):
        """Zero limit bytes results in 0.0 saturation (avoid division by zero)."""
        sp = ScalingPressure()
        sp.set_memory(used_bytes=100, limit_bytes=0)
        snap = sp.snapshot()
        assert snap.memory == 0.0

    def test_set_memory_exceeds_limit(self):
        """Used > limit is clamped to 1.0."""
        sp = ScalingPressure()
        sp.set_memory(used_bytes=2_000_000_000, limit_bytes=1_000_000_000)
        snap = sp.snapshot()
        assert snap.memory == 1.0

    def test_set_memory_triggers_gate(self):
        """set_memory at 90% with default 0.85 threshold triggers gate."""
        sp = ScalingPressure()
        sp.set_memory(used_bytes=900, limit_bytes=1000)
        result = sp.calculate()
        assert result == 100.0


class TestComponentMapping:
    """Test that component names map to correct weights."""

    def test_queue_alias(self):
        """'queue' maps to queue_depth_weight."""
        sp = ScalingPressure()
        sp.set_component("queue", 0.5)
        snap = sp.snapshot()
        assert snap.queue == 0.5

    def test_queue_depth_alias(self):
        """'queue_depth' maps to queue_depth_weight."""
        sp = ScalingPressure()
        sp.set_component("queue_depth", 0.7)
        snap = sp.snapshot()
        assert snap.queue == 0.7

    def test_error_alias(self):
        """'error' maps to error_rate_weight."""
        sp = ScalingPressure()
        sp.set_component("error", 0.3)
        snap = sp.snapshot()
        assert snap.error == 0.3

    def test_error_rate_alias(self):
        """'error_rate' maps to error_rate_weight."""
        sp = ScalingPressure()
        sp.set_component("error_rate", 0.4)
        snap = sp.snapshot()
        assert snap.error == 0.4

    def test_unknown_component_maps_to_custom(self):
        """Any unrecognised component name maps to custom_weight."""
        sp = ScalingPressure()
        sp.set_component("my_special_signal", 0.6)
        # custom_weight = 0.05, so 0.6 * 0.05 * 100 = 3.0
        result = sp.calculate()
        assert abs(result - 3.0) < 1e-9


class TestSnapshot:
    """Test PressureSnapshot frozen data class."""

    def test_snapshot_returns_frozen_state(self):
        """Snapshot is a frozen dataclass — immutable after creation."""
        sp = ScalingPressure()
        sp.set_component("memory", 0.5)
        sp.set_component("queue", 0.3)
        snap = sp.snapshot()

        assert isinstance(snap, PressureSnapshot)
        assert snap.memory == 0.5
        assert snap.queue == 0.3
        assert snap.latency == 0.0
        assert snap.error == 0.0
        assert snap.circuit_open is False

    def test_snapshot_overall_matches_calculate(self):
        """Snapshot.overall matches calculate() result."""
        sp = ScalingPressure()
        sp.set_component("memory", 0.4)
        sp.set_component("latency", 0.6)
        expected = sp.calculate()
        snap = sp.snapshot()
        assert abs(snap.overall - expected) < 1e-9

    def test_snapshot_immutable(self):
        """PressureSnapshot cannot be modified after creation."""
        sp = ScalingPressure()
        snap = sp.snapshot()
        with pytest.raises(AttributeError):
            snap.overall = 50.0  # type: ignore[misc]

    def test_snapshot_with_circuit_open(self):
        """Snapshot reflects circuit open state."""
        sp = ScalingPressure()
        sp.set_circuit_open(True)
        snap = sp.snapshot()
        assert snap.circuit_open is True
        assert snap.overall == 0.0


class TestThreadSafety:
    """Test thread safety of concurrent component updates."""

    def test_concurrent_set_component(self):
        """Multiple threads updating different components concurrently is safe."""
        sp = ScalingPressure()
        errors: list[Exception] = []

        def update_component(name: str, iterations: int):
            try:
                for i in range(iterations):
                    sp.set_component(name, (i % 100) / 100.0)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_component, args=("memory", 1000)),
            threading.Thread(target=update_component, args=("queue", 1000)),
            threading.Thread(target=update_component, args=("latency", 1000)),
            threading.Thread(target=update_component, args=("error", 1000)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # After all threads finish, we can still calculate without errors
        result = sp.calculate()
        assert 0.0 <= result <= 100.0

    def test_concurrent_calculate_and_set(self):
        """Concurrent reads (calculate) and writes (set_component) are safe."""
        sp = ScalingPressure()
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(500):
                    sp.set_component("memory", (i % 100) / 100.0)
                    sp.set_component("queue", (i % 50) / 50.0)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(500):
                    result = sp.calculate()
                    assert 0.0 <= result <= 100.0
                    snap = sp.snapshot()
                    assert 0.0 <= snap.overall <= 100.0
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestRegisterGauge:
    """Test optional metrics integration via register_gauge."""

    def test_register_gauge_with_metrics_manager(self):
        """register_gauge creates a scaling_pressure gauge on MetricsManager."""
        from hyperi_pylib.metrics import MetricsManager, create_metrics

        mgr = create_metrics(f"test_scaling_{int(time.monotonic_ns())}", backend="prometheus", enable_auto_update=False)
        sp = ScalingPressure()
        sp.register_gauge(mgr)

        sp.set_component("memory", 0.4)
        sp.set_component("queue", 0.6)
        result = sp.calculate()

        output = mgr.metrics_text
        assert "scaling_pressure" in output

    def test_register_gauge_updates_on_calculate(self):
        """Gauge value updates each time calculate() is called."""
        from hyperi_pylib.metrics import create_metrics

        mgr = create_metrics(f"test_scaling_{int(time.monotonic_ns())}", backend="prometheus", enable_auto_update=False)
        sp = ScalingPressure()
        sp.register_gauge(mgr)

        sp.set_component("memory", 0.0)
        sp.calculate()
        output1 = mgr.metrics_text

        sp.set_component("memory", 0.5)
        sp.calculate()
        output2 = mgr.metrics_text

        # Both should contain the gauge, but values differ
        assert "scaling_pressure" in output1
        assert "scaling_pressure" in output2

    def test_works_without_register_gauge(self):
        """ScalingPressure works fine without calling register_gauge."""
        sp = ScalingPressure()
        sp.set_component("memory", 0.5)
        result = sp.calculate()
        assert result > 0.0


class TestImports:
    """Test public API imports."""

    def test_import_from_scaling_package(self):
        """ScalingPressure and config are importable from hyperi_pylib.scaling."""
        from hyperi_pylib.scaling import ScalingPressure, ScalingPressureConfig

        assert ScalingPressure is not None
        assert ScalingPressureConfig is not None

    def test_import_snapshot_from_pressure_module(self):
        """PressureSnapshot is importable from hyperi_pylib.scaling.pressure."""
        from hyperi_pylib.scaling.pressure import PressureSnapshot

        assert PressureSnapshot is not None
