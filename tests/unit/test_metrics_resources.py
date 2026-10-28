"""ResourceMetrics: the process and cgroup readings, and their export over OTLP."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scalo.metrics import create_metrics
from scalo.metrics.groups import ResourceMetrics
from scalo.metrics.groups.resources import UNLIMITED

from .test_metrics_backends import _exported_metrics, _run_export_script, otel_required


def _resources(cgroup_root: Path) -> ResourceMetrics:
    # The Prometheus backend registers nothing, so these readers run without
    # touching the process-global OTel provider or the default registry.
    return ResourceMetrics(cgroup_root=cgroup_root, mgr=create_metrics("resources-test", backend="prometheus"))


def _write(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(content, encoding="utf-8")


def test_cgroup_v2_reports_usage_limit_and_cpu_quota(tmp_path: Path):
    _write(
        files={
            "cgroup.controllers": "cpu memory\n",
            "cpu.max": "150000 100000\n",
            "memory.current": "1048576\n",
            "memory.max": "536870912\n",
        },
        root=tmp_path,
    )

    resources = _resources(cgroup_root=tmp_path)

    assert resources.container_memory_usage_bytes() == 1048576.0
    assert resources.container_memory_limit_bytes() == 536870912.0
    assert resources.container_cpu_limit_cores() == 1.5


def test_an_unlimited_cgroup_v2_reports_the_rust_sentinel_and_no_cpu_quota(tmp_path: Path):
    _write(
        files={"cgroup.controllers": "", "cpu.max": "max 100000\n", "memory.current": "4096\n", "memory.max": "max\n"},
        root=tmp_path,
    )

    resources = _resources(cgroup_root=tmp_path)

    assert resources.container_memory_limit_bytes() == UNLIMITED == float(2**64 - 1)
    assert resources.container_cpu_limit_cores() is None


def test_cgroup_v1_reads_the_controller_directories(tmp_path: Path):
    _write(
        files={
            "cpu/cpu.cfs_period_us": "100000\n",
            "cpu/cpu.cfs_quota_us": "50000\n",
            "memory/memory.limit_in_bytes": "268435456\n",
            "memory/memory.usage_in_bytes": "8192\n",
        },
        root=tmp_path,
    )

    resources = _resources(cgroup_root=tmp_path)

    assert resources.container_memory_usage_bytes() == 8192.0
    assert resources.container_memory_limit_bytes() == 268435456.0
    assert resources.container_cpu_limit_cores() == 0.5


@pytest.mark.parametrize(
    ("limit", "expected"),
    [("9223372036854771712", UNLIMITED), ("9223372036854775807", UNLIMITED), ("268435456", 268435456.0)],
)
def test_cgroup_v1_reads_a_huge_memory_limit_as_unlimited(tmp_path: Path, limit: str, expected: float):
    _write(files={"memory/memory.limit_in_bytes": f"{limit}\n"}, root=tmp_path)

    assert _resources(cgroup_root=tmp_path).container_memory_limit_bytes() == expected


def test_a_cgroup_v1_quota_of_minus_one_is_unlimited(tmp_path: Path):
    _write(files={"cpu/cpu.cfs_period_us": "100000\n", "cpu/cpu.cfs_quota_us": "-1\n"}, root=tmp_path)

    assert _resources(cgroup_root=tmp_path).container_cpu_limit_cores() is None


def test_no_cgroup_reports_no_container_readings(tmp_path: Path):
    resources = _resources(cgroup_root=tmp_path / "absent")

    assert resources.container_memory_usage_bytes() is None
    assert resources.container_memory_limit_bytes() is None
    assert resources.container_cpu_limit_cores() is None


def test_an_unparseable_cgroup_value_reports_nothing(tmp_path: Path):
    _write(files={"cgroup.controllers": "", "memory.current": "not-a-number\n"}, root=tmp_path)

    assert _resources(cgroup_root=tmp_path).container_memory_usage_bytes() is None


def test_process_readings_describe_this_process(tmp_path: Path):
    resources = _resources(cgroup_root=tmp_path)

    resources.cpu_percent()
    cpu_percent = resources.cpu_percent()
    resident = resources.resident_memory_bytes()
    virtual = resources.virtual_memory_bytes()
    assert cpu_percent is not None
    assert cpu_percent >= 0
    assert resident is not None
    assert resident > 0
    assert virtual is not None
    assert virtual >= resident
    if sys.platform == "linux":
        open_fds = resources.open_fds()
        assert open_fds is not None
        assert open_fds > 0
    else:
        assert resources.open_fds() is None


def test_cpu_seconds_is_the_cpu_time_used_and_never_falls(tmp_path: Path):
    """process_cpu_seconds_total is accumulated CPU time, as scalo-rs reports it."""
    resources = _resources(cgroup_root=tmp_path)
    before = resources.cpu_seconds()
    deadline = time.process_time() + 0.05
    while time.process_time() < deadline:
        pass
    after = resources.cpu_seconds()

    assert before is not None
    assert after is not None
    # psutil reads whole 10 ms ticks; a percent-of-a-core reading would jump by about 100.
    assert 0.03 <= after - before < 5.0, f"50 ms of busy loop moved CPU time {before} -> {after}"


def test_the_prometheus_backend_registers_nothing(tmp_path: Path):
    assert _resources(cgroup_root=tmp_path).registered is False


_RESOURCE_EXPORT_SCRIPT = """
from scalo.metrics import create_metrics
from scalo.metrics.groups import ResourceMetrics

metrics = create_metrics("resource-export", backend="opentelemetry")
ResourceMetrics(mgr=metrics)
metrics.update()
metrics.update()
"""


@otel_required
@pytest.mark.skipif(sys.platform != "linux", reason="process_open_fds is Linux only, as in scalo-rs")
def test_resource_gauges_reach_every_otlp_export():
    result, bodies = _run_export_script(script=_RESOURCE_EXPORT_SCRIPT)

    assert result.returncode == 0, result.stderr
    for name in ("process_resident_memory_bytes", "process_open_fds"):
        exported = _exported_metrics(bodies=bodies, name=name)
        assert len(exported) >= 2, f"{name} in {len(exported)} export(s): {result.stderr!r}"
        assert all(metric.WhichOneof("data") == "gauge" for metric in exported)
        assert exported[-1].gauge.data_points[0].as_double > 0


_RESOURCE_SCRAPE_SCRIPT = """
from scalo.metrics import create_metrics
from scalo.metrics.groups import ResourceMetrics

metrics = create_metrics("resource-scrape", backend="opentelemetry")
ResourceMetrics(mgr=metrics)
body = metrics.get_metrics()
print(body.decode() if isinstance(body, bytes) else body)
"""


@otel_required
def test_the_otel_backend_serves_process_cpu_once_as_a_gauge():
    # A subprocess, because ResourceMetrics unregisters prometheus_client's process collector process-wide.
    result = subprocess.run(
        [sys.executable, "-c", _RESOURCE_SCRAPE_SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "OTEL_EXPORTER_OTLP_ENDPOINT": ""},
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    declared = [line for line in result.stdout.splitlines() if line.startswith("# TYPE process_cpu_seconds_total ")]
    assert declared == ["# TYPE process_cpu_seconds_total gauge"], result.stdout
