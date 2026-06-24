#  Project:      scalo
#  File:         app.py
#  Purpose:      AppMetrics group -- mandatory for all services
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
AppMetrics -- mandatory metric group for all pipeline applications.

Mirrors scalo-rs's groups::AppMetrics. Registers standard application
identity, throughput, memory, and config reload metrics.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager


class AppMetrics:
    """
    Mandatory application metrics for any service.

    Registers (shown with the optional platform prefix ``{p}_``):
        {p}_info gauge (labels: version, commit, app)
        {p}_start_time_seconds gauge
        {p}_records_received_total counter
        {p}_records_processed_total counter
        {p}_records_error_total counter
        {p}_bytes_received_total counter
        {p}_bytes_written_total counter
        {p}_memory_used_bytes gauge
        {p}_memory_limit_bytes gauge
        {p}_config_reloads_total counter (labels: result)

    ``{p}`` is the MetricsManager's ``metric_prefix`` -- bare ("") by default,
    so names are unprefixed unless an app calls ``set_metric_prefix("myapp")``
    (-> ``myapp_info`` ...). App identity is also carried in the ``app`` label.
    """

    def __init__(self, mgr: MetricsManager, version: str, commit: str) -> None:
        """
        Register all mandatory app metrics.

        Args:
            mgr: MetricsManager instance providing the namespace prefix
            version: Application version string
            commit: Git commit hash
        """
        app_name = mgr.app_name

        # Identity
        self._info: Any = mgr.gauge("info", "Service identity and version", labels=["version", "commit", "app"])
        self._info.labels(version=version, commit=commit, app=app_name).set(1)

        self._start_time: Any = mgr.gauge("start_time_seconds", "Unix timestamp of process start")
        self._start_time.set(time.time())

        # Throughput counters
        self._records_received: Any = mgr.counter("records_received_total", "Records received from source")
        self._records_processed: Any = mgr.counter("records_processed_total", "Records successfully processed")
        self._records_error: Any = mgr.counter("records_error_total", "Records that failed processing")

        # Byte counters
        self._bytes_received: Any = mgr.counter("bytes_received_total", "Bytes received from source")
        self._bytes_written: Any = mgr.counter("bytes_written_total", "Bytes written to sink")

        # Memory gauges
        self._memory_used: Any = mgr.gauge("memory_used_bytes", "Current memory usage (cgroup-aware)")
        self._memory_limit: Any = mgr.gauge("memory_limit_bytes", "Effective memory limit")

        # Config reload counter
        self._config_reloads: Any = mgr.counter("config_reloads_total", "Hot-reload attempts", labels=["result"])

    def record_received(self, count: int = 1) -> None:
        """Increment records received counter."""
        self._records_received.inc(count)

    def record_processed(self, count: int = 1) -> None:
        """Increment records processed counter."""
        self._records_processed.inc(count)

    def record_error(self, count: int = 1) -> None:
        """Increment records error counter."""
        self._records_error.inc(count)

    def record_bytes_received(self, nbytes: int) -> None:
        """Increment bytes received counter."""
        self._bytes_received.inc(nbytes)

    def record_bytes_written(self, nbytes: int) -> None:
        """Increment bytes written counter."""
        self._bytes_written.inc(nbytes)

    def set_memory(self, used: int, limit: int) -> None:
        """Set current memory usage and limit gauges."""
        self._memory_used.set(used)
        self._memory_limit.set(limit)

    def record_config_reload(self, result: str) -> None:
        """
        Increment config reload counter with result label.

        Args:
            result: "success" or "error"
        """
        self._config_reloads.labels(result=result).inc()
