#  Project:      hyperi-pylib
#  File:         test_metrics_dfe_groups.py
#  Purpose:      Tests for DFE metric groups matching rustlib standard
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for DFE metric groups -- composable metric structs for DFE apps."""

import time

import pytest

from hyperi_pylib.metrics import MetricsManager, create_metrics
from hyperi_pylib.metrics.dfe_groups import (
    AppMetrics,
    BackpressureMetrics,
    BufferMetrics,
    CircuitBreakerMetrics,
    ConsumerMetrics,
    SinkMetrics,
)


@pytest.fixture
def mgr() -> MetricsManager:
    """Create a fresh MetricsManager with Prometheus backend for testing."""
    return create_metrics(f"dfe_loader_{int(time.monotonic_ns())}", backend="prometheus", enable_auto_update=False)


class TestAppMetrics:
    """Test AppMetrics group -- mandatory for all DFE apps."""

    def test_construction(self, mgr: MetricsManager):
        """AppMetrics registers all mandatory metrics on construction."""
        app = AppMetrics(mgr, version="1.2.3", commit="abc123")
        assert app is not None

    def test_info_gauge_set(self, mgr: MetricsManager):
        """Info gauge is set to 1 with version/commit/app labels."""
        AppMetrics(mgr, version="1.2.3", commit="abc123")
        output = mgr.metrics_text
        assert "info" in output
        assert "1.2.3" in output
        assert "abc123" in output

    def test_record_received(self, mgr: MetricsManager):
        """record_received increments records_received_total counter."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.record_received(10)
        output = mgr.metrics_text
        assert "records_received_total" in output

    def test_record_processed(self, mgr: MetricsManager):
        """record_processed increments records_processed_total counter."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.record_processed(5)
        output = mgr.metrics_text
        assert "records_processed_total" in output

    def test_record_error(self, mgr: MetricsManager):
        """record_error increments records_error_total counter."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.record_error(1)
        output = mgr.metrics_text
        assert "records_error_total" in output

    def test_record_bytes_received(self, mgr: MetricsManager):
        """record_bytes_received increments bytes_received_total counter."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.record_bytes_received(1024)
        output = mgr.metrics_text
        assert "bytes_received_total" in output

    def test_record_bytes_written(self, mgr: MetricsManager):
        """record_bytes_written increments bytes_written_total counter."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.record_bytes_written(2048)
        output = mgr.metrics_text
        assert "bytes_written_total" in output

    def test_set_memory(self, mgr: MetricsManager):
        """set_memory sets memory_used_bytes and memory_limit_bytes gauges."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.set_memory(used=512_000_000, limit=1_073_741_824)
        output = mgr.metrics_text
        assert "memory_used_bytes" in output
        assert "memory_limit_bytes" in output

    def test_record_config_reload(self, mgr: MetricsManager):
        """record_config_reload increments config_reloads_total with result label."""
        app = AppMetrics(mgr, version="1.0.0", commit="def456")
        app.record_config_reload("success")
        app.record_config_reload("error")
        output = mgr.metrics_text
        assert "config_reloads_total" in output

    def test_start_time_set(self, mgr: MetricsManager):
        """start_time_seconds gauge is set on construction."""
        AppMetrics(mgr, version="1.0.0", commit="def456")
        output = mgr.metrics_text
        assert "start_time_seconds" in output


class TestBufferMetrics:
    """Test BufferMetrics group -- for receiver, loader, archiver."""

    def test_construction(self, mgr: MetricsManager):
        """BufferMetrics registers all buffer metrics on construction."""
        buf = BufferMetrics(mgr)
        assert buf is not None

    def test_set_buffer_state(self, mgr: MetricsManager):
        """set_buffer_state sets bytes and records gauges."""
        buf = BufferMetrics(mgr)
        buf.set_buffer_state(bytes_val=4096, records=100)
        output = mgr.metrics_text
        assert "buffer_bytes" in output
        assert "buffer_records" in output

    def test_record_flush(self, mgr: MetricsManager):
        """record_flush increments counter and observes duration histogram."""
        buf = BufferMetrics(mgr)
        buf.record_flush(duration_seconds=0.042, trigger="size")
        output = mgr.metrics_text
        assert "buffer_flush_total" in output
        assert "buffer_flush_duration_seconds" in output
        assert "buffer_flush_trigger_total" in output

    def test_custom_buckets(self, mgr: MetricsManager):
        """BufferMetrics accepts custom histogram buckets."""
        custom_buckets = (0.001, 0.01, 0.1, 1.0, 10.0)
        buf = BufferMetrics(mgr, flush_duration_buckets=custom_buckets)
        buf.record_flush(duration_seconds=0.005, trigger="age")
        output = mgr.metrics_text
        assert "buffer_flush_duration_seconds" in output


class TestConsumerMetrics:
    """Test ConsumerMetrics group -- for Kafka consumer apps."""

    def test_construction(self, mgr: MetricsManager):
        """ConsumerMetrics registers all consumer metrics on construction."""
        consumer = ConsumerMetrics(mgr)
        assert consumer is not None

    def test_set_lag(self, mgr: MetricsManager):
        """set_lag sets consumer_lag gauge with topic and partition labels."""
        consumer = ConsumerMetrics(mgr)
        consumer.set_lag(topic="events", partition=0, lag=1500)
        output = mgr.metrics_text
        assert "consumer_lag" in output

    def test_set_partitions_assigned(self, mgr: MetricsManager):
        """set_partitions_assigned sets consumer_partitions_assigned gauge."""
        consumer = ConsumerMetrics(mgr)
        consumer.set_partitions_assigned(6)
        output = mgr.metrics_text
        assert "consumer_partitions_assigned" in output

    def test_record_rebalance(self, mgr: MetricsManager):
        """record_rebalance increments consumer_rebalance_total counter."""
        consumer = ConsumerMetrics(mgr)
        consumer.record_rebalance()
        output = mgr.metrics_text
        assert "consumer_rebalance_total" in output

    def test_record_poll_duration(self, mgr: MetricsManager):
        """record_poll_duration observes consumer_poll_duration_seconds histogram."""
        consumer = ConsumerMetrics(mgr)
        consumer.record_poll_duration(0.015)
        output = mgr.metrics_text
        assert "consumer_poll_duration_seconds" in output

    def test_record_offsets_committed(self, mgr: MetricsManager):
        """record_offsets_committed increments offsets_committed_total counter."""
        consumer = ConsumerMetrics(mgr)
        consumer.record_offsets_committed()
        output = mgr.metrics_text
        assert "offsets_committed_total" in output


class TestSinkMetrics:
    """Test SinkMetrics group -- for apps with a downstream."""

    def test_construction(self, mgr: MetricsManager):
        """SinkMetrics registers all sink metrics on construction."""
        sink = SinkMetrics(mgr)
        assert sink is not None

    def test_record_duration(self, mgr: MetricsManager):
        """record_duration observes sink_duration_seconds with backend label."""
        sink = SinkMetrics(mgr)
        sink.record_duration(backend="clickhouse", duration_seconds=0.015)
        output = mgr.metrics_text
        assert "sink_duration_seconds" in output

    def test_record_error(self, mgr: MetricsManager):
        """record_error increments sink_errors_total with backend label."""
        sink = SinkMetrics(mgr)
        sink.record_error(backend="clickhouse")
        output = mgr.metrics_text
        assert "sink_errors_total" in output

    def test_record_bytes_sent(self, mgr: MetricsManager):
        """record_bytes_sent increments bytes_sent_total with format label."""
        sink = SinkMetrics(mgr)
        sink.record_bytes_sent(fmt="json", nbytes=2048)
        output = mgr.metrics_text
        assert "bytes_sent_total" in output

    def test_set_concurrent_inserts(self, mgr: MetricsManager):
        """set_concurrent_inserts sets concurrent_inserts gauge."""
        sink = SinkMetrics(mgr)
        sink.set_concurrent_inserts(3)
        output = mgr.metrics_text
        assert "concurrent_inserts" in output


class TestCircuitBreakerMetrics:
    """Test CircuitBreakerMetrics group."""

    def test_construction(self, mgr: MetricsManager):
        """CircuitBreakerMetrics registers circuit breaker metrics on construction."""
        cb = CircuitBreakerMetrics(mgr)
        assert cb is not None

    def test_set_state(self, mgr: MetricsManager):
        """set_state sets circuit_breaker_state gauge for a target."""
        cb = CircuitBreakerMetrics(mgr)
        cb.set_state(target="db.events", state="open")
        output = mgr.metrics_text
        assert "circuit_breaker_state" in output

    def test_record_transition(self, mgr: MetricsManager):
        """record_transition increments circuit_breaker_transitions_total."""
        cb = CircuitBreakerMetrics(mgr)
        cb.record_transition(target="db.events", to_state="open")
        output = mgr.metrics_text
        assert "circuit_breaker_transitions_total" in output

    def test_state_values(self, mgr: MetricsManager):
        """State strings map to correct numeric values: closed=0, open=1, half_open=2."""
        cb = CircuitBreakerMetrics(mgr)
        # Should not raise for any valid state
        cb.set_state(target="db1", state="closed")
        cb.set_state(target="db2", state="open")
        cb.set_state(target="db3", state="half_open")


class TestBackpressureMetrics:
    """Test BackpressureMetrics group."""

    def test_construction(self, mgr: MetricsManager):
        """BackpressureMetrics registers backpressure metrics on construction."""
        bp = BackpressureMetrics(mgr)
        assert bp is not None

    def test_record_event(self, mgr: MetricsManager):
        """record_event increments backpressure_events_total counter."""
        bp = BackpressureMetrics(mgr)
        bp.record_event()
        output = mgr.metrics_text
        assert "backpressure_events_total" in output

    def test_record_duration(self, mgr: MetricsManager):
        """record_duration increments backpressure_duration_seconds_total counter."""
        bp = BackpressureMetrics(mgr)
        bp.record_duration(0.5)
        output = mgr.metrics_text
        assert "backpressure_duration_seconds_total" in output


class TestDfeGroupsReExports:
    """Test that dfe_groups module re-exports are accessible from metrics package."""

    def test_import_from_dfe_groups(self):
        """All metric group classes are importable from hyperi_pylib.metrics.dfe_groups."""
        from hyperi_pylib.metrics.dfe_groups import (
            AppMetrics,
            BackpressureMetrics,
            BufferMetrics,
            CircuitBreakerMetrics,
            ConsumerMetrics,
            SinkMetrics,
        )

        assert AppMetrics is not None
        assert BufferMetrics is not None
        assert ConsumerMetrics is not None
        assert SinkMetrics is not None
        assert CircuitBreakerMetrics is not None
        assert BackpressureMetrics is not None

    def test_import_from_metrics_package(self):
        """Metric group classes are importable from hyperi_pylib.metrics."""
        from hyperi_pylib.metrics import (
            AppMetrics,
            BackpressureMetrics,
            BufferMetrics,
            CircuitBreakerMetrics,
            ConsumerMetrics,
            SinkMetrics,
        )

        assert AppMetrics is not None
        assert BackpressureMetrics is not None


class TestMultipleGroupsIntegration:
    """Test composing multiple metric groups on one MetricsManager."""

    def test_compose_all_groups(self, mgr: MetricsManager):
        """All metric groups can be composed on a single MetricsManager."""
        app = AppMetrics(mgr, version="2.0.0", commit="feed01")
        buf = BufferMetrics(mgr)
        consumer = ConsumerMetrics(mgr)
        sink = SinkMetrics(mgr)
        cb = CircuitBreakerMetrics(mgr)
        bp = BackpressureMetrics(mgr)

        # Exercise each group
        app.record_received(100)
        app.record_processed(95)
        app.record_error(5)
        buf.set_buffer_state(bytes_val=8192, records=50)
        buf.record_flush(duration_seconds=0.01, trigger="size")
        consumer.set_lag(topic="events", partition=0, lag=200)
        consumer.record_poll_duration(0.005)
        sink.record_duration(backend="clickhouse", duration_seconds=0.02)
        cb.set_state(target="db", state="closed")
        bp.record_event()

        output = mgr.metrics_text
        assert "records_received_total" in output
        assert "buffer_flush_total" in output
        assert "consumer_lag" in output
        assert "sink_duration_seconds" in output
        assert "circuit_breaker_state" in output
        assert "backpressure_events_total" in output
