"""
Base abstractions for metrics backends.

This module provides abstract base classes for metrics backends,
enabling backend-agnostic instrumentation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class MetricsBackend(ABC):
    """
    Abstract base for metrics backends (Prometheus, OpenTelemetry, etc.).

    Provides unified API for creating and managing metrics regardless
    of underlying implementation.
    """

    def __init__(self, app_name: str, config: dict[str, Any] | None = None):
        """
        Initialize metrics backend.

        Args:
            app_name: Application name for metric labels
            config: Backend-specific configuration
        """
        self.app_name = app_name
        self.config = config or {}
        self.enabled = True

    @abstractmethod
    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Counter metric.

        Counter is for values that only increase (requests, errors, etc.).

        Args:
            name: Metric name
            description: Human-readable description
            labels: Optional label names

        Returns:
            Counter instance (backend-specific)
        """
        pass

    @abstractmethod
    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Gauge metric.

        Gauge is for values that can go up and down (queue size, etc.).

        Args:
            name: Metric name
            description: Human-readable description
            labels: Optional label names

        Returns:
            Gauge instance (backend-specific)
        """
        pass

    @abstractmethod
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
            Histogram instance (backend-specific)
        """
        pass

    @abstractmethod
    def get_metrics(self) -> bytes:
        """
        Get metrics in backend's native format.

        Returns:
            Metrics as bytes (ready for HTTP response)
        """
        pass

    @abstractmethod
    def get_content_type(self) -> str:
        """
        Get HTTP content type for metrics endpoint.

        Returns:
            Content-Type string
        """
        pass

    @abstractmethod
    def start_auto_update(self) -> None:
        """Start background metric collection (if applicable)."""
        pass

    @abstractmethod
    def stop_auto_update(self) -> None:
        """Stop background metric collection (if applicable)."""
        pass

    @abstractmethod
    def update(self) -> None:
        """Update metrics immediately (if applicable)."""
        pass


class NoOpMetric:
    """No-op metric for when backend is disabled or unavailable."""

    def inc(self, *args, **kwargs):
        """No-op increment."""
        pass

    def dec(self, *args, **kwargs):
        """No-op decrement."""
        pass

    def set(self, *args, **kwargs):
        """No-op set."""
        pass

    def observe(self, *args, **kwargs):
        """No-op observe."""
        pass

    def info(self, *args, **kwargs):
        """No-op info."""
        pass

    def labels(self, *args, **kwargs):
        """No-op labels."""
        return self

    def time(self, *args, **kwargs):
        """No-op timer context manager."""
        return self

    def __enter__(self):
        """No-op context manager entry."""
        return self

    def __exit__(self, *args):
        """No-op context manager exit."""
        pass
