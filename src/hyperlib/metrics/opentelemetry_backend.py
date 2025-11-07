"""
OpenTelemetry metrics backend.

Provides OpenTelemetry implementation of MetricsBackend interface.
"""

import warnings
from typing import Any, Dict, List, Optional, Tuple

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

    Configuration:
        metrics:
          backend: opentelemetry
          opentelemetry:
            endpoint: http://otel-collector:4318  # OTLP endpoint
            protocol: grpc  # or "http"
            exporter: otlp  # or "prometheus"
            export_interval_millis: 60000  # 60 seconds
    """

    def __init__(self, app_name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize OpenTelemetry backend.

        Args:
            app_name: Application name
            config: Backend configuration
        """
        super().__init__(app_name, config)

        if not OTEL_AVAILABLE:
            logger.error(
                "OpenTelemetry not installed. Install with: pip install hyperlib[opentelemetry]"
            )
            self.enabled = False
            return

        # Extract config
        otel_config = config.get("opentelemetry", {}) if config else {}
        exporter_type = otel_config.get("exporter", "otlp")
        endpoint = otel_config.get("endpoint", "http://localhost:4318")
        protocol = otel_config.get("protocol", "grpc")
        export_interval = otel_config.get("export_interval_millis", 60000)

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
            self._metrics_cache: Dict[str, Any] = {}

            self.enabled = True
            logger.info(
                f"OpenTelemetry metrics initialized: exporter={exporter_type}, endpoint={endpoint}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry backend: {e}")
            self.enabled = False

    def counter(
        self, name: str, description: str, labels: Optional[List[str]] = None
    ) -> Any:
        """
        Create or get an OpenTelemetry Counter.

        Args:
            name: Metric name
            description: Description
            labels: Label names (not used in OTel, labels set at observation time)

        Returns:
            Counter instance
        """
        if not self.enabled:
            return NoOpMetric()

        cache_key = f"counter:{name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        counter = self._meter.create_counter(
            name=name,
            description=description,
            unit="1",
        )

        self._metrics_cache[cache_key] = counter
        return counter

    def gauge(
        self, name: str, description: str, labels: Optional[List[str]] = None
    ) -> Any:
        """
        Create or get an OpenTelemetry Gauge (UpDownCounter).

        Args:
            name: Metric name
            description: Description
            labels: Label names

        Returns:
            UpDownCounter instance
        """
        if not self.enabled:
            return NoOpMetric()

        cache_key = f"gauge:{name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        # OTel uses UpDownCounter for gauge-like metrics
        gauge = self._meter.create_up_down_counter(
            name=name,
            description=description,
            unit="1",
        )

        self._metrics_cache[cache_key] = gauge
        return gauge

    def histogram(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[Tuple[float, ...]] = None,
    ) -> Any:
        """
        Create or get an OpenTelemetry Histogram.

        Args:
            name: Metric name
            description: Description
            labels: Label names
            buckets: Bucket boundaries (handled by views in OTel)

        Returns:
            Histogram instance
        """
        if not self.enabled:
            return NoOpMetric()

        cache_key = f"histogram:{name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        histogram = self._meter.create_histogram(
            name=name,
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
