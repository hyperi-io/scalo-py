#  Project:   scalo
#  File:      tests/unit/test_otel_backoff.py
#  Purpose:   Backoff gate contract, shared with scalo-rs
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""The OTLP backoff gate.

Mirrors the unit tests in ``scalo-rs/src/otel_backoff.rs``. The constants are a
cross-language contract, so these assert the same behaviour: one failure blocks
the next attempt, a success reopens the gate, the wait doubles and stops at the
ceiling, and a long outage never overflows it.
"""

from __future__ import annotations

import pytest

from scalo.otel_backoff import (
    JITTER_PCT,
    MAX_BACKOFF_SECONDS,
    BackoffGate,
    GatedMetricExporter,
    GatedSpanExporter,
)


class TestBackoffGate:
    def test_first_failure_blocks_the_next_attempt(self):
        gate = BackoffGate(60)
        assert not gate.should_skip(), "a fresh gate must not block"
        gate.record_failure("metric", "connection refused")
        assert gate.should_skip(), "the attempt after a failure is skipped"

    def test_success_clears_the_backoff(self):
        gate = BackoffGate(60)
        gate.record_failure("metric", "connection refused")
        assert gate.should_skip()
        gate.record_success("metric")
        assert not gate.should_skip(), "a success must reopen the gate"

    def test_wait_doubles_and_stops_at_the_ceiling(self):
        gate = BackoffGate(1)
        # Jitter is +/-20%, so compare against the band rather than a point.
        first = gate._wait_for(1)
        second = gate._wait_for(2)
        assert 0.8 <= first <= 1.2, f"first wait {first} outside the jitter band around 1s"
        assert 1.6 <= second <= 2.4, f"second wait {second} outside the jitter band around 2s"
        assert gate._wait_for(1_000) <= MAX_BACKOFF_SECONDS

    @pytest.mark.parametrize("failures", [50, 1_000, 2**31 - 1])
    def test_wait_never_overflows_on_a_long_outage(self, failures):
        gate = BackoffGate(60)
        assert gate._wait_for(failures) <= MAX_BACKOFF_SECONDS

    def test_suppressed_attempts_are_counted(self):
        gate = BackoffGate(60)
        gate.record_failure("span", "connection refused")
        assert gate.should_skip()
        assert gate.should_skip()
        assert gate.suppressed == 2, "each skipped attempt must be counted"

    def test_recovery_reports_what_the_outage_cost(self):
        gate = BackoffGate(60)
        gate.record_failure("metric", "connection refused")
        gate.should_skip()
        assert gate.consecutive_failures == 1
        gate.record_success("metric")
        assert gate.consecutive_failures == 0
        assert gate.suppressed == 0

    def test_base_wait_has_a_floor(self):
        """A misconfigured interval must not turn the gate into a spin."""
        gate = BackoffGate(0)
        assert gate._wait_for(1) > 0

    def test_reporting_never_becomes_the_problem(self, monkeypatch):
        """An exporter thread outlives the sinks; a broken log must not escape."""
        import scalo.otel_backoff as mod

        class _BrokenLogger:
            def bind(self, **kwargs):
                raise ValueError("I/O operation on closed file")

        monkeypatch.setattr(mod, "logger", _BrokenLogger())
        gate = BackoffGate(60)
        gate.record_failure("metric", "connection refused")
        gate.record_success("metric")
        assert gate.consecutive_failures == 0, "the state must still be maintained"

    def test_nothing_is_logged_during_interpreter_finalisation(self, monkeypatch):
        import scalo.otel_backoff as mod

        calls = []

        class _CountingLogger:
            def bind(self, **kwargs):
                calls.append(kwargs)
                return self

            def warning(self, message):
                pass

        monkeypatch.setattr(mod, "logger", _CountingLogger())
        monkeypatch.setattr(mod.sys, "is_finalizing", lambda: True)
        BackoffGate(60).record_failure("metric", "connection refused")
        assert calls == [], "logging during finalisation prints a loguru traceback, not the message"

    def test_jitter_is_applied(self):
        """Two waits for the same failure count must not be identical every time."""
        gate = BackoffGate(60)
        waits = {gate._wait_for(3) for _ in range(50)}
        assert len(waits) > 1, "no jitter -- a fleet would retry in lockstep"
        assert JITTER_PCT > 0


class _FlakyExporter:
    """Records calls and returns whatever the test queued up."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self._preferred_temporality = {"sentinel": 1}
        self._preferred_aggregation = {"sentinel": 2}

    def _next(self):
        self.calls += 1
        result = self._results.pop(0) if self._results else self._results
        if isinstance(result, Exception):
            raise result
        return result

    def export(self, *args, **kwargs):
        return self._next()

    def force_flush(self, timeout_millis=10_000):
        return True

    def shutdown(self, *args, **kwargs):
        return None


class TestGatedMetricExporter:
    def test_temporality_and_aggregation_come_from_the_inner_exporter(self):
        """PeriodicExportingMetricReader reads these off whatever it is handed."""
        inner = _FlakyExporter([])
        gated = GatedMetricExporter(inner, 1)
        assert gated._preferred_temporality is inner._preferred_temporality
        assert gated._preferred_aggregation is inner._preferred_aggregation

    def test_failure_suppresses_the_next_call_to_the_collector(self):
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = _FlakyExporter([MetricExportResult.FAILURE])
        gated = GatedMetricExporter(inner, 60)

        assert gated.export(None) == MetricExportResult.SUCCESS, "a handled failure must not be re-reported"
        assert inner.calls == 1

        gated.export(None)
        assert inner.calls == 1, "the collector must not be dialled again while backing off"

    def test_an_exception_is_treated_as_a_failure_not_a_crash(self):
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = _FlakyExporter([ConnectionRefusedError("nothing listening")])
        gated = GatedMetricExporter(inner, 60)

        assert gated.export(None) == MetricExportResult.SUCCESS
        assert gated.gate.consecutive_failures == 1

    def test_success_keeps_the_gate_open(self):
        from opentelemetry.sdk.metrics.export import MetricExportResult

        inner = _FlakyExporter([MetricExportResult.SUCCESS, MetricExportResult.SUCCESS])
        gated = GatedMetricExporter(inner, 60)

        gated.export(None)
        gated.export(None)
        assert inner.calls == 2

    def test_the_readers_shutdown_budget_reaches_the_exporter(self):
        """The reader passes its remaining budget as `timeout`, not `timeout_millis`.

        Left alone that lands in **kwargs and the exporter uses its own 30s
        default, so the bound a service sets never reaches the wire.
        """
        seen = {}

        class _Recorder(_FlakyExporter):
            def shutdown(self, timeout_millis=30_000, **kwargs):
                seen["timeout_millis"] = timeout_millis
                seen["kwargs"] = kwargs

        GatedMetricExporter(_Recorder([]), 60).shutdown(timeout=1_500)
        assert seen["timeout_millis"] == 1_500
        assert seen["kwargs"] == {}, "the misnamed argument must not be forwarded as well"

    def test_an_explicit_shutdown_bound_is_not_widened(self):
        seen = {}

        class _Recorder(_FlakyExporter):
            def shutdown(self, timeout_millis=30_000, **kwargs):
                seen["timeout_millis"] = timeout_millis

        GatedMetricExporter(_Recorder([]), 60).shutdown(timeout_millis=2_000, timeout=9_000)
        assert seen["timeout_millis"] == 2_000, "the tighter of the two must win"


class TestGatedSpanExporter:
    def test_failure_suppresses_the_next_batch(self):
        from opentelemetry.sdk.trace.export import SpanExportResult

        inner = _FlakyExporter([SpanExportResult.FAILURE])
        gated = GatedSpanExporter(inner, 5)

        assert gated.export([]) == SpanExportResult.SUCCESS
        assert inner.calls == 1

        gated.export([])
        assert inner.calls == 1, "the collector must not be dialled again while backing off"

    def test_shutdown_passes_the_bound_the_processor_gives_it(self):
        """BatchSpanProcessor only forwards its budget to an exporter that names it."""
        import inspect

        assert "timeout_millis" in inspect.getfullargspec(GatedSpanExporter.shutdown).args, (
            "without timeout_millis in the signature the processor calls shutdown() bare "
            "and the exporter falls back to its own 30s default"
        )

        seen = {}

        class _Recorder(_FlakyExporter):
            def shutdown(self, timeout_millis=30_000):
                seen["timeout_millis"] = timeout_millis

        GatedSpanExporter(_Recorder([]), 5).shutdown(timeout_millis=2_000)
        assert seen == {"timeout_millis": 2_000}

    def test_shutdown_tolerates_an_exporter_that_takes_no_timeout(self):
        class _NoTimeout(_FlakyExporter):
            def __init__(self):
                super().__init__([])
                self.shut_down = False

            def shutdown(self):
                self.shut_down = True

        inner = _NoTimeout()
        GatedSpanExporter(inner, 5).shutdown(timeout_millis=2_000)
        assert inner.shut_down

    def test_shutdown_reaches_the_inner_exporter(self):
        class _Recorder(_FlakyExporter):
            def __init__(self):
                super().__init__([])
                self.shut_down = False

            def shutdown(self, *args, **kwargs):
                self.shut_down = True

        inner = _Recorder()
        GatedSpanExporter(inner, 5).shutdown()
        assert inner.shut_down, "a wrapper that swallows shutdown leaks the exporter thread"
