"""Unit tests for hs_pylib.prometheus module."""

import time
from unittest import mock

import pytest

# Check if prometheus_client is available
try:
    from prometheus_client import CollectorRegistry

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestProcessMetrics:
    """Test ProcessMetrics class."""

    def test_init(self):
        """Test ProcessMetrics initialization."""
        from hs_pylib.metrics.prometheus import ProcessMetrics

        metrics = ProcessMetrics(app_name="test-app")

        assert metrics.enabled is True
        assert metrics.app_name == "test-app"
        assert metrics.registry is not None

    def test_update(self):
        """Test metric updates."""
        from hs_pylib.metrics.prometheus import ProcessMetrics

        metrics = ProcessMetrics(app_name="test-app")
        metrics.update()

        # Verify metrics were updated (values should be > 0)
        assert metrics.cpu_percent._value.get() >= 0
        assert metrics.memory_rss_bytes._value.get() > 0
        assert metrics.threads_total._value.get() > 0

    def test_uptime_tracking(self):
        """Test uptime metric increases over time."""
        from hs_pylib.metrics.prometheus import ProcessMetrics

        metrics = ProcessMetrics(app_name="test-app")

        # Initial update
        metrics.update()
        uptime1 = metrics.uptime_seconds._value.get()

        # Wait and update again
        time.sleep(0.1)
        metrics.update()
        uptime2 = metrics.uptime_seconds._value.get()

        assert uptime2 > uptime1

    def test_without_prometheus_client(self):
        """Test ProcessMetrics gracefully handles missing prometheus_client."""
        # This is more of a documentation test since we skip if not available
        # In real scenarios without prometheus_client, enabled should be False
        pass


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestContainerMetrics:
    """Test ContainerMetrics class."""

    def test_init_not_container(self):
        """Test ContainerMetrics initialization outside container."""
        from hs_pylib.metrics.prometheus import ContainerMetrics

        with mock.patch("hs_pylib.metrics.prometheus.RuntimeEnvironment") as mock_runtime:
            # Mock non-container environment
            mock_instance = mock_runtime.return_value
            mock_instance._is_container.return_value = (False, "none")

            metrics = ContainerMetrics(app_name="test-app")

            # Should be disabled outside containers
            assert metrics.enabled is False

    def test_init_in_container(self):
        """Test ContainerMetrics initialization in container."""
        from hs_pylib.metrics.prometheus import ContainerMetrics

        with mock.patch("hs_pylib.metrics.prometheus.RuntimeEnvironment") as mock_runtime:
            # Mock container environment
            mock_instance = mock_runtime.return_value
            mock_instance._is_container.return_value = (True, "kubernetes")

            with mock.patch.object(ContainerMetrics, "_read_container_limits"):
                metrics = ContainerMetrics(app_name="test-app")

                assert metrics.enabled is True
                assert metrics.is_container is True
                assert metrics.detection_method == "kubernetes"

    def test_read_cgroup_memory_limit(self):
        """Test reading memory limit from cgroups."""
        from hs_pylib.metrics.prometheus import ContainerMetrics

        with mock.patch("hs_pylib.runtime.RuntimeEnvironment") as mock_runtime:
            mock_instance = mock_runtime.return_value
            mock_instance._is_container.return_value = (True, "docker")

            metrics = ContainerMetrics(app_name="test-app")

            # Mock cgroup file reading
            mock_open = mock.mock_open(read_data="1073741824")  # 1GB
            with mock.patch("builtins.open", mock_open):
                limit = metrics._read_cgroup_memory_limit()

                assert limit == 1073741824

    def test_read_cgroup_memory_unlimited(self):
        """Test reading unlimited memory from cgroups."""
        from hs_pylib.metrics.prometheus import ContainerMetrics

        with mock.patch("hs_pylib.runtime.RuntimeEnvironment") as mock_runtime:
            mock_instance = mock_runtime.return_value
            mock_instance._is_container.return_value = (True, "docker")

            metrics = ContainerMetrics(app_name="test-app")

            # Mock "max" (unlimited) and psutil to avoid /proc/meminfo issues
            mock_open = mock.mock_open(read_data="max")
            with (
                mock.patch("builtins.open", mock_open),
                mock.patch("psutil.virtual_memory") as mock_vm,
            ):
                mock_vm.return_value.total = 16 * 1024 * 1024 * 1024  # 16GB
                limit = metrics._read_cgroup_memory_limit()

                # Should return system memory
                assert limit == 16 * 1024 * 1024 * 1024

    def test_read_cgroup_cpu_quota(self):
        """Test reading CPU quota from cgroups."""
        from hs_pylib.metrics.prometheus import ContainerMetrics

        with mock.patch("hs_pylib.runtime.RuntimeEnvironment") as mock_runtime:
            mock_instance = mock_runtime.return_value
            mock_instance._is_container.return_value = (True, "docker")

            metrics = ContainerMetrics(app_name="test-app")

            # Mock CPU quota (2 cores = 200000/100000)
            mock_open = mock.mock_open(read_data="200000 100000")
            with mock.patch("builtins.open", mock_open):
                quota = metrics._read_cgroup_cpu_quota()

                assert quota == 2.0


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestHTTPMetrics:
    """Test HTTPMetrics class."""

    def test_init(self):
        """Test HTTPMetrics initialization."""
        from hs_pylib.metrics.prometheus import HTTPMetrics

        metrics = HTTPMetrics(app_name="test-app")

        assert metrics.enabled is True
        assert metrics.app_name == "test-app"
        assert metrics.registry is not None

    def test_track_request(self):
        """Test tracking HTTP request."""
        from hs_pylib.metrics.prometheus import HTTPMetrics

        metrics = HTTPMetrics(app_name="test-app")

        # Track a request
        metrics.track_request(
            method="GET",
            endpoint="/api/users",
            status=200,
            duration=0.123,
        )

        # Verify counter was incremented
        counter_value = metrics.requests_total.labels(
            method="GET",
            endpoint="/api/users",
            status="200",
        )._value.get()

        assert counter_value == 1

    def test_track_request_size(self):
        """Test tracking request size."""
        from hs_pylib.metrics.prometheus import HTTPMetrics

        metrics = HTTPMetrics(app_name="test-app")

        metrics.track_request_size(1024)
        metrics.track_request_size(2048)

        # Histogram should have observations
        assert metrics.request_size_bytes._sum.get() == 3072

    def test_track_response_size(self):
        """Test tracking response size."""
        from hs_pylib.metrics.prometheus import HTTPMetrics

        metrics = HTTPMetrics(app_name="test-app")

        metrics.track_response_size(512)
        metrics.track_response_size(1024)

        # Histogram should have observations
        assert metrics.response_size_bytes._sum.get() == 1536


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestPrometheusMetrics:
    """Test PrometheusMetrics unified manager."""

    def test_init(self):
        """Test PrometheusMetrics initialization."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test-app", enable_auto_update=False)

        assert metrics.enabled is True
        assert metrics.app_name == "test-app"
        assert metrics.registry is not None
        assert metrics.process is not None
        assert metrics.container is not None
        assert metrics.http is not None

    def test_update(self):
        """Test manual metric update."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test-app", enable_auto_update=False)

        # Should not raise
        metrics.update()

    def test_get_metrics(self):
        """Test metrics output generation."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test-app", enable_auto_update=False)
        metrics.update()

        output = metrics.get_metrics()

        assert isinstance(output, bytes)
        assert b"process_cpu_percent" in output
        assert b"process_memory_rss_bytes" in output
        assert b"process_threads_total" in output

    def test_get_metrics_text(self):
        """Test metrics text output."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test-app", enable_auto_update=False)
        metrics.update()

        output = metrics.get_metrics_text()

        assert isinstance(output, str)
        assert "process_cpu_percent" in output
        assert "process_memory_rss_bytes" in output

    def test_auto_update(self):
        """Test automatic metric updates."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(
            app_name="test-app",
            enable_auto_update=True,
            update_interval=0.1,
        )

        try:
            # Wait for at least one update
            time.sleep(0.2)

            # Metrics should have been updated
            uptime = metrics.process.uptime_seconds._value.get()
            assert uptime > 0

        finally:
            metrics.stop_auto_update()

    def test_stop_auto_update(self):
        """Test stopping automatic updates."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(
            app_name="test-app",
            enable_auto_update=True,
            update_interval=0.1,
        )

        assert metrics.update_thread is not None
        assert metrics.update_thread.is_alive()

        metrics.stop_auto_update()

        # Thread should have stopped
        assert metrics.shutdown_event.is_set()

    def test_get_content_type(self):
        """Test content type for HTTP responses."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test-app", enable_auto_update=False)

        content_type = metrics.get_content_type()

        assert "text/plain" in content_type


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestConvenienceFunction:
    """Test create_metrics convenience function."""

    def test_create_metrics(self):
        """Test create_metrics function."""
        from hs_pylib.metrics.prometheus import create_metrics

        metrics = create_metrics("test-app", enable_auto_update=False)

        assert metrics.enabled is True
        assert metrics.app_name == "test-app"

    def test_create_metrics_with_auto_update(self):
        """Test create_metrics with auto-update."""
        from hs_pylib.metrics.prometheus import create_metrics

        metrics = create_metrics(
            "test-app",
            enable_auto_update=True,
            update_interval=0.1,
        )

        try:
            assert metrics.update_thread is not None
        finally:
            metrics.stop_auto_update()


class TestWithoutPrometheusClient:
    """Test behavior when prometheus_client is not available."""

    def test_prometheus_not_available(self):
        """Test that module handles missing prometheus_client."""
        from hs_pylib.metrics import prometheus

        # If prometheus_client is not available, PROMETHEUS_AVAILABLE should be False
        if not PROMETHEUS_AVAILABLE:
            assert prometheus.PROMETHEUS_AVAILABLE is False


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestCustomMetrics:
    """Test custom metrics API."""

    def test_counter(self):
        """Test creating and using custom counter."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create counter
        requests = metrics.counter(
            "my_requests_total",
            "Total requests",
            labels=["method"],
        )

        # Increment
        requests.labels(method="GET").inc()
        requests.labels(method="POST").inc(5)

        # Verify in output
        output = metrics.get_metrics_text()
        assert "my_requests_total" in output
        assert 'method="GET"' in output
        assert 'method="POST"' in output

    def test_gauge(self):
        """Test creating and using custom gauge."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create gauge
        queue_size = metrics.gauge("queue_size", "Number of items in queue")

        # Set value
        queue_size.set(42)

        # Verify in output
        output = metrics.get_metrics_text()
        assert "queue_size" in output
        assert "42" in output

    def test_histogram(self):
        """Test creating and using custom histogram."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create histogram
        duration = metrics.histogram(
            "processing_seconds",
            "Processing time",
        )

        # Observe values
        duration.observe(0.123)
        duration.observe(0.456)

        # Verify in output
        output = metrics.get_metrics_text()
        assert "processing_seconds" in output

    def test_histogram_custom_buckets(self):
        """Test histogram with custom buckets."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create histogram with custom buckets
        latency = metrics.histogram(
            "api_latency_seconds",
            "API latency",
            buckets=(0.01, 0.1, 1.0, 10.0),
        )

        latency.observe(0.05)

        output = metrics.get_metrics_text()
        assert "api_latency_seconds" in output

    def test_summary(self):
        """Test creating and using custom summary."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create summary
        response_time = metrics.summary(
            "response_time_seconds",
            "Response time distribution",
        )

        # Observe values
        response_time.observe(0.123)

        # Verify in output
        output = metrics.get_metrics_text()
        assert "response_time_seconds" in output

    def test_info(self):
        """Test creating and using custom info."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create info
        app_info = metrics.info("custom_app", "Application info")

        # Set info
        app_info.info(
            {
                "version": "1.2.3",
                "environment": "test",
            }
        )

        # Verify in output
        output = metrics.get_metrics_text()
        assert "custom_app_info" in output
        assert "version" in output
        assert "1.2.3" in output

    def test_get_custom_metric(self):
        """Test retrieving custom metric by name."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create metric
        counter = metrics.counter("my_counter", "Test counter")

        # Retrieve it
        retrieved = metrics.get_custom_metric("my_counter")

        assert retrieved is counter

    def test_metric_reuse(self):
        """Test that creating same metric twice returns same instance."""
        from hs_pylib.metrics.prometheus import PrometheusMetrics

        metrics = PrometheusMetrics(app_name="test", enable_auto_update=False)

        # Create metric
        counter1 = metrics.counter("reused_counter", "Test counter")

        # Create again with same name
        counter2 = metrics.counter("reused_counter", "Test counter")

        # Should be same instance
        assert counter1 is counter2


@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestIntegration:
    """Integration tests for prometheus metrics."""

    def test_full_workflow(self):
        """Test complete metrics workflow."""
        from hs_pylib.metrics.prometheus import create_metrics

        # Create metrics manager
        metrics = create_metrics("integration-test", enable_auto_update=False)

        # Update process metrics
        metrics.update()

        # Track HTTP requests
        metrics.http.track_request("GET", "/api/users", 200, 0.123)
        metrics.http.track_request("POST", "/api/users", 201, 0.456)
        metrics.http.track_request_size(1024)
        metrics.http.track_response_size(2048)

        # Generate metrics output
        output = metrics.get_metrics_text()

        # Verify all metric types are present
        assert "process_cpu_percent" in output
        assert "process_memory_rss_bytes" in output
        assert "process_threads_total" in output
        assert "http_requests_total" in output
        assert "http_request_duration_seconds" in output

    def test_full_workflow_with_custom_metrics(self):
        """Test workflow including custom metrics."""
        from hs_pylib.metrics.prometheus import create_metrics

        metrics = create_metrics("integration-test", enable_auto_update=False)

        # Add custom metrics
        api_calls = metrics.counter("api_calls_total", "Total API calls", labels=["service"])
        cache_size = metrics.gauge("cache_entries", "Number of cache entries")
        processing_time = metrics.histogram("processing_seconds", "Processing time")

        # Use metrics
        api_calls.labels(service="database").inc()
        cache_size.set(1000)
        processing_time.observe(0.5)

        # Update built-in metrics
        metrics.update()

        # Generate output
        output = metrics.get_metrics_text()

        # Verify all are present
        assert "process_cpu_percent" in output
        assert "api_calls_total" in output
        assert "cache_entries" in output
        assert "processing_seconds" in output

    def test_shared_registry(self):
        """Test that all metrics use same registry."""
        from hs_pylib.metrics.prometheus import HTTPMetrics, ProcessMetrics

        registry = CollectorRegistry()

        process_metrics = ProcessMetrics(registry=registry, app_name="test")
        http_metrics = HTTPMetrics(registry=registry, app_name="test")

        process_metrics.update()
        http_metrics.track_request("GET", "/test", 200, 0.1)

        # Both should be in same output
        from prometheus_client import generate_latest

        output = generate_latest(registry).decode()

        assert "process_cpu_percent" in output
        assert "http_requests_total" in output
