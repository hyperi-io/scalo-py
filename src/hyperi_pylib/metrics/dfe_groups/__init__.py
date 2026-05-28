#  Project:      hyperi-pylib
#  File:         __init__.py
#  Purpose:      DFE metric groups -- composable metric structs matching rustlib
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
DFE metric groups -- composable metric structs for DFE pipeline applications.

Each group is a class that takes a MetricsManager in its constructor,
creates prefixed metrics, and exposes convenience record/set methods.
Apps compose the groups they need.

Example:
    >>> from hyperi_pylib.metrics import create_metrics
    >>> from hyperi_pylib.metrics.dfe_groups import AppMetrics, BufferMetrics
    >>>
    >>> mgr = create_metrics("dfe_loader")
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
from .sink import SinkMetrics

__all__ = [
    "AppMetrics",
    "BackpressureMetrics",
    "BufferMetrics",
    "CircuitBreakerMetrics",
    "ConsumerMetrics",
    "SinkMetrics",
]
