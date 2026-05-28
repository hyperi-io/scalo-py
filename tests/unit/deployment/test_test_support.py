# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_test_support.py
# Purpose:   Unit tests for hyperi_pylib.deployment.test_support
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for ``hyperi_pylib.deployment.test_support``.

Covers tool probes (cached via ``lru_cache``), skip emission to both
stderr and the side-channel log file, tier_b env parsing, the skip
log path resolution (Linux/macOS/WSL vs native Windows), and the
``KindClusterGuard`` context manager lifecycle.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# tier_b_enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"])
def test_tier_b_enabled_truthy_values(val: str) -> None:
    from hyperi_pylib.deployment.test_support import tier_b_enabled

    with patch.dict(os.environ, {"HYPERI_E2E_CLUSTER": val}):
        assert tier_b_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "garbage"])
def test_tier_b_enabled_falsy_values(val: str) -> None:
    from hyperi_pylib.deployment.test_support import tier_b_enabled

    with patch.dict(os.environ, {"HYPERI_E2E_CLUSTER": val}):
        assert tier_b_enabled() is False


def test_tier_b_enabled_unset() -> None:
    from hyperi_pylib.deployment.test_support import tier_b_enabled

    env = {k: v for k, v in os.environ.items() if k != "HYPERI_E2E_CLUSTER"}
    with patch.dict(os.environ, env, clear=True):
        assert tier_b_enabled() is False


# ---------------------------------------------------------------------------
# Skip log path
# ---------------------------------------------------------------------------


def test_skip_log_path_linux_uses_xdg_cache(tmp_path: Path) -> None:
    from hyperi_pylib.deployment import test_support

    with patch.object(Path, "home", return_value=tmp_path), patch.object(test_support.sys, "platform", "linux"):
        p = test_support._skip_log_path()
    assert p == tmp_path / ".cache" / "hyperi-ai" / "contract-e2e-skips.log"


def test_skip_log_path_darwin_uses_home_cache(tmp_path: Path) -> None:
    from hyperi_pylib.deployment import test_support

    with patch.object(Path, "home", return_value=tmp_path), patch.object(test_support.sys, "platform", "darwin"):
        p = test_support._skip_log_path()
    assert p == tmp_path / ".cache" / "hyperi-ai" / "contract-e2e-skips.log"


def test_skip_log_path_windows_uses_localappdata(tmp_path: Path) -> None:
    from hyperi_pylib.deployment import test_support

    fake_appdata = str(tmp_path / "AppDataLocal")
    with (
        patch.dict(os.environ, {"LOCALAPPDATA": fake_appdata}, clear=False),
        patch.object(test_support.sys, "platform", "win32"),
    ):
        p = test_support._skip_log_path()
    assert p == Path(fake_appdata) / "hyperi-ai" / "Cache" / "contract-e2e-skips.log"


def test_skip_log_path_never_in_tmp() -> None:
    """AGENT-RULES Rule 4 -- /tmp is forbidden for state."""
    from hyperi_pylib.deployment.test_support import _skip_log_path

    p = _skip_log_path()
    assert not str(p).startswith("/tmp/"), f"skip log must NOT live under /tmp, got {p}"


# ---------------------------------------------------------------------------
# skip() function
# ---------------------------------------------------------------------------


def test_skip_writes_canonical_prefix_to_stderr_and_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from hyperi_pylib.deployment import test_support

    log_path = tmp_path / "skips.log"
    with patch.object(test_support, "_skip_log_path", return_value=log_path), pytest.raises(pytest.skip.Exception):
        test_support.skip("tier-a", "test_foo", "docker missing")
    captured = capsys.readouterr()
    expected = "HYPERCI-SKIP[contract-e2e][tier-a]: test_foo: docker missing"
    assert expected in captured.err
    assert log_path.exists()
    assert expected in log_path.read_text(encoding="utf-8")


def test_skip_rejects_invalid_tier(tmp_path: Path) -> None:
    from hyperi_pylib.deployment import test_support

    log_path = tmp_path / "skips.log"
    with (
        patch.object(test_support, "_skip_log_path", return_value=log_path),
        pytest.raises(ValueError, match="tier"),
    ):
        test_support.skip("tier-z", "test_x", "bad tier")


def test_skip_appends_not_truncates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from hyperi_pylib.deployment import test_support

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


def test_docker_available_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """`docker_available()` calls shutil.which at most once across invocations."""
    from hyperi_pylib.deployment import test_support

    test_support.docker_available.cache_clear()
    call_counter = {"which": 0, "run": 0}

    def fake_which(name: str) -> str | None:
        call_counter["which"] += 1
        return "/usr/bin/docker"

    def fake_run(*a, **kw) -> subprocess.CompletedProcess[str]:
        call_counter["run"] += 1
        return subprocess.CompletedProcess(args=a[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(test_support.shutil, "which", fake_which)
    monkeypatch.setattr(test_support.subprocess, "run", fake_run)

    test_support.docker_available()
    test_support.docker_available()
    test_support.docker_available()

    assert call_counter["which"] == 1
    assert call_counter["run"] == 1


def test_docker_available_false_when_no_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    from hyperi_pylib.deployment import test_support

    test_support.docker_available.cache_clear()
    monkeypatch.setattr(test_support.shutil, "which", lambda _name: None)
    assert test_support.docker_available() is False


def test_helm_available_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from hyperi_pylib.deployment import test_support

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
    from hyperi_pylib.deployment import test_support

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
    from hyperi_pylib.deployment.test_support import docker_empty_creds_json

    assert docker_empty_creds_json() == '{"auths": {}}'


# ---------------------------------------------------------------------------
# wait_until
# ---------------------------------------------------------------------------


def test_wait_until_returns_true_on_first_success() -> None:
    from hyperi_pylib.deployment.test_support import wait_until

    assert wait_until(deadline_seconds=1.0, interval_seconds=0.01, predicate=lambda: True) is True


def test_wait_until_returns_false_on_timeout() -> None:
    from hyperi_pylib.deployment.test_support import wait_until

    assert wait_until(deadline_seconds=0.05, interval_seconds=0.01, predicate=lambda: False) is False


def test_wait_until_polls_until_predicate_true() -> None:
    from hyperi_pylib.deployment.test_support import wait_until

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
    from hyperi_pylib.deployment.test_support import KindClusterGuard

    g = KindClusterGuard(test_name="test_foo")
    assert g.name.startswith("pylib-e2e-")
    assert len(g.name.removeprefix("pylib-e2e-")) == 12  # 12-char hash slice


def test_kind_cluster_guard_same_test_name_same_cluster() -> None:
    from hyperi_pylib.deployment.test_support import KindClusterGuard

    a = KindClusterGuard(test_name="test_foo")
    b = KindClusterGuard(test_name="test_foo")
    assert a.name == b.name


def test_kind_cluster_guard_different_test_name_different_cluster() -> None:
    from hyperi_pylib.deployment.test_support import KindClusterGuard

    a = KindClusterGuard(test_name="test_foo")
    b = KindClusterGuard(test_name="test_bar")
    assert a.name != b.name


def test_ensure_kind_cluster_returns_none_when_prereqs_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hyperi_pylib.deployment import test_support

    test_support.kind_available.cache_clear()
    test_support.kubectl_available.cache_clear()
    monkeypatch.setattr(test_support.shutil, "which", lambda _name: None)
    log_path = tmp_path / "skips.log"
    monkeypatch.setattr(test_support, "_skip_log_path", lambda: log_path)
    env = {k: v for k, v in os.environ.items() if k != "HYPERI_E2E_CLUSTER"}
    with patch.dict(os.environ, env, clear=True), pytest.raises(pytest.skip.Exception):
        test_support.ensure_kind_cluster("test_x")
