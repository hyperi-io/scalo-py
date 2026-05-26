"""
Tests for metrics backend abstraction.

Tests both Prometheus and OpenTelemetry backends with unified API.
"""

import pytest

from hyperi_pylib.metrics import MetricsManager, create_metrics


class TestPrometheusBackend:
    """Test Prometheus backend implementation."""

    def test_create_with_prometheus_backend(self):
        """Test creating metrics with explicit Prometheus backend."""
        metrics = create_metrics("test-app", backend="prometheus")

        assert metrics.enabled
        assert metrics.backend_name == "prometheus"

    def test_counter_creation(self):
        """Test counter creation with Prometheus backend."""
        metrics = create_metrics("test-app", backend="prometheus")

        counter = metrics.counter("test_requests", "Test requests")
        assert counter is not None

        # Test increment
        counter.inc()
        counter.inc(5)

    def test_gauge_creation(self):
        """Test gauge creation with Prometheus backend."""
        metrics = create_metrics("test-app", backend="prometheus")

        gauge = metrics.gauge("test_queue_size", "Test queue size")
        assert gauge is not None

        # Test set/inc/dec
        gauge.set(42)
        gauge.inc()
        gauge.dec(2)

    def test_histogram_creation(self):
        """Test histogram creation with Prometheus backend."""
        metrics = create_metrics("test-app", backend="prometheus")

        histogram = metrics.histogram("test_latency", "Test latency")
        assert histogram is not None

        # Test observe
        histogram.observe(0.123)
        histogram.observe(0.456)

    def test_get_metrics_prometheus(self):
        """Test getting metrics in Prometheus format."""
        metrics = create_metrics("test-app", backend="prometheus")

        # Create some metrics
        counter = metrics.counter("test_total", "Test total")
        counter.inc()

        # Get metrics
        metrics_bytes = metrics.get_metrics()
        assert isinstance(metrics_bytes, bytes)
        assert b"test_total" in metrics_bytes or b"Prometheus" in metrics_bytes

    def test_content_type_prometheus(self):
        """Test Prometheus content type."""
        metrics = create_metrics("test-app", backend="prometheus")

        content_type = metrics.get_content_type()
        assert "text" in content_type.lower() or "prometheus" in content_type.lower()

    def test_backward_compatibility_prometheus_metrics(self):
        """Test backward compatibility with PrometheusMetrics."""
        from hyperi_pylib.metrics import PrometheusMetrics

        # Old API should still work
        metrics = PrometheusMetrics("test-app", enable_auto_update=False)

        assert metrics.enabled
        counter = metrics.counter("old_style_counter", "Old style")
        counter.inc()


try:
    import opentelemetry

    OTEL_INSTALLED = True
except ImportError:
    OTEL_INSTALLED = False

otel_required = pytest.mark.skipif(not OTEL_INSTALLED, reason="OpenTelemetry not installed")


class TestOpenTelemetryBackend:
    """Test OpenTelemetry backend implementation."""

    def test_create_with_otel_backend(self):
        """Test creating metrics with OpenTelemetry backend."""
        try:
            metrics = create_metrics("test-app", backend="opentelemetry")
            assert metrics.backend_name == "opentelemetry"
        except ImportError:
            pytest.skip("OpenTelemetry not installed")

    @otel_required
    def test_counter_prometheus_style_api(self):
        """OTel counter supports .labels().inc() (prometheus-client style)."""
        metrics = create_metrics("otel-prom-api-1", backend="opentelemetry")
        if not metrics.enabled:
            pytest.skip("OpenTelemetry backend not enabled")

        counter = metrics.counter("otel_http_requests_total", "Requests", labels=["method", "status"])
        assert counter is not None

        # prometheus-client style -- must not raise
        counter.labels(method="GET", status="200").inc()
        counter.labels(method="POST", status="201").inc(3)

        # Unlabelled shorthand
        counter.inc()

        # Native OTel add() passthrough still works
        counter.add(1)

    @otel_required
    def test_gauge_prometheus_style_api(self):
        """OTel gauge supports .labels().set()/.inc()/.dec()."""
        metrics = create_metrics("otel-prom-api-2", backend="opentelemetry")
        if not metrics.enabled:
            pytest.skip("OpenTelemetry backend not enabled")

        gauge = metrics.gauge("otel_queue_size", "Queue depth", labels=["queue"])
        assert gauge is not None

        # Labelled
        gauge.labels(queue="default").set(42)
        gauge.labels(queue="default").inc(5)
        gauge.labels(queue="default").dec(2)

        # Unlabelled
        gauge.set(10)
        gauge.inc()
        gauge.dec()

    @otel_required
    def test_gauge_set_is_absolute(self):
        """Gauge .set() is absolute, not a delta -- subsequent reads reflect the set value."""
        from hyperi_pylib.metrics.opentelemetry_backend import OtelGaugeAdapter

        metrics = create_metrics("otel-prom-api-3", backend="opentelemetry")
        if not metrics.enabled:
            pytest.skip("OpenTelemetry backend not enabled")

        gauge = metrics.gauge("otel_abs_gauge", "Absolute gauge")

        # Internal state tracking must reflect absolute values
        assert isinstance(gauge, OtelGaugeAdapter)
        gauge.set(100)
        key = ()  # no attributes
        assert gauge._current[key] == 100.0
        gauge.set(50)
        assert gauge._current[key] == 50.0

    @otel_required
    def test_histogram_prometheus_style_api(self):
        """OTel histogram supports .labels().observe()."""
        metrics = create_metrics("otel-prom-api-4", backend="opentelemetry")
        if not metrics.enabled:
            pytest.skip("OpenTelemetry backend not enabled")

        hist = metrics.histogram("otel_request_duration_seconds", "Latency", labels=["method"])
        assert hist is not None

        # prometheus-client style -- must not raise
        hist.labels(method="GET").observe(0.123)
        hist.labels(method="POST").observe(0.456)

        # Unlabelled shorthand
        hist.observe(0.789)

        # Native OTel record() passthrough still works
        hist.record(0.001)

    @otel_required
    def test_label_name_conversion(self):
        """Labels are converted to OTel attribute names when auto_convert_names is on."""
        from hyperi_pylib.metrics.opentelemetry_backend import OtelCounterAdapter

        metrics = create_metrics("otel-prom-api-5", backend="opentelemetry")
        if not metrics.enabled:
            pytest.skip("OpenTelemetry backend not enabled")

        counter = metrics.counter("http_requests_total", "Requests", labels=["method", "status"])
        assert isinstance(counter, OtelCounterAdapter)

        # .labels() with prometheus names should produce OTel attribute names internally
        bound = counter.labels(method="GET", status="200")
        # http.method and http.status_code are the expected OTel names
        assert bound._attributes.get("http.method") == "GET"

    def test_fallback_to_prometheus(self):
        """Test fallback to Prometheus if OpenTelemetry not available."""
        # This test assumes opentelemetry is NOT installed
        # If installed, it will use OTel (which is fine)
        metrics = create_metrics("test-app", backend="opentelemetry")

        # Should always have a working backend (Prometheus fallback)
        assert metrics.backend_name in ["opentelemetry", "prometheus"]
        assert metrics.counter is not None


class TestBackendAbstraction:
    """Test backend abstraction and switching."""

    def test_default_backend_is_opentelemetry(self):
        """Test that default backend is OpenTelemetry (falls back to Prometheus if not installed)."""
        metrics = create_metrics("test-app")

        # OTel is the default; falls back to Prometheus if OTel packages missing
        assert metrics.backend_name in ["opentelemetry", "prometheus"]

    def test_backend_switching(self):
        """Test switching backends via parameter."""
        # Prometheus
        prom_metrics = create_metrics("test-app", backend="prometheus")
        assert prom_metrics.backend_name == "prometheus"

        # OpenTelemetry (may fall back to Prometheus)
        otel_metrics = create_metrics("test-app", backend="opentelemetry")
        assert otel_metrics.backend_name in ["opentelemetry", "prometheus"]

    def test_unknown_backend_falls_back(self):
        """Test that unknown backend falls back to Prometheus."""
        metrics = create_metrics("test-app", backend="invalid_backend")

        assert metrics.backend_name == "prometheus"
        assert metrics.enabled

    def test_unified_api_counter(self):
        """Test that counter API works the same across backends."""
        # Prometheus
        prom_metrics = create_metrics("test-app-1", backend="prometheus")
        prom_counter = prom_metrics.counter("unified_counter", "Unified counter")
        assert prom_counter is not None

        # OpenTelemetry (may fall back)
        otel_metrics = create_metrics("test-app-2", backend="opentelemetry")
        otel_counter = otel_metrics.counter("unified_counter", "Unified counter")
        assert otel_counter is not None

    def test_unified_api_gauge(self):
        """Test that gauge API works the same across backends."""
        # Prometheus
        prom_metrics = create_metrics("test-app-3", backend="prometheus")
        prom_gauge = prom_metrics.gauge("unified_gauge", "Unified gauge")
        assert prom_gauge is not None

        # OpenTelemetry
        otel_metrics = create_metrics("test-app-4", backend="opentelemetry")
        otel_gauge = otel_metrics.gauge("unified_gauge", "Unified gauge")
        assert otel_gauge is not None

    def test_unified_api_histogram(self):
        """Test that histogram API works the same across backends."""
        # Prometheus
        prom_metrics = create_metrics("test-app-5", backend="prometheus")
        prom_hist = prom_metrics.histogram("unified_hist", "Unified histogram")
        assert prom_hist is not None

        # OpenTelemetry
        otel_metrics = create_metrics("test-app-6", backend="opentelemetry")
        otel_hist = otel_metrics.histogram("unified_hist", "Unified histogram")
        assert otel_hist is not None

    def test_get_metrics_returns_bytes(self):
        """Test that get_metrics() returns bytes for all backends."""
        for backend in ["prometheus", "opentelemetry"]:
            metrics = create_metrics(f"test-app-{backend}", backend=backend)
            metrics_bytes = metrics.get_metrics()

            assert isinstance(metrics_bytes, bytes)
            assert len(metrics_bytes) > 0

    def test_lifecycle_methods(self):
        """Test that lifecycle methods work for all backends."""
        for backend in ["prometheus", "opentelemetry"]:
            metrics = create_metrics(f"test-app-{backend}", backend=backend)

            # Should not raise
            metrics.update()
            metrics.stop_auto_update()
            metrics.start_auto_update()
