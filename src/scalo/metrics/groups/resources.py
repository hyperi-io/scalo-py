#  Project:      scalo
#  File:         resources.py
#  Purpose:      ResourceMetrics group -- process and container resource gauges
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
ResourceMetrics -- process and container resource gauges.

Mirrors scalo-rs's process and container collectors: the same bare names, each
read fresh at every collection. Container gauges come from the cgroup (v2, else
v1) and are left out where there is none, as scalo-rs leaves them out.
"""

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..manager import MetricsManager

CGROUP_ROOT = Path("/sys/fs/cgroup")

# scalo-rs reports an unlimited cgroup ("max") as u64::MAX.
UNLIMITED = float(2**64 - 1)


def _read_number(path: Path) -> float | None:
    """A cgroup value file as a number: "max" is UNLIMITED, anything unreadable is None."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if raw == "max":
        return UNLIMITED
    try:
        return float(raw)
    except ValueError:
        return None


def _psutil_process() -> Any:
    """This process under psutil, or None when psutil is not installed."""
    try:
        import psutil
    except ImportError:
        return None
    return psutil.Process()


def _drop_prometheus_process_collector() -> None:
    """Unregister prometheus_client's default process collector from its registry.

    The OpenTelemetry backend serves /metrics from that registry, which would
    otherwise carry each process_* name twice.
    """
    try:
        from prometheus_client import PROCESS_COLLECTOR, REGISTRY
    except ImportError:
        return
    try:
        REGISTRY.unregister(PROCESS_COLLECTOR)
    except KeyError:
        return


class ResourceMetrics:
    """
    Process and container resource gauges, read at every collection.

    Registers (under the manager's optional ``metric_prefix``):
        process_cpu_seconds_total gauge -- CPU use as a percent of one core since the
            previous collection, the meaning released scalo-rs gives this name
        process_resident_memory_bytes gauge
        process_virtual_memory_bytes gauge
        process_open_fds gauge (Linux only)
        process_start_time_seconds gauge
        container_memory_usage_bytes gauge (cgroup only)
        container_memory_limit_bytes gauge (cgroup only; unlimited is 2**64 - 1)
        container_cpu_limit_cores gauge (cgroup CPU quota only)

    Only a backend with per-collection reads (OpenTelemetry) registers them; on
    Prometheus, prometheus_client's own process collector covers the process_* set.

    Args:
        cgroup_root: Where the cgroup filesystem is mounted.
        mgr: MetricsManager to register with.
    """

    def __init__(self, *, cgroup_root: Path = CGROUP_ROOT, mgr: MetricsManager) -> None:
        self._cgroup_root = cgroup_root
        self._cgroup_v2 = (cgroup_root / "cgroup.controllers").exists()
        self._start_time = time.time()
        self._process = _psutil_process()

        readings: dict[str, tuple[str, Callable[[], float | None]]] = {
            "process_cpu_seconds_total": ("CPU use in percent of one core since the last read", self.cpu_percent),
            "process_resident_memory_bytes": ("Resident memory size in bytes", self.resident_memory_bytes),
            "process_virtual_memory_bytes": ("Virtual memory size in bytes", self.virtual_memory_bytes),
            "process_open_fds": ("Open file descriptors", self.open_fds),
            "process_start_time_seconds": ("Unix time the collector started", self.start_time),
            "container_memory_usage_bytes": ("Container memory in use in bytes", self.container_memory_usage_bytes),
            "container_memory_limit_bytes": ("Container memory limit in bytes", self.container_memory_limit_bytes),
            "container_cpu_limit_cores": ("Container CPU quota in cores", self.container_cpu_limit_cores),
        }
        self.registered = False
        for name, (description, callback) in readings.items():
            if mgr.observable_gauge(callback=callback, description=description, name=name):
                self.registered = True
        if self.registered:
            _drop_prometheus_process_collector()

    def cpu_percent(self) -> float | None:
        """CPU use in percent of one core since the previous read (100 per busy core), or None without psutil."""
        if self._process is None:
            return None
        return float(self._process.cpu_percent(interval=None))

    def resident_memory_bytes(self) -> float | None:
        """Resident set size, or None without psutil."""
        memory = self._memory_info()
        return None if memory is None else float(memory.rss)

    def virtual_memory_bytes(self) -> float | None:
        """Virtual memory size, or None without psutil."""
        memory = self._memory_info()
        return None if memory is None else float(memory.vms)

    def open_fds(self) -> float | None:
        """Entries in /proc/self/fd, or None off Linux."""
        try:
            return float(len(os.listdir("/proc/self/fd")))
        except OSError:
            return None

    def start_time(self) -> float | None:
        """Unix time this collector was built, as scalo-rs reports it."""
        return self._start_time

    def container_memory_usage_bytes(self) -> float | None:
        """Memory the cgroup is using, or None outside one."""
        name = "memory.current" if self._cgroup_v2 else "memory/memory.usage_in_bytes"
        return _read_number(self._cgroup_root / name)

    def container_memory_limit_bytes(self) -> float | None:
        """The cgroup's memory limit, UNLIMITED when there is none, or None outside a cgroup."""
        name = "memory.max" if self._cgroup_v2 else "memory/memory.limit_in_bytes"
        return _read_number(self._cgroup_root / name)

    def container_cpu_limit_cores(self) -> float | None:
        """The cgroup's CPU quota in cores, or None when unlimited or outside a cgroup."""
        if self._cgroup_v2:
            try:
                quota, period = (self._cgroup_root / "cpu.max").read_text(encoding="utf-8").split()
            except (OSError, ValueError):
                return None
            if quota == "max":
                return None
            return float(quota) / float(period)
        quota_us = _read_number(self._cgroup_root / "cpu/cpu.cfs_quota_us")
        period_us = _read_number(self._cgroup_root / "cpu/cpu.cfs_period_us")
        if (quota_us is None) or (period_us is None) or (quota_us <= 0) or (period_us <= 0):
            return None
        return quota_us / period_us

    def _memory_info(self) -> Any:
        if self._process is None:
            return None
        return self._process.memory_info()
