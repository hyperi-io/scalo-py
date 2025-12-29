"""
Prometheus metrics backend.

Wraps existing PrometheusMetrics implementation to conform to
MetricsBackend interface.
"""

from typing import Any

from .base import MetricsBackend
from .prometheus import PrometheusMetrics


class PrometheusBackend(MetricsBackend):
    """
    Prometheus implementation of MetricsBackend.

    Wraps the existing PrometheusMetrics class to provide
    backend-agnostic interface.
    """

    def __init__(
        self,
        app_name: str,
        enable_auto_update: bool = True,
        update_interval: int = 5,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize Prometheus backend.

        Args:
            app_name: Application name
            enable_auto_update: Start background metric updates
            update_interval: Seconds between updates
            config: Backend-specific configuration (unused for Prometheus)
        """
        super().__init__(app_name, config)

        # Create underlying Prometheus metrics instance
        self._metrics = PrometheusMetrics(
            app_name=app_name,
            enable_auto_update=enable_auto_update,
            update_interval=update_interval,
        )

        self.enabled = self._metrics.enabled

        # Expose process/container/http for backward compatibility
        if self.enabled:
            self.process = self._metrics.process
            self.container = self._metrics.container
            self.http = self._metrics.http

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """Create or get a Prometheus Counter."""
        return self._metrics.counter(name, description, labels)

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """Create or get a Prometheus Gauge."""
        return self._metrics.gauge(name, description, labels)

    def histogram(
        self,
        name: str,
        description: str,
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Any:
        """Create or get a Prometheus Histogram."""
        return self._metrics.histogram(name, description, labels, buckets)

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus text format."""
        return self._metrics.get_metrics()

    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return self._metrics.get_content_type()

    def start_auto_update(self) -> None:
        """Start background metric collection."""
        self._metrics.start_auto_update()

    def stop_auto_update(self) -> None:
        """Stop background metric collection."""
        self._metrics.stop_auto_update()

    def update(self) -> None:
        """Update metrics immediately."""
        self._metrics.update()
