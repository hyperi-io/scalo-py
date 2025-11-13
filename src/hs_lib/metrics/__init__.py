"""
HyperLib Metrics Module - Backend-Agnostic Metrics Instrumentation.

Provides unified API for metrics collection with pluggable backends:
- Prometheus (default)
- OpenTelemetry (optional)

Quick Start:
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

Configuration (settings.yaml):
    metrics:
      backend: prometheus  # or "opentelemetry"
      namespace: myapp
"""

# Primary API (backend-agnostic)
from .manager import MetricsManager, create_metrics

# Backward compatibility: Re-export Prometheus-specific classes
from .prometheus import (
    ContainerMetrics,
    HTTPMetrics,
    ProcessMetrics,
    PrometheusMetrics,
)

__all__ = [
    # Primary API
    "create_metrics",
    "MetricsManager",
    # Backward compatibility
    "PrometheusMetrics",
    "ProcessMetrics",
    "ContainerMetrics",
    "HTTPMetrics",
]
