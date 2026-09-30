"""ResourceMetrics: the process and cgroup readings, and their export over OTLP."""

import sys
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
    assert resources.cpu_percent() >= 0
    assert resources.resident_memory_bytes() > 0
    assert resources.virtual_memory_bytes() >= resources.resident_memory_bytes()
    if sys.platform == "linux":
        assert resources.open_fds() > 0
    else:
        assert resources.open_fds() is None


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
