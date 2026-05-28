#  Project:      hyperi-pylib
#  File:         app.py
#  Purpose:      AppMetrics group -- mandatory for all DFE apps
#  Language:     Python
#
#  License:      BUSL-1.1
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
AppMetrics -- mandatory metric group for all DFE pipeline applications.

Mirrors rustlib's dfe_groups::AppMetrics. Registers standard application
identity, throughput, memory, and config reload metrics.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager


class AppMetrics:
    """
    Mandatory application metrics for DFE apps.

    Registers:
        {ns}_info gauge (labels: version, commit, app)
        {ns}_start_time_seconds gauge
        {ns}_records_received_total counter
        {ns}_records_processed_total counter
        {ns}_records_error_total counter
        {ns}_bytes_received_total counter
        {ns}_bytes_written_total counter
        {ns}_memory_used_bytes gauge
        {ns}_memory_limit_bytes gauge
        {ns}_config_reloads_total counter (labels: result)

    Where {ns} is the MetricsManager's app_name (e.g. dfe_loader).
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
