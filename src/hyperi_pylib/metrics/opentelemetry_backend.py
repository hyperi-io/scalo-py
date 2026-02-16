"""
OpenTelemetry metrics backend with dual export.

Provides OpenTelemetry implementation of MetricsBackend interface with
simultaneous OTLP push and Prometheus scrape support.

A single MeterProvider with multiple MetricReaders means every metric
observation is seen by ALL readers automatically - no duplication needed.

Configuration (settings.yaml):
    metrics:
      backend: opentelemetry
      opentelemetry:
        endpoint: http://otel-collector:4317    # or OTEL_EXPORTER_OTLP_ENDPOINT
        protocol: grpc                           # grpc|http, or OTEL_EXPORTER_OTLP_PROTOCOL
        export_interval_millis: 60000
        prometheus_scrape: true                  # also expose /metrics (default: true)
        auto_convert_names: true                 # Prometheus->OTEL name conversion
        service_version: "1.0.0"
"""

import os
from typing import Any

from ..logger import logger
from .base import MetricsBackend, NoOpMetric

# Try to import OpenTelemetry SDK
try:
    from opentelemetry import metrics
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Try to import prometheus_client for generate_latest
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except ImportError:
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"


def _create_otlp_exporter(protocol: str, endpoint: str) -> Any:
    """Create OTLP exporter based on protocol selection.

    Args:
        protocol: "grpc" or "http"
        endpoint: Collector endpoint URL

    Returns:
        OTLP metric exporter instance
    """
    if protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        return OTLPMetricExporter(endpoint=endpoint)
    else:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        return OTLPMetricExporter(endpoint=endpoint)


class OpenTelemetryBackend(MetricsBackend):
    """
    OpenTelemetry implementation of MetricsBackend with dual export.

    By default, attaches BOTH an OTLP push exporter AND a Prometheus scrape
    reader to a single MeterProvider. Every counter.add(1) is observed by
    all readers automatically.

    **Dual export architecture:**

    ::

        Application -> MetricsManager -> OpenTelemetryBackend
                                             |
                                         MeterProvider
                                           /        \\
              PeriodicExportingMetricReader    PrometheusMetricReader
                        |                            |
                  OTLP Collector              /metrics endpoint
                   (push)                      (scrape)

    **Prometheus->OTEL Name Conversion:**

    Automatically converts Prometheus metric names to OTEL semantic conventions.
    Developers write Prometheus-style names, backend converts to OTEL standards.

    Example:
        - http_requests_total -> http.server.request.count
        - http_request_duration_seconds -> http.server.request.duration
        - task_execution_total -> task.execution.count
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

    # Label name mappings (Prometheus -> OTEL)
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
        Initialise OpenTelemetry backend with dual export support.

        Reads configuration from the provided dict and falls back to standard
        OTel environment variables (OTEL_EXPORTER_OTLP_ENDPOINT, etc.).

        Args:
            app_name: Application name
            config: Backend configuration dict
        """
        super().__init__(app_name, config)

        if not OTEL_AVAILABLE:
            logger.error("OpenTelemetry not installed. Install with: pip install hyperi-pylib[opentelemetry]")
            self.enabled = False
            return

        otel_config = config.get("opentelemetry", {}) if config else {}

        # Resolve endpoint: config > env var > default
        endpoint = otel_config.get(
            "endpoint",
            os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        )

        # Resolve protocol: config > env var > default
        protocol = otel_config.get(
            "protocol",
            os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc"),
        )

        export_interval = otel_config.get("export_interval_millis", 60000)
        prometheus_scrape = otel_config.get("prometheus_scrape", True)
        self.auto_convert_names = otel_config.get("auto_convert_names", True)

        # Create resource (app metadata)
        service_version = otel_config.get("service_version", "1.0.0")
        resource = Resource.create(
            {
                "service.name": app_name,
                "service.version": service_version,
            }
        )

        try:
            metric_readers = []
            readers_desc = []

            # OTLP push reader (always created unless endpoint explicitly empty)
            if endpoint:
                otlp_exporter = _create_otlp_exporter(protocol, endpoint)
                otlp_reader = PeriodicExportingMetricReader(
                    exporter=otlp_exporter,
                    export_interval_millis=export_interval,
                )
                metric_readers.append(otlp_reader)
                readers_desc.append(f"otlp({protocol})->{endpoint}")

            # Prometheus scrape reader (enabled by default)
            self._prometheus_reader = None
            if prometheus_scrape:
                self._prometheus_reader = PrometheusMetricReader()
                metric_readers.append(self._prometheus_reader)
                readers_desc.append("prometheus(/metrics)")

            if not metric_readers:
                logger.error("No metric readers configured — at least one of OTLP or Prometheus required")
                self.enabled = False
                return

            # Single MeterProvider with all readers
            self._provider = MeterProvider(
                resource=resource,
                metric_readers=metric_readers,
            )

            # Set global meter provider
            metrics.set_meter_provider(self._provider)

            # Get meter for this app
            self._meter = metrics.get_meter(app_name)

            # Cache for created metrics
            self._metrics_cache: dict[str, Any] = {}

            self.enabled = True
            logger.info(f"OpenTelemetry metrics initialised: readers=[{', '.join(readers_desc)}]")

        except Exception as e:
            logger.error(f"Failed to initialise OpenTelemetry backend: {e}")
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

        otel_name = self.PROMETHEUS_TO_OTEL.get(prometheus_name)

        if otel_name:
            logger.debug(f"Converted metric name: {prometheus_name} -> {otel_name}")
            return otel_name

        logger.debug(f"No OTEL mapping for '{prometheus_name}', using original name")
        return prometheus_name

    def _convert_labels(self, labels: dict[str, Any]) -> dict[str, Any]:
        """
        Convert Prometheus label names to OTEL attribute names.

        Args:
            labels: Prometheus-style labels (e.g., {{"method": "GET", "status": "200"}})

        Returns:
            OTEL-style attributes (e.g., {{"http.method": "GET", "http.status_code": "200"}})
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
        """
        if not self.enabled:
            return NoOpMetric()

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

        otel_name = self._convert_metric_name(name)

        cache_key = f"gauge:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

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
        """
        if not self.enabled:
            return NoOpMetric()

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
        Get metrics in Prometheus exposition format.

        When a PrometheusMetricReader is attached (prometheus_scrape: true),
        this returns actual Prometheus-format metrics via generate_latest().
        Applications can serve this from their own /metrics endpoint.

        When only OTLP is active, returns an informational message since
        metrics are pushed automatically to the collector.

        Returns:
            Metrics as bytes in Prometheus text format
        """
        if not self.enabled:
            return b"# OpenTelemetry metrics not available\n"

        # If Prometheus scrape reader is active, return real metrics
        if self._prometheus_reader is not None and generate_latest is not None:
            from prometheus_client import REGISTRY

            return generate_latest(REGISTRY)

        # OTLP-only mode
        return (
            b"# OpenTelemetry OTLP exporter active\n"
            b"# Metrics are pushed automatically to collector\n"
            b"# No scraping endpoint needed\n"
        )

    def get_content_type(self) -> str:
        """Get content type for metrics endpoint."""
        if self._prometheus_reader is not None and CONTENT_TYPE_LATEST:
            return CONTENT_TYPE_LATEST
        return "text/plain; version=0.0.4"

    def start_auto_update(self) -> None:
        """
        Start automatic metric collection.

        OTel uses periodic exporting, so this is a no-op.
        """
        pass

    def stop_auto_update(self) -> None:
        """
        Stop automatic metric collection.

        Shuts down the MeterProvider which flushes and stops all readers.
        """
        if self.enabled and hasattr(self, "_provider"):
            try:
                self._provider.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down OpenTelemetry: {e}")

    def update(self) -> None:
        """
        Update metrics immediately.

        Forces a flush of all metric readers.
        """
        if self.enabled and hasattr(self, "_provider"):
            try:
                self._provider.force_flush()
            except Exception as e:
                logger.debug(f"Force flush failed (may be expected during shutdown): {e}")
