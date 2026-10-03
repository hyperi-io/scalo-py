"""
scalo Metrics Module - Backend-Agnostic Metrics Instrumentation.

Provides unified API for metrics collection with pluggable backends:
- OpenTelemetry (default) - dual export: OTLP push + Prometheus scrape
- Prometheus - standalone Prometheus scrape

Quick Start:
    >>> from scalo.metrics import create_metrics
    >>>
    >>> # Default backend (OpenTelemetry with dual export)
    >>> metrics = create_metrics("myapp")
    >>>
    >>> # Or explicit Prometheus-only
    >>> metrics = create_metrics("myapp", backend="prometheus")
    >>>
    >>> # Same API regardless of backend
    >>> metrics.counter("requests", "Total requests").inc()
    >>> metrics.gauge("queue_size", "Queue depth").set(42)
    >>> metrics.histogram("latency", "Request latency").observe(0.123)

Configuration (settings.yaml):
    metrics:
      backend: opentelemetry  # or "prometheus"
      opentelemetry:
        endpoint: http://otel-collector:4317
        protocol: grpc
        prometheus_scrape: true  # also expose /metrics (default)
"""

# Configurable metric-name prefix (bare by default, mirrors the env prefix)
from .._env_compat import metric_prefix, set_metric_prefix

# Primary API (backend-agnostic)
from .cardinality import CardinalityTracker

# Metric groups (composable structs matching scalo-rs)
from .groups import (
    AppMetrics,
    BackpressureMetrics,
    BufferMetrics,
    CircuitBreakerMetrics,
    ConsumerMetrics,
    SinkMetrics,
)
from .manager import MetricsManager, create_metrics
from .naming import validate_metric_name, validate_metric_prefix

# Backward compatibility: Re-export Prometheus-specific classes
from .prometheus import (
    ContainerMetrics,
    HTTPMetrics,
    ProcessMetrics,
    PrometheusMetrics,
)

__all__ = [
    # Metric groups
    "AppMetrics",
    "BackpressureMetrics",
    "BufferMetrics",
    "CardinalityTracker",
    "CircuitBreakerMetrics",
    "ConsumerMetrics",
    "ContainerMetrics",
    "HTTPMetrics",
    "MetricsManager",
    "ProcessMetrics",
    # Backward compatibility
    "PrometheusMetrics",
    "SinkMetrics",
    # Primary API
    "create_metrics",
    # Configurable metric prefix
    "metric_prefix",
    "set_metric_prefix",
    # Naming validation
    "validate_metric_name",
    "validate_metric_prefix",
]
