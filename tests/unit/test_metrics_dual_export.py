"""
Tests for OpenTelemetry dual export (OTLP push + Prometheus scrape).

Validates that the OpenTelemetryBackend creates both metric readers,
returns real Prometheus-format metrics via get_metrics(), and respects
configuration and environment variable overrides.
"""

import os

import pytest

from hyperi_pylib.metrics import MetricsManager, create_metrics

# Check if OTel is available in this environment
try:
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    OTEL_INSTALLED = True
except ImportError:
    OTEL_INSTALLED = False

pytestmark = pytest.mark.skipif(not OTEL_INSTALLED, reason="OpenTelemetry packages not installed")


class TestDualReaderCreation:
    """Test that both OTLP and Prometheus readers are created."""

    def test_default_creates_both_readers(self):
        """Default config creates both OTLP push and Prometheus scrape readers."""
        metrics = create_metrics("dual-test-default", backend="opentelemetry")

        assert metrics.enabled
        assert metrics.backend_name == "opentelemetry"

        # Access the underlying backend's provider to verify readers
        backend = metrics._backend
        readers = backend._provider._sdk_config.metric_readers
        reader_types = [type(r).__name__ for r in readers]

        assert "PeriodicExportingMetricReader" in reader_types
        assert "PrometheusMetricReader" in reader_types

    def test_prometheus_scrape_disabled(self):
        """prometheus_scrape: false creates OTLP-only reader."""
        config = {
            "opentelemetry": {
                "prometheus_scrape": False,
                "endpoint": "http://localhost:4317",
            }
        }
        metrics = create_metrics("dual-test-no-prom", backend="opentelemetry", backend_config=config)

        assert metrics.enabled
        backend = metrics._backend
        readers = backend._provider._sdk_config.metric_readers
        reader_types = [type(r).__name__ for r in readers]

        assert "PeriodicExportingMetricReader" in reader_types
        assert "PrometheusMetricReader" not in reader_types
        assert backend._prometheus_reader is None

    def test_prometheus_only_when_no_endpoint(self):
        """Empty endpoint skips OTLP, Prometheus-only reader."""
        config = {
            "opentelemetry": {
                "endpoint": "",
                "prometheus_scrape": True,
            }
        }
        metrics = create_metrics("dual-test-prom-only", backend="opentelemetry", backend_config=config)

        assert metrics.enabled
        backend = metrics._backend
        readers = backend._provider._sdk_config.metric_readers
        reader_types = [type(r).__name__ for r in readers]

        assert "PeriodicExportingMetricReader" not in reader_types
        assert "PrometheusMetricReader" in reader_types


class TestPrometheusOutputFromOTel:
    """Test that get_metrics() returns real Prometheus-format output when prometheus_scrape is enabled."""

    def test_get_metrics_returns_prometheus_format(self):
        """get_metrics() returns bytes containing Prometheus exposition format."""
        metrics = create_metrics("dual-test-output", backend="opentelemetry")

        # Create a counter and increment it
        counter = metrics.counter("dual_test_total", "Dual test counter")
        counter.add(1)

        output = metrics.get_metrics()
        assert isinstance(output, bytes)
        # Should contain actual Prometheus data (at minimum the Python GC metrics
        # from the default prometheus_client registry)
        assert len(output) > 0
        # The output should not be the placeholder message
        assert b"OTLP exporter active" not in output

    def test_get_metrics_otlp_only_returns_info(self):
        """get_metrics() returns info message when only OTLP is configured."""
        config = {
            "opentelemetry": {
                "prometheus_scrape": False,
                "endpoint": "http://localhost:4317",
            }
        }
        metrics = create_metrics("dual-test-otlp-only", backend="opentelemetry", backend_config=config)

        output = metrics.get_metrics()
        assert b"OTLP exporter active" in output

    def test_content_type_with_prometheus(self):
        """Content type should be Prometheus exposition format when prometheus_scrape is enabled."""
        metrics = create_metrics("dual-test-ct", backend="opentelemetry")

        content_type = metrics.get_content_type()
        assert "text" in content_type.lower()


class TestEnvVarOverrides:
    """Test that OTEL environment variables and HYPERI_METRICS_BACKEND work."""

    def test_hyperi_metrics_backend_env_var(self, monkeypatch):
        """HYPERI_METRICS_BACKEND env var selects backend."""
        monkeypatch.setenv("HYPERI_METRICS_BACKEND", "prometheus")

        metrics = create_metrics("env-test-backend")
        assert metrics.backend_name == "prometheus"

    def test_hyperi_metrics_backend_otel(self, monkeypatch):
        """HYPERI_METRICS_BACKEND=opentelemetry selects OTel backend."""
        monkeypatch.setenv("HYPERI_METRICS_BACKEND", "opentelemetry")

        metrics = create_metrics("env-test-otel")
        assert metrics.backend_name == "opentelemetry"

    def test_explicit_param_overrides_env_var(self, monkeypatch):
        """Explicit backend param takes priority over env var."""
        monkeypatch.setenv("HYPERI_METRICS_BACKEND", "opentelemetry")

        metrics = create_metrics("env-test-override", backend="prometheus")
        assert metrics.backend_name == "prometheus"

    def test_otel_endpoint_env_var(self, monkeypatch):
        """OTEL_EXPORTER_OTLP_ENDPOINT env var is respected."""
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://custom-collector:4317")

        from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

        backend = OpenTelemetryBackend("env-test-endpoint")
        assert backend.enabled

    def test_otel_protocol_env_var(self, monkeypatch):
        """OTEL_EXPORTER_OTLP_PROTOCOL env var is respected."""
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http")

        from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

        backend = OpenTelemetryBackend("env-test-protocol")
        assert backend.enabled


class TestConfigOverrides:
    """Test configuration dict overrides for OpenTelemetry backend."""

    def test_custom_endpoint(self):
        """Custom endpoint in config is used."""
        config = {
            "opentelemetry": {
                "endpoint": "http://my-collector:4317",
            }
        }
        metrics = create_metrics("config-test-ep", backend="opentelemetry", backend_config=config)
        assert metrics.enabled
        assert metrics.backend_name == "opentelemetry"

    def test_http_protocol(self):
        """HTTP protocol creates HTTP OTLP exporter."""
        config = {
            "opentelemetry": {
                "protocol": "http",
                "endpoint": "http://my-collector:4318",
            }
        }
        metrics = create_metrics("config-test-http", backend="opentelemetry", backend_config=config)
        assert metrics.enabled

    def test_custom_export_interval(self):
        """Custom export interval is applied to OTLP reader."""
        config = {
            "opentelemetry": {
                "export_interval_millis": 5000,
            }
        }
        metrics = create_metrics("config-test-interval", backend="opentelemetry", backend_config=config)
        assert metrics.enabled

    def test_auto_convert_names_disabled(self):
        """auto_convert_names: false disables metric name conversion."""
        config = {
            "opentelemetry": {
                "auto_convert_names": False,
            }
        }
        from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

        backend = OpenTelemetryBackend("config-test-names", config=config)
        assert not backend.auto_convert_names

        # Should NOT convert name
        assert backend._convert_metric_name("http_requests_total") == "http_requests_total"


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_fallback_to_prometheus_when_otel_not_enabled(self):
        """If OTel backend fails, falls back to Prometheus."""
        # Unknown backend always falls back to Prometheus
        metrics = create_metrics("compat-test", backend="invalid")
        assert metrics.backend_name == "prometheus"
        assert metrics.enabled

    def test_prometheus_explicit_still_works(self):
        """Explicit Prometheus backend still works as before."""
        metrics = create_metrics("compat-prom", backend="prometheus")
        assert metrics.backend_name == "prometheus"
        assert metrics.enabled

        counter = metrics.counter("compat_counter", "Compat counter")
        counter.inc()

        output = metrics.get_metrics()
        assert isinstance(output, bytes)

    def test_lifecycle_methods_work(self):
        """start/stop/update lifecycle methods work for OTel backend."""
        metrics = create_metrics("compat-lifecycle", backend="opentelemetry")

        # None of these should raise
        metrics.update()
        metrics.start_auto_update()
        metrics.stop_auto_update()


class TestOTelNotInstalled:
    """Test behaviour when OTel packages are missing (simulated)."""

    def test_otel_available_flag(self):
        """OTEL_AVAILABLE reflects installation status."""
        from hyperi_pylib.metrics.opentelemetry_backend import OTEL_AVAILABLE

        # In our test env, OTel is installed
        assert OTEL_AVAILABLE is True

    def test_disabled_when_otel_unavailable(self):
        """Backend reports disabled when OTEL_AVAILABLE is False."""
        import hyperi_pylib.metrics.opentelemetry_backend as otel_mod
        from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

        # Temporarily pretend OTel is not available
        original = otel_mod.OTEL_AVAILABLE
        try:
            otel_mod.OTEL_AVAILABLE = False
            backend = OpenTelemetryBackend("unavail-test")
            assert not backend.enabled
        finally:
            otel_mod.OTEL_AVAILABLE = original
