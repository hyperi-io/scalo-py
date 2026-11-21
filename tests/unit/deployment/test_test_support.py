# Project:   scalo
# File:      tests/unit/deployment/test_test_support.py
# Purpose:   Unit tests for scalo.deployment.test_support
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for ``scalo.deployment.test_support``.

Covers tool probes (cached via ``lru_cache``), skip emission to both
stderr and the side-channel log file, tier_b env parsing, the skip
log path resolution (Linux/macOS/WSL vs native Windows), and the
``KindClusterGuard`` context manager lifecycle.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# tier_b_enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"])
def test_tier_b_enabled_truthy_values(val: str) -> None:
    from scalo.deployment.test_support import tier_b_enabled

    with patch.dict(os.environ, {"E2E_CLUSTER": val}):
        assert tier_b_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "garbage"])
def test_tier_b_enabled_falsy_values(val: str) -> None:
    from scalo.deployment.test_support import tier_b_enabled

    with patch.dict(os.environ, {"E2E_CLUSTER": val}):
        assert tier_b_enabled() is False


def test_tier_b_enabled_unset() -> None:
    from scalo.deployment.test_support import tier_b_enabled

    env = {k: v for k, v in os.environ.items() if k != "E2E_CLUSTER"}
    with patch.dict(os.environ, env, clear=True):
        assert tier_b_enabled() is False


# ---------------------------------------------------------------------------
# Skip log path
# ---------------------------------------------------------------------------


def test_skip_log_path_linux_uses_xdg_cache(tmp_path: Path) -> None:
    from scalo.deployment import test_support

    with patch.object(Path, "home", return_value=tmp_path), patch.object(test_support.sys, "platform", "linux"):
        p = test_support._skip_log_path()
    assert p == tmp_path / ".cache" / "scalo" / "contract-e2e-skips.log"


def test_skip_log_path_darwin_uses_home_cache(tmp_path: Path) -> None:
    from scalo.deployment import test_support

    with patch.object(Path, "home", return_value=tmp_path), patch.object(test_support.sys, "platform", "darwin"):
        p = test_support._skip_log_path()
    assert p == tmp_path / ".cache" / "scalo" / "contract-e2e-skips.log"


def test_skip_log_path_windows_uses_localappdata(tmp_path: Path) -> None:
    from scalo.deployment import test_support

    fake_appdata = str(tmp_path / "AppDataLocal")
    with (
        patch.dict(os.environ, {"LOCALAPPDATA": fake_appdata}, clear=False),
        patch.object(test_support.sys, "platform", "win32"),
    ):
        p = test_support._skip_log_path()
    assert p == Path(fake_appdata) / "scalo" / "Cache" / "contract-e2e-skips.log"


def test_skip_log_path_never_in_tmp() -> None:
    """AGENT-RULES Rule 4 -- /tmp is forbidden for state."""
    from scalo.deployment.test_support import _skip_log_path

    p = _skip_log_path()
    assert not str(p).startswith("/tmp/"), f"skip log must NOT live under /tmp, got {p}"


# ---------------------------------------------------------------------------
# skip() function
# ---------------------------------------------------------------------------


def test_skip_writes_canonical_prefix_to_stderr_and_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scalo.deployment import test_support

    log_path = tmp_path / "skips.log"
    with patch.object(test_support, "_skip_log_path", return_value=log_path), pytest.raises(pytest.skip.Exception):
        test_support.skip("tier-a", "test_foo", "docker missing")
    captured = capsys.readouterr()
    expected = "HYPERCI-SKIP[contract-e2e][tier-a]: test_foo: docker missing"
    assert expected in captured.err
    assert log_path.exists()
    assert expected in log_path.read_text(encoding="utf-8")


def test_skip_rejects_invalid_tier(tmp_path: Path) -> None:
    from scalo.deployment import test_support

    log_path = tmp_path / "skips.log"
    with (
        patch.object(test_support, "_skip_log_path", return_value=log_path),
        pytest.raises(ValueError, match="tier"),
    ):
        test_support.skip("tier-z", "test_x", "bad tier")


def test_skip_appends_not_truncates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scalo.deployment import test_support

    log_path = tmp_path / "skips.log"
    with patch.object(test_support, "_skip_log_path", return_value=log_path):
        for i in range(3):
            with pytest.raises(pytest.skip.Exception):
                test_support.skip("tier-a", f"test_{i}", f"reason_{i}")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# Probes (cached)
# ---------------------------------------------------------------------------


_FAKE_DOCKER = """#!/bin/sh
dir="$(dirname "$0")"
n=$(cat "$dir/calls" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$dir/calls"
action=$(sed -n "${n}p" "$dir/plan")
[ -n "$action" ] || action=$(tail -n 1 "$dir/plan")
case "$action" in
  ok) echo "29.4.2" ;;
  refuse) echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock" >&2; exit 1 ;;
  hang) exec sleep 30 ;;
esac
"""


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[list[str]], Path]]:
    """Put a real executable called ``docker`` first on PATH, in a CI run, with the waits shrunk to fractions of a second.

    Call it with the plan: what the n-th call does (``ok``, ``refuse`` or ``hang``), the last line repeating.
    It returns the file that counts the calls.
    """
    from scalo.deployment import test_support

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "docker"
    script.write_text(_FAKE_DOCKER, encoding="utf-8", newline="\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("CI", "1")
    monkeypatch.delenv("HYPERCI_TEST_TIER", raising=False)
    monkeypatch.setattr(test_support, "_DOCKER_WAIT_SECONDS", 2.0)
    monkeypatch.setattr(test_support, "_DOCKER_ATTEMPT_SECONDS", 0.3)
    monkeypatch.setattr(test_support, "_DOCKER_LOCAL_ATTEMPT_SECONDS", 0.3)
    monkeypatch.setattr(test_support, "_DOCKER_RETRY_PAUSE_SECONDS", 0.05)
    monkeypatch.setattr(test_support, "_DOCKER_MIN_ATTEMPT_SECONDS", 0.1)
    test_support.docker_unreachable_reason.cache_clear()

    def install(plan: list[str]) -> Path:
        (bin_dir / "plan").write_text("\n".join(plan) + "\n", encoding="utf-8", newline="\n")
        return bin_dir / "calls"

    yield install
    test_support.docker_unreachable_reason.cache_clear()


def _calls(counter: Path) -> int:
    return int(counter.read_text(encoding="utf-8"))


_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in docker is a POSIX shell script")


@_POSIX_ONLY
@pytest.mark.parametrize(
    ("plan", "reachable", "min_calls"),
    [
        pytest.param(["ok"], True, 1, id="answers-at-once"),
        pytest.param(["refuse", "refuse", "ok"], True, 3, id="daemon-still-starting"),
        pytest.param(["hang", "ok"], True, 2, id="first-call-stalls-past-the-attempt-timeout"),
        pytest.param(["refuse"], False, 2, id="no-daemon"),
        pytest.param(["hang"], False, 2, id="wedged-daemon"),
    ],
)
def test_docker_probe_waits_out_a_daemon_that_is_slow_or_starting_in_ci(
    fake_docker: Callable[[list[str]], Path], plan: list[str], reachable: bool, min_calls: int
) -> None:
    from scalo.deployment import test_support

    calls = fake_docker(plan)

    assert test_support.docker_available() is reachable
    reason = test_support.docker_unreachable_reason()
    assert (reason is None) is reachable
    assert reason is None or reason.startswith("docker version --format")
    assert _calls(calls) >= min_calls


@_POSIX_ONLY
def test_docker_probe_is_as_patient_under_the_full_tier_without_ci(
    fake_docker: Callable[[list[str]], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scalo.deployment import test_support

    monkeypatch.delenv("CI")
    monkeypatch.setenv("HYPERCI_TEST_TIER", "full")
    calls = fake_docker(["refuse", "refuse", "ok"])

    assert test_support.docker_available() is True
    assert _calls(calls) == 3


@_POSIX_ONLY
@pytest.mark.parametrize(
    ("plan", "reason_part"),
    [
        pytest.param(["refuse", "ok"], "exited 1: Cannot connect", id="refused"),
        pytest.param(["hang", "ok"], "did not finish within 0.3 s", id="stalled"),
    ],
)
def test_docker_probe_asks_once_where_no_daemon_is_expected(
    fake_docker: Callable[[list[str]], Path], monkeypatch: pytest.MonkeyPatch, plan: list[str], reason_part: str
) -> None:
    """A stopped Docker Desktop must not stall every collection, so a developer's run takes the first answer."""
    from scalo.deployment import test_support

    monkeypatch.delenv("CI")
    calls = fake_docker(plan)

    assert test_support.docker_available() is False
    reason = test_support.docker_unreachable_reason()
    assert reason is not None
    assert reason_part in reason
    assert _calls(calls) == 1


@pytest.mark.parametrize(
    ("left", "expected"),
    [
        pytest.param(30.0, 20.0, id="plenty-left-takes-the-full-limit"),
        pytest.param(8.0, 8.0, id="less-than-the-limit-caps-the-call"),
        pytest.param(1.0, 1.0, id="exactly-the-floor-still-starts"),
        pytest.param(0.99, None, id="under-the-floor-stops"),
        pytest.param(-3.0, None, id="past-the-deadline-stops"),
    ],
)
def test_docker_probe_caps_each_call_at_the_time_left(left: float, expected: float | None) -> None:
    from scalo.deployment import test_support

    assert test_support._next_docker_timeout(left, 20.0) == expected


@_POSIX_ONLY
def test_docker_probe_asks_the_daemon_once_per_process(fake_docker: Callable[[list[str]], Path]) -> None:
    from scalo.deployment import test_support

    calls = fake_docker(["ok"])

    assert [test_support.docker_available() for _ in range(3)] == [True, True, True]
    assert _calls(calls) == 1


@_POSIX_ONLY
def test_docker_probe_asks_again_after_cache_clear(
    fake_docker: Callable[[list[str]], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scalo.deployment import test_support

    monkeypatch.delenv("CI")
    fake_docker(["refuse"])
    assert test_support.docker_available() is False

    calls = fake_docker(["ok"])
    test_support.docker_unreachable_reason.cache_clear()

    assert test_support.docker_available() is True
    assert test_support.docker_unreachable_reason() is None
    assert _calls(calls) > 1


def test_docker_probe_says_when_docker_is_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scalo.deployment import test_support

    monkeypatch.setenv("PATH", str(tmp_path))
    test_support.docker_unreachable_reason.cache_clear()
    try:
        assert test_support.docker_available() is False
        assert test_support.docker_unreachable_reason() == "docker is not on PATH"
    finally:
        test_support.docker_unreachable_reason.cache_clear()


def test_helm_available_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from scalo.deployment import test_support

    test_support.helm_available.cache_clear()
    monkeypatch.setattr(test_support.shutil, "which", lambda _name: "/usr/bin/helm")
    monkeypatch.setattr(
        test_support.subprocess,
        "run",
        lambda *a, **_kw: subprocess.CompletedProcess(args=a[0], returncode=0, stdout="", stderr=""),
    )
    assert test_support.helm_available() is True


def test_kubeconform_available_no_health_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """kubeconform is a CLI lint -- only check binary presence, no version call."""
    from scalo.deployment import test_support

    test_support.kubeconform_available.cache_clear()
    monkeypatch.setattr(test_support.shutil, "which", lambda _name: "/usr/bin/kubeconform")
    # subprocess.run should NOT be called for kubeconform; sentinel to detect violations:
    monkeypatch.setattr(
        test_support.subprocess,
        "run",
        lambda *_a, **_kw: pytest.fail("kubeconform_available should not call subprocess.run"),
    )
    assert test_support.kubeconform_available() is True


# ---------------------------------------------------------------------------
# docker_empty_creds_json
# ---------------------------------------------------------------------------


def test_docker_empty_creds_json_format() -> None:
    import json

    from scalo.deployment.test_support import docker_empty_creds_json

    parsed = json.loads(docker_empty_creds_json())
    # Empty auths is the point: public base images pull anonymously
    # regardless of any credential helper on the host.
    assert parsed["auths"] == {}
    # Plugin dirs must survive, or pointing DOCKER_CONFIG at a temp dir
    # hides `docker buildx` and builds fail with "unknown flag: --load".
    extra = parsed.get("cliPluginsExtraDirs")
    assert extra is None or isinstance(extra, list)


# ---------------------------------------------------------------------------
# wait_until
# ---------------------------------------------------------------------------


def test_wait_until_returns_true_on_first_success() -> None:
    from scalo.deployment.test_support import wait_until

    assert wait_until(deadline_seconds=1.0, interval_seconds=0.01, predicate=lambda: True) is True


def test_wait_until_returns_false_on_timeout() -> None:
    from scalo.deployment.test_support import wait_until

    assert wait_until(deadline_seconds=0.05, interval_seconds=0.01, predicate=lambda: False) is False


def test_wait_until_polls_until_predicate_true() -> None:
    from scalo.deployment.test_support import wait_until

    counter = {"calls": 0}

    def predicate() -> bool:
        counter["calls"] += 1
        return counter["calls"] >= 3

    assert wait_until(deadline_seconds=1.0, interval_seconds=0.01, predicate=predicate) is True
    assert counter["calls"] == 3


# ---------------------------------------------------------------------------
# KindClusterGuard
# ---------------------------------------------------------------------------


def test_kind_cluster_guard_name_is_hashed_from_test_name() -> None:
    from scalo.deployment.test_support import KindClusterGuard

    g = KindClusterGuard(test_name="test_foo")
    assert g.name.startswith("scalo-py-e2e-")
    assert len(g.name.removeprefix("scalo-py-e2e-")) == 12  # 12-char hash slice


def test_kind_cluster_guard_same_test_name_same_cluster() -> None:
    from scalo.deployment.test_support import KindClusterGuard

    a = KindClusterGuard(test_name="test_foo")
    b = KindClusterGuard(test_name="test_foo")
    assert a.name == b.name


def test_kind_cluster_guard_different_test_name_different_cluster() -> None:
    from scalo.deployment.test_support import KindClusterGuard

    a = KindClusterGuard(test_name="test_foo")
    b = KindClusterGuard(test_name="test_bar")
    assert a.name != b.name


def test_ensure_kind_cluster_returns_none_when_prereqs_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scalo.deployment import test_support

    test_support.kind_available.cache_clear()
    test_support.kubectl_available.cache_clear()
    monkeypatch.setattr(test_support.shutil, "which", lambda _name: None)
    log_path = tmp_path / "skips.log"
    monkeypatch.setattr(test_support, "_skip_log_path", lambda: log_path)
    env = {k: v for k, v in os.environ.items() if k != "E2E_CLUSTER"}
    with patch.dict(os.environ, env, clear=True), pytest.raises(pytest.skip.Exception):
        test_support.ensure_kind_cluster("test_x")
