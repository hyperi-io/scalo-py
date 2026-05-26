# Project:   hyperi-pylib
# File:      deployment/test_support.py
# Purpose:   Reusable test probes / skip helper / kind-cluster guard for
#            consumer e2e tests of the deployment contract
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Reusable test infrastructure for the deployment-contract e2e suite.

Consumers import these helpers from their own ``tests/e2e/`` modules. The
canonical pylib template lives at ``tests/e2e/test_contract_artefacts.py``.

Mirrors ``hyperi_rustlib::deployment::test_support`` once that lands;
both implementations emit the same ``HYPERCI-SKIP[contract-e2e][...]:``
prefix so the hyperi-ci runner can aggregate skip counts uniformly.

Std-library only -- no new runtime dependencies.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Callable

import pytest

SKIP_PREFIX = "HYPERCI-SKIP[contract-e2e]"
"""Canonical greppable prefix for runner aggregation."""

_VALID_TIERS = frozenset({"tier-a", "tier-b"})


# ---------------------------------------------------------------------------
# Tool probes (cached: each tool shelled out at most once per process)
# ---------------------------------------------------------------------------


def _shell_ok(args: list[str], timeout: float = 10.0) -> bool:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


@cache
def docker_available() -> bool:
    """Docker daemon reachable for build/run."""
    if shutil.which("docker") is None:
        return False
    return _shell_ok(["docker", "info"])


@cache
def helm_available() -> bool:
    """Helm CLI installed and responsive."""
    if shutil.which("helm") is None:
        return False
    return _shell_ok(["helm", "version"])


@cache
def kubeconform_available() -> bool:
    """kubeconform CLI present (lint-only, no health probe)."""
    return shutil.which("kubeconform") is not None


@cache
def kind_available() -> bool:
    """kind CLI installed and responsive."""
    if shutil.which("kind") is None:
        return False
    return _shell_ok(["kind", "version"])


@cache
def kubectl_available() -> bool:
    """kubectl client installed and responsive (no server required)."""
    if shutil.which("kubectl") is None:
        return False
    return _shell_ok(["kubectl", "version", "--client"])


# ---------------------------------------------------------------------------
# Tier B env gate
# ---------------------------------------------------------------------------


def tier_b_enabled() -> bool:
    """True iff ``HYPERI_E2E_CLUSTER`` is set to a truthy value."""
    raw = os.environ.get("HYPERI_E2E_CLUSTER", "").lower()
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Skip emission (stderr + side-channel log) -> pytest.skip
# ---------------------------------------------------------------------------


def _skip_log_path() -> Path:
    """Resolve the side-channel skip log path.

    Linux/macOS/WSL/Git Bash: ``~/.cache/hyperi-ai/contract-e2e-skips.log``.
    Native Windows: ``%LOCALAPPDATA%\\hyperi-ai\\Cache\\contract-e2e-skips.log``.

    Never ``/tmp`` (AGENT-RULES Rule 4).
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "hyperi-ai" / "Cache" / "contract-e2e-skips.log"
    return Path.home() / ".cache" / "hyperi-ai" / "contract-e2e-skips.log"


def skip(tier: str, test_name: str, reason: str) -> None:
    """Emit a canonical skip line and call :func:`pytest.skip`.

    Writes ``HYPERCI-SKIP[contract-e2e][<tier>]: <test_name>: <reason>``
    to ``sys.stderr`` AND best-effort appends it to the side-channel
    log file at :func:`_skip_log_path`. Then raises
    ``pytest.skip.Exception`` via :func:`pytest.skip`, so callers
    don't need an extra ``return``.

    The side-channel log write is best-effort: any OSError (read-only
    filesystem, permission denied, missing parent we can't create) is
    swallowed and the skip still proceeds. The runner-aggregator scan
    relies on the stderr line, not the log file, so the log being
    unwritable degrades gracefully.

    Raises:
        ValueError: if ``tier`` is not ``tier-a`` or ``tier-b``.
    """
    if tier not in _VALID_TIERS:
        raise ValueError(f"tier must be one of {sorted(_VALID_TIERS)}; got {tier!r}")
    line = f"{SKIP_PREFIX}[{tier}]: {test_name}: {reason}"
    print(line, file=sys.stderr, flush=True)
    try:
        log_path = _skip_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError:
        # Read-only filesystem, missing perms, etc. Skip still proceeds.
        pass
    pytest.skip(reason)


# ---------------------------------------------------------------------------
# docker_empty_creds_json -- bypass credential helpers in CI
# ---------------------------------------------------------------------------


def docker_empty_creds_json() -> str:
    """Empty Docker creds JSON (write into a tempdir's ``config.json``)."""
    return '{"auths": {}}'


# ---------------------------------------------------------------------------
# wait_until -- generic poll helper
# ---------------------------------------------------------------------------


def wait_until(
    deadline_seconds: float,
    interval_seconds: float,
    predicate: Callable[[], bool],
) -> bool:
    """Poll ``predicate`` until True or deadline elapses."""
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return predicate()


# ---------------------------------------------------------------------------
# KindClusterGuard -- per-test kind cluster lifecycle
# ---------------------------------------------------------------------------


@dataclass
class KindClusterGuard:
    """Context manager wrapping a uniquely-named kind cluster.

    Cluster name is derived from a hash of ``test_name`` so parallel
    pytest-xdist workers get distinct clusters. ``__enter__`` brings the
    cluster up via ``kind create cluster``; ``__exit__`` runs
    ``kind delete cluster`` with ``check=False`` so test failures don't
    suppress cleanup.

    Use via :func:`ensure_kind_cluster`, which checks prereqs and skips
    the test cleanly if any are missing.
    """

    test_name: str
    kubeconfig: Path | None = None

    def __post_init__(self) -> None:
        digest = hashlib.sha256(self.test_name.encode("utf-8")).hexdigest()[:12]
        self.name = f"pylib-e2e-{digest}"

    def __enter__(self) -> KindClusterGuard:
        if not (kind_available() and kubectl_available() and tier_b_enabled()):
            raise RuntimeError("kind cluster prerequisites not met: requires kind, kubectl, and HYPERI_E2E_CLUSTER=1")
        # Cluster brought up by caller via subprocess; this class only
        # tracks the lifecycle. Test bodies invoke `kind create cluster`
        # with self.name so they can pass --image / --config flags.
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if shutil.which("kind") is None:
            return
        subprocess.run(
            ["kind", "delete", "cluster", "--name", self.name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )


def ensure_kind_cluster(test_name: str) -> KindClusterGuard | None:
    """Return a :class:`KindClusterGuard` or skip the test with a clear reason.

    Returns the guard (entered) when all of ``kind_available()``,
    ``kubectl_available()``, ``tier_b_enabled()`` are true. Otherwise
    calls :func:`skip` (which raises ``pytest.skip.Exception``).
    """
    missing: list[str] = []
    if not tier_b_enabled():
        missing.append("HYPERI_E2E_CLUSTER=1")
    if not kind_available():
        missing.append("kind")
    if not kubectl_available():
        missing.append("kubectl")
    if missing:
        skip("tier-b", test_name, f"tier-b prereqs missing: {', '.join(missing)}")
        return None  # unreachable; skip() raises
    guard = KindClusterGuard(test_name=test_name)
    return guard.__enter__()


__all__ = [
    "SKIP_PREFIX",
    "KindClusterGuard",
    "docker_available",
    "docker_empty_creds_json",
    "ensure_kind_cluster",
    "helm_available",
    "kind_available",
    "kubeconform_available",
    "kubectl_available",
    "skip",
    "tier_b_enabled",
    "wait_until",
]
