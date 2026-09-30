#  Project:      scalo
#  File:         __init__.py
#  Purpose:      Metric groups -- composable metric structs matching scalo-rs
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Metric groups -- composable metric structs for pipeline applications.

Each group is a class that takes a MetricsManager in its constructor,
registers its standard metrics (under the manager's optional ``metric_prefix``,
bare by default), and exposes convenience record/set methods. Apps compose the
groups they need.

Example:
    >>> from scalo.metrics import create_metrics
    >>> from scalo.metrics.groups import AppMetrics, BufferMetrics
    >>>
    >>> mgr = create_metrics("loader")  # or create_metrics("loader", metric_prefix="myapp")
    >>> app = AppMetrics(mgr, version="1.0.0", commit="abc123")
    >>> buf = BufferMetrics(mgr)
    >>>
    >>> app.record_received(100)
    >>> buf.record_flush(duration_seconds=0.01, trigger="size")
"""

from .app import AppMetrics
from .backpressure import BackpressureMetrics
from .buffer import BufferMetrics
from .circuit_breaker import CircuitBreakerMetrics
from .consumer import ConsumerMetrics
from .resources import ResourceMetrics
from .sink import SinkMetrics

__all__ = [
    "AppMetrics",
    "BackpressureMetrics",
    "BufferMetrics",
    "CircuitBreakerMetrics",
    "ConsumerMetrics",
    "ResourceMetrics",
    "SinkMetrics",
]
