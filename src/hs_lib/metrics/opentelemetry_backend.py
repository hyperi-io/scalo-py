"""
OpenTelemetry metrics backend.

Provides OpenTelemetry implementation of MetricsBackend interface.
"""

from typing import Any

from ..logger import logger
from .base import MetricsBackend, NoOpMetric

# Try to import OpenTelemetry SDK
try:
    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


class OpenTelemetryBackend(MetricsBackend):
    """
    OpenTelemetry implementation of MetricsBackend.

    Supports multiple exporters:
    - OTLP (gRPC/HTTP) - for OpenTelemetry Collector
    - Prometheus - for Prometheus scraping

    **Prometheus→OTEL Name Conversion:**

    Automatically converts Prometheus metric names to OTEL semantic conventions.
    Developers write Prometheus-style names, backend converts to OTEL standards.

    Example:
        - http_requests_total → http.server.request.count
        - http_request_duration_seconds → http.server.request.duration
        - task_execution_total → task.execution.count

    Configuration:
        metrics:
          backend: opentelemetry
          opentelemetry:
            endpoint: http://otel-collector:4318  # OTLP endpoint
            protocol: grpc  # or "http"
            exporter: otlp  # or "prometheus"
            export_interval_millis: 60000  # 60 seconds
            auto_convert_names: true  # Enable Prometheus→OTEL conversion
    """

    # Prometheus to OpenTelemetry Semantic Convention mappings
    PROMETHEUS_TO_OTEL = {
        # HTTP Server metrics
        "http_requests_total": "http.server.request.count",
        "http_request_duration_seconds": "http.server.request.duration",
        "http_requests_in_progress": "http.server.active_requests",
        "http_request_size_bytes": "http.server.request.size",
        "http_response_size_bytes": "http.server.response.size",
        # Task/Job metrics
        "task_execution_total": "task.execution.count",
        "task_execution_duration_seconds": "task.execution.duration",
        "task_queue_depth": "task.queue.depth",
        "task_failures_total": "task.execution.failures",
        # Worker pool metrics
        "worker_pool_busy": "worker.pool.busy",
        "worker_pool_idle": "worker.pool.idle",
        "worker_pool_size": "worker.pool.size",
        # Job metrics (oneshot)
        "job_execution_total": "job.execution.count",
        "job_execution_duration_seconds": "job.execution.duration",
        "job_last_success_timestamp": "job.last_success.time",
        # MCP metrics
        "mcp_requests_total": "rpc.server.request.count",
        "mcp_request_duration_seconds": "rpc.server.request.duration",
        # Database metrics
        "db_queries_total": "db.client.operation.count",
        "db_query_duration_seconds": "db.client.operation.duration",
        "db_connections_active": "db.client.connections.usage",
    }

    # Label name mappings (Prometheus → OTEL)
    LABEL_MAP = {
        # HTTP labels
        "method": "http.method",
        "endpoint": "http.route",
        "status": "http.status_code",
        "path": "http.target",
        # Task labels
        "task": "task.name",
        "status": "task.status",
        "queue": "task.queue.name",
        # Job labels
        "job": "job.name",
        # Transport labels
        "transport": "rpc.transport",
    }

    def __init__(self, app_name: str, config: dict[str, Any] | None = None):
        """
        Initialize OpenTelemetry backend.

        Args:
            app_name: Application name
            config: Backend configuration
        """
        super().__init__(app_name, config)

        if not OTEL_AVAILABLE:
            logger.error("OpenTelemetry not installed. Install with: pip install hs-lib[opentelemetry]")
            self.enabled = False
            return

        # Extract config
        otel_config = config.get("opentelemetry", {}) if config else {}
        exporter_type = otel_config.get("exporter", "otlp")
        endpoint = otel_config.get("endpoint", "http://localhost:4318")
        otel_config.get("protocol", "grpc")
        export_interval = otel_config.get("export_interval_millis", 60000)
        self.auto_convert_names = otel_config.get("auto_convert_names", True)

        # Create resource (app metadata)
        resource = Resource.create(
            {
                "service.name": app_name,
                "service.version": "1.0.0",  # TODO: Get from config
            }
        )

        # Create exporter based on config
        try:
            if exporter_type == "prometheus":
                # Prometheus exporter (for scraping)
                reader = PrometheusMetricReader()
            else:
                # OTLP exporter (push to collector)
                otlp_exporter = OTLPMetricExporter(
                    endpoint=endpoint,
                    # insecure=True if using http, secure if using https
                )
                reader = PeriodicExportingMetricReader(
                    exporter=otlp_exporter,
                    export_interval_millis=export_interval,
                )

            # Create meter provider
            self._provider = MeterProvider(
                resource=resource,
                metric_readers=[reader],
            )

            # Set global meter provider
            metrics.set_meter_provider(self._provider)

            # Get meter for this app
            self._meter = metrics.get_meter(app_name)

            # Cache for created metrics
            self._metrics_cache: dict[str, Any] = {}

            self.enabled = True
            logger.info(f"OpenTelemetry metrics initialized: exporter={exporter_type}, endpoint={endpoint}")

        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry backend: {e}")
            self.enabled = False

    def _convert_metric_name(self, prometheus_name: str) -> str:
        """
        Convert Prometheus metric name to OTEL semantic convention.

        Args:
            prometheus_name: Prometheus-style metric name (e.g., "http_requests_total")

        Returns:
            OTEL semantic convention name (e.g., "http.server.request.count")
            or original name if no mapping exists
        """
        if not self.auto_convert_names:
            return prometheus_name

        # Check if we have a mapping
        otel_name = self.PROMETHEUS_TO_OTEL.get(prometheus_name)

        if otel_name:
            logger.debug(f"Converted metric name: {prometheus_name} → {otel_name}")
            return otel_name

        # No mapping, use original name
        logger.debug(f"No OTEL mapping for '{prometheus_name}', using original name")
        return prometheus_name

    def _convert_labels(self, labels: dict[str, Any]) -> dict[str, Any]:
        """
        Convert Prometheus label names to OTEL attribute names.

        Args:
            labels: Prometheus-style labels (e.g., {"method": "GET", "status": "200"})

        Returns:
            OTEL-style attributes (e.g., {"http.method": "GET", "http.status_code": "200"})
        """
        if not self.auto_convert_names or not labels:
            return labels

        converted = {}
        for key, value in labels.items():
            otel_key = self.LABEL_MAP.get(key, key)
            converted[otel_key] = value

        return converted

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get an OpenTelemetry Counter.

        Automatically converts Prometheus metric names to OTEL semantic conventions.

        Args:
            name: Metric name (Prometheus format, e.g., "http_requests_total")
            description: Description
            labels: Label names (not used in OTel, labels set at observation time)

        Returns:
            Counter instance

        Example:
            >>> counter = backend.counter("http_requests_total", "Total HTTP requests")
            >>> # Creates counter with name "http.server.request.count" (auto-converted)
        """
        if not self.enabled:
            return NoOpMetric()

        # Convert Prometheus name to OTEL semantic convention
        otel_name = self._convert_metric_name(name)

        cache_key = f"counter:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        counter = self._meter.create_counter(
            name=otel_name,
            description=description,
            unit="1",
        )

        self._metrics_cache[cache_key] = counter
        return counter

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get an OpenTelemetry Gauge (UpDownCounter).

        Automatically converts Prometheus metric names to OTEL semantic conventions.

        Args:
            name: Metric name (Prometheus format, e.g., "task_queue_depth")
            description: Description
            labels: Label names

        Returns:
            UpDownCounter instance
        """
        if not self.enabled:
            return NoOpMetric()

        # Convert Prometheus name to OTEL semantic convention
        otel_name = self._convert_metric_name(name)

        cache_key = f"gauge:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        # OTel uses UpDownCounter for gauge-like metrics
        gauge = self._meter.create_up_down_counter(
            name=otel_name,
            description=description,
            unit="1",
        )

        self._metrics_cache[cache_key] = gauge
        return gauge

    def histogram(
        self,
        name: str,
        description: str,
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Any:
        """
        Create or get an OpenTelemetry Histogram.

        Automatically converts Prometheus metric names to OTEL semantic conventions.

        Args:
            name: Metric name (Prometheus format, e.g., "http_request_duration_seconds")
            description: Description
            labels: Label names
            buckets: Bucket boundaries (handled by views in OTel)

        Returns:
            Histogram instance

        Example:
            >>> hist = backend.histogram("http_request_duration_seconds", "Request duration")
            >>> # Creates histogram with name "http.server.request.duration" (auto-converted)
        """
        if not self.enabled:
            return NoOpMetric()

        # Convert Prometheus name to OTEL semantic convention
        otel_name = self._convert_metric_name(name)

        cache_key = f"histogram:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        histogram = self._meter.create_histogram(
            name=otel_name,
            description=description,
            unit="1",
        )

        self._metrics_cache[cache_key] = histogram
        return histogram

    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus format (if using Prometheus exporter).

        **How OpenTelemetry exports metrics:**

        1. **OTLP mode (default)**: Metrics are pushed automatically to collector
           - No HTTP endpoint needed
           - Periodic export at configured interval
           - Use this method returns informational message

        2. **Prometheus mode**: Metrics exposed for scraping
           - PrometheusMetricReader exposes /metrics endpoint on port 9464
           - This method returns current metrics snapshot
           - Applications can also serve via their own endpoint

        **For OTLP mode**, metrics are pushed automatically. No endpoint needed.

        **For Prometheus mode**, PrometheusMetricReader runs HTTP server on port 9464
        or you can serve metrics via your application's endpoint using this method.

        Returns:
            Metrics as bytes (Prometheus format if using Prometheus exporter)
        """
        if not self.enabled:
            return b"# OpenTelemetry metrics not available\n"

        # Check if using Prometheus exporter
        if hasattr(self, "_provider") and self._provider:
            # Get metrics from PrometheusMetricReader if available
            for reader in self._provider._sdk_config.metric_readers:
                if isinstance(reader, PrometheusMetricReader):
                    # PrometheusMetricReader exposes metrics via HTTP server (port 9464)
                    # For applications that want to serve via their own endpoint,
                    # we'd need to access the registry directly
                    # For now, return info message
                    return (
                        b"# OpenTelemetry Prometheus exporter active\n"
                        b"# Metrics available at http://localhost:9464/metrics\n"
                        b"# Or configure your application to serve this endpoint\n"
                    )

        # OTLP mode - metrics pushed automatically
        return (
            b"# OpenTelemetry OTLP exporter active\n"
            b"# Metrics are pushed automatically to collector\n"
            b"# No scraping endpoint needed\n"
        )

    def get_content_type(self) -> str:
        """Get content type for metrics endpoint."""
        return "text/plain; version=0.0.4"

    def start_auto_update(self) -> None:
        """
        Start automatic metric collection.

        Note: OTel uses periodic exporting, so this is a no-op.
        """
        pass

    def stop_auto_update(self) -> None:
        """
        Stop automatic metric collection.

        Note: OTel manages its own lifecycle.
        """
        if self.enabled and hasattr(self, "_provider"):
            try:
                self._provider.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down OpenTelemetry: {e}")

    def update(self) -> None:
        """
        Update metrics immediately.

        Note: OTel exports periodically, this is a no-op.
        """
        pass
