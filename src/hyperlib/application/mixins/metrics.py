"""
MetricsMixin: Auto-instrumentation for application metrics.

This mixin integrates with hyperlib.metrics to provide automatic metrics
collection based on application type (API, Daemon, MCP, Oneshot).
"""

import os
from typing import Any, Dict, Optional

from hyperlib.logger import logger


class MetricsMixin:
    """
    Mixin to add metrics collection to applications.

    Automatically starts metrics server and provides helper methods for
    tracking application-specific metrics. Uses existing hyperlib.metrics module.

    Example:
        class MyAPI(MetricsMixin, ProfileMixin):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

            def handle_request(self):
                self.track_counter("http_requests_total", labels={"endpoint": "/"})
    """

    def __init__(self, **kwargs: Any):
        """
        Initialize metrics mixin.

        Args:
            **kwargs: Additional args passed to next mixin in chain
        """
        self.metrics = None

        # Setup metrics if enabled in profile
        if self._should_setup_metrics():
            self._setup_metrics()

        # Call next mixin in MRO chain
        super().__init__(**kwargs)

    def _should_setup_metrics(self) -> bool:
        """Check if metrics should be enabled based on profile."""
        if hasattr(self, "profile"):
            return self.profile.get("metrics", False)
        return False

    def _setup_metrics(self) -> None:
        """
        Setup metrics collection using hyperlib.metrics.

        Creates metrics backend (Prometheus or OpenTelemetry) and starts
        metrics server on configured port.
        """
        try:
            from hyperlib.metrics import create_metrics

            # Get backend from environment or use Prometheus default
            backend = os.getenv("METRICS_BACKEND", "prometheus")
            port = self.profile.get("metrics_port", 9090)

            logger.info(
                f"Initializing metrics backend '{backend}' on port {port}",
            )

            # Create metrics instance
            self.metrics = create_metrics(
                app_name=self.name if hasattr(self, "name") else "app",
                backend=backend,
            )

            # Start metrics server
            self.metrics.start()

            logger.info(f"Metrics server started on port {port}")

        except ImportError as e:
            logger.warning(f"Metrics module not available: {e}")
            logger.warning("Metrics collection disabled")
        except Exception as e:
            logger.error(f"Failed to setup metrics: {e}", exc_info=True)
            logger.warning("Metrics collection disabled")

    def track_counter(
        self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Track a counter metric.

        Counters are cumulative values that only increase (e.g., request count).

        Args:
            name: Metric name (Prometheus format, e.g., "http_requests_total")
            value: Value to increment by (default: 1)
            labels: Optional labels/tags (e.g., {"method": "GET", "status": "200"})

        Example:
            self.track_counter("http_requests_total", labels={"method": "GET"})
        """
        if self.metrics:
            try:
                counter = self.metrics.counter(name, f"{name} counter")
                counter.inc(value, labels or {})
            except Exception as e:
                logger.debug(f"Failed to track counter '{name}': {e}")

    def track_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Track a gauge metric.

        Gauges are point-in-time values that can go up or down (e.g., queue depth).

        Args:
            name: Metric name (Prometheus format, e.g., "task_queue_depth")
            value: Current value
            labels: Optional labels/tags

        Example:
            self.track_gauge("task_queue_depth", 42)
        """
        if self.metrics:
            try:
                gauge = self.metrics.gauge(name, f"{name} gauge")
                gauge.set(value, labels or {})
            except Exception as e:
                logger.debug(f"Failed to track gauge '{name}': {e}")

    def track_histogram(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Track a histogram metric.

        Histograms track distributions of values (e.g., request duration).

        Args:
            name: Metric name (Prometheus format, e.g., "http_request_duration_seconds")
            value: Observed value
            labels: Optional labels/tags

        Example:
            self.track_histogram("http_request_duration_seconds", 0.123)
        """
        if self.metrics:
            try:
                histogram = self.metrics.histogram(name, f"{name} histogram")
                histogram.observe(value, labels or {})
            except Exception as e:
                logger.debug(f"Failed to track histogram '{name}': {e}")

    def shutdown_metrics(self) -> None:
        """
        Shutdown metrics server.

        Called during application shutdown to clean up metrics resources.
        """
        if self.metrics:
            try:
                logger.debug("Shutting down metrics server")
                self.metrics.stop()
            except Exception as e:
                logger.error(f"Error shutting down metrics: {e}", exc_info=True)
