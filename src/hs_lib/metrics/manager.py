"""
Unified metrics manager with backend abstraction.

Provides backend-agnostic API for application metrics.
"""

from typing import Any

from ..config import get_config
from ..logger import logger
from .base import MetricsBackend, NoOpMetric


class MetricsManager:
    """
    Unified metrics manager that wraps backend implementations.

    Provides consistent API regardless of backend (Prometheus, OpenTelemetry, etc.).

    **Lifecycle Management:**

    Each backend handles its own lifecycle:
    - **Prometheus**: Runs background thread for process/container metrics collection
    - **OpenTelemetry**: Runs periodic exporter for pushing metrics to collector

    Both automatically start/stop services as needed.

    Example:
        >>> from hs_lib.metrics import create_metrics
        >>>
        >>> # Default backend (Prometheus)
        >>> metrics = create_metrics("myapp")
        >>>
        >>> # Or specify backend
        >>> metrics = create_metrics("myapp", backend="opentelemetry")
        >>>
        >>> # Same API regardless of backend
        >>> metrics.counter("requests", "Total requests").inc()
        >>> metrics.gauge("queue_size", "Queue depth").set(42)
        >>> metrics.histogram("latency", "Request latency").observe(0.123)
    """

    def __init__(
        self,
        app_name: str,
        backend: str | None = None,
        enable_auto_update: bool = True,
        update_interval: int = 5,
        backend_config: dict[str, Any] | None = None,
    ):
        """
        Initialize metrics manager.

        Args:
            app_name: Application name
            backend: Backend type ("prometheus" or "opentelemetry", defaults to config)
            enable_auto_update: Start background metric updates (Prometheus only)
            update_interval: Seconds between updates (Prometheus only)
            backend_config: Backend-specific configuration
        """
        self.app_name = app_name
        self.update_interval = update_interval
        self.backend_config = backend_config or {}

        # Determine backend (config > param > default)
        if backend is None:
            try:
                config = get_config()
                backend = config.get("metrics", {}).get("backend", "prometheus")
            except Exception:
                backend = "prometheus"

        self._requested_backend = backend  # Store original request
        self._actual_backend = backend  # Will be updated if fallback occurs
        self._backend = self._create_backend(backend, app_name, enable_auto_update, update_interval)

        # Expose backend-specific attributes (for backward compatibility)
        if hasattr(self._backend, "process"):
            self.process = self._backend.process
        if hasattr(self._backend, "container"):
            self.container = self._backend.container
        if hasattr(self._backend, "http"):
            self.http = self._backend.http

        logger.info(f"Metrics initialized: backend={self._actual_backend}, app={app_name}")

    def _create_backend(
        self,
        backend: str,
        app_name: str,
        enable_auto_update: bool,
        update_interval: int,
    ) -> MetricsBackend:
        """
        Create backend instance.

        Args:
            backend: Backend type
            app_name: Application name
            enable_auto_update: Enable automatic updates
            update_interval: Update interval

        Returns:
            Backend instance
        """
        if backend == "prometheus":
            from .prometheus_backend import PrometheusBackend

            self._actual_backend = "prometheus"
            return PrometheusBackend(
                app_name=app_name,
                enable_auto_update=enable_auto_update,
                update_interval=update_interval,
                config=self.backend_config,
            )
        elif backend == "opentelemetry":
            try:
                from .opentelemetry_backend import OpenTelemetryBackend

                self._actual_backend = "opentelemetry"
                return OpenTelemetryBackend(app_name=app_name, config=self.backend_config)
            except ImportError:
                logger.error("OpenTelemetry backend not available. " "Install with: pip install hs-lib[opentelemetry]")
                logger.warning("Falling back to Prometheus backend")
                from .prometheus_backend import PrometheusBackend

                self._actual_backend = "prometheus"
                return PrometheusBackend(
                    app_name=app_name,
                    enable_auto_update=enable_auto_update,
                    update_interval=update_interval,
                    config=self.backend_config,
                )
        else:
            logger.error(f"Unknown metrics backend: {backend}. Supported: prometheus, opentelemetry")
            logger.warning("Falling back to Prometheus backend")
            from .prometheus_backend import PrometheusBackend

            self._actual_backend = "prometheus"
            return PrometheusBackend(
                app_name=app_name,
                enable_auto_update=enable_auto_update,
                update_interval=update_interval,
                config=self.backend_config,
            )

    @property
    def backend_name(self) -> str:
        """Get actual backend name (after any fallbacks)."""
        return self._actual_backend

    @property
    def enabled(self) -> bool:
        """Check if metrics backend is enabled."""
        return self._backend.enabled

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Counter metric.

        Counter is for values that only increase (requests, errors, etc.).

        Args:
            name: Metric name
            description: Human-readable description
            labels: Optional label names

        Returns:
            Counter instance

        Example:
            >>> requests = metrics.counter("api_requests", "Total requests", ["method", "status"])
            >>> requests.labels(method="GET", status="200").inc()
        """
        if not self.enabled:
            return NoOpMetric()
        return self._backend.counter(name, description, labels)

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Gauge metric.

        Gauge is for values that can go up and down (queue size, etc.).

        Args:
            name: Metric name
            description: Human-readable description
            labels: Optional label names

        Returns:
            Gauge instance

        Example:
            >>> queue_size = metrics.gauge("queue_size", "Items in queue")
            >>> queue_size.set(42)
            >>> queue_size.inc()
            >>> queue_size.dec(5)
        """
        if not self.enabled:
            return NoOpMetric()
        return self._backend.gauge(name, description, labels)

    def histogram(
        self,
        name: str,
        description: str,
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Any:
        """
        Create or get a Histogram metric.

        Histogram tracks distribution of values (latency, size, etc.).

        Args:
            name: Metric name
            description: Human-readable description
            labels: Optional label names
            buckets: Optional bucket boundaries

        Returns:
            Histogram instance

        Example:
            >>> latency = metrics.histogram("request_latency", "Request latency in seconds")
            >>> latency.observe(0.123)
        """
        if not self.enabled:
            return NoOpMetric()
        return self._backend.histogram(name, description, labels, buckets)

    @property
    def metrics(self) -> bytes:
        """
        Get metrics in backend's native format (bytes for HTTP response).

        Example:
            >>> from fastapi import Response
            >>> @app.get("/metrics")
            >>> def metrics_endpoint():
            >>>     return Response(
            >>>         content=metrics.metrics,
            >>>         media_type=metrics.content_type
            >>>     )
        """
        if not self.enabled:
            return b"# Metrics not available\n"
        return self._backend.get_metrics()

    @property
    def metrics_text(self) -> str:
        """Get metrics as text string (decoded from bytes)."""
        return self.metrics.decode("utf-8")

    @property
    def content_type(self) -> str:
        """HTTP content type for metrics endpoint."""
        if not self.enabled:
            return "text/plain"
        return self._backend.get_content_type()

    # Backward compatibility - keep old method names
    def get_metrics(self) -> bytes:
        """Deprecated: Use .metrics property instead."""
        return self.metrics

    def get_metrics_text(self) -> str:
        """Deprecated: Use .metrics_text property instead."""
        return self.metrics_text

    def get_content_type(self) -> str:
        """Deprecated: Use .content_type property instead."""
        return self.content_type

    def start_auto_update(self) -> None:
        """Start background metric updates (Prometheus only)."""
        if self.enabled:
            self._backend.start_auto_update()

    def stop_auto_update(self) -> None:
        """Stop background metric updates (Prometheus only)."""
        if self.enabled:
            self._backend.stop_auto_update()

    def update(self) -> None:
        """Update metrics immediately (Prometheus only)."""
        if self.enabled:
            self._backend.update()


def create_metrics(
    app_name: str = "app",
    backend: str | None = None,
    enable_auto_update: bool = True,
    update_interval: int = 5,
    backend_config: dict[str, Any] | None = None,
) -> MetricsManager:
    """
    Create metrics manager with sensible defaults.

    Args:
        app_name: Application name
        backend: Backend type ("prometheus" or "opentelemetry", defaults to config)
        enable_auto_update: Start background updates (Prometheus only)
        update_interval: Seconds between updates (Prometheus only)
        backend_config: Backend-specific configuration

    Returns:
        MetricsManager instance

    Example:
        >>> # Default backend (Prometheus)
        >>> metrics = create_metrics("myapp")
        >>>
        >>> # OpenTelemetry backend
        >>> metrics = create_metrics("myapp", backend="opentelemetry")
        >>>
        >>> # With custom config
        >>> metrics = create_metrics(
        ...     "myapp",
        ...     backend="opentelemetry",
        ...     backend_config={"endpoint": "http://otel-collector:4318"}
        ... )
    """
    return MetricsManager(
        app_name=app_name,
        backend=backend,
        enable_auto_update=enable_auto_update,
        update_interval=update_interval,
        backend_config=backend_config,
    )
