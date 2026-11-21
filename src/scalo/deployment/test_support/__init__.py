# Project:   scalo
# File:      deployment/test_support.py
# Purpose:   Reusable test probes / skip helper / kind-cluster guard for
#            consumer e2e tests of the deployment contract
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Reusable test infrastructure for the deployment-contract e2e suite.

Consumers import these helpers from their own ``tests/e2e/`` modules. The
canonical scalo-py template lives at ``tests/e2e/test_contract_artefacts.py``.

Mirrors ``scalo::deployment::test_support`` once that lands;
both implementations emit the same ``HYPERCI-SKIP[contract-e2e][...]:``
prefix so the hyperi-ci runner can aggregate skip counts uniformly.

Std-library only -- no new runtime dependencies.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Callable

import pytest

from scalo._env_compat import control_var

SKIP_PREFIX = "HYPERCI-SKIP[contract-e2e]"
"""Canonical greppable prefix for runner aggregation."""

_VALID_TIERS = frozenset({"tier-a", "tier-b"})


# ---------------------------------------------------------------------------
# Tool probes (cached: each tool shelled out at most once per process)
# ---------------------------------------------------------------------------


def _probe(args: list[str], timeout: float = 10.0) -> str | None:
    """Run ``args``. None when it exits 0, otherwise a one-line reason it did not."""
    command = " ".join(args)
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
    except subprocess.TimeoutExpired:
        return f"{command} did not finish within {timeout:g} s"
    except FileNotFoundError:
        return f"{args[0]} is not on PATH"
    except OSError as exc:
        return f"{command} could not start: {exc}"
    if result.returncode == 0:
        return None
    stderr_lines = result.stderr.strip().splitlines()
    detail = f": {stderr_lines[-1][:200]}" if stderr_lines else ""
    return f"{command} exited {result.returncode}{detail}"


def _shell_ok(args: list[str], timeout: float = 10.0) -> bool:
    return _probe(args, timeout) is None


# Where a daemon is expected: retry for _WAIT in all, never start a call with under _MIN left, which would only time out.
_DOCKER_DAEMON_ARGV = ["docker", "version", "--format", "{{.Server.Version}}"]
_DOCKER_WAIT_SECONDS = 30.0
_DOCKER_ATTEMPT_SECONDS = 20.0
_DOCKER_RETRY_PAUSE_SECONDS = 2.0
_DOCKER_LOCAL_ATTEMPT_SECONDS = 10.0
_DOCKER_MIN_ATTEMPT_SECONDS = 1.0


def _docker_is_expected() -> bool:
    """CI and the full tier run with a daemon, so a failed probe there is a stall, not an absent daemon."""
    return "CI" in os.environ or (os.environ.get("HYPERCI_TEST_TIER") or "").strip().lower() == "full"


def _next_docker_timeout(left: float, attempt_limit: float) -> float | None:
    """Timeout for the next call with ``left`` seconds of the wait remaining, None when too little is left to start one."""
    if left < _DOCKER_MIN_ATTEMPT_SECONDS:
        return None
    return min(attempt_limit, left)


@cache
def docker_unreachable_reason() -> str | None:
    """Why no docker daemon answers, or None when one does. Asked once per process.

    Where a daemon is expected, the first calls of a job can stall, so a failed call is retried for
    ``_DOCKER_WAIT_SECONDS`` in all. Elsewhere one call is enough: a stopped Docker Desktop must not
    stall every collection.

    ``docker version`` reaches the daemon without the CLI plugin scan that ``docker info`` also runs.
    """
    if shutil.which("docker") is None:
        return "docker is not on PATH"
    patient = _docker_is_expected()
    attempt_limit = _DOCKER_ATTEMPT_SECONDS if patient else _DOCKER_LOCAL_ATTEMPT_SECONDS
    deadline = time.monotonic() + (_DOCKER_WAIT_SECONDS if patient else 0.0)
    timeout = attempt_limit
    while True:
        problem = _probe(_DOCKER_DAEMON_ARGV, timeout)
        if problem is None:
            return None
        next_timeout = _next_docker_timeout(deadline - time.monotonic() - _DOCKER_RETRY_PAUSE_SECONDS, attempt_limit)
        if next_timeout is None:
            return problem
        time.sleep(_DOCKER_RETRY_PAUSE_SECONDS)
        timeout = next_timeout


def docker_available() -> bool:
    """Docker daemon reachable for build/run."""
    return docker_unreachable_reason() is None


@cache
def buildx_available() -> bool:
    """BuildKit (``docker buildx``) usable for builds."""
    if shutil.which("docker") is None:
        return False
    return _shell_ok(["docker", "buildx", "version"])


def docker_build_cmd(
    tag: str,
    *,
    dockerfile: str = "Dockerfile",
    context: str = ".",
    no_cache: bool = False,
) -> list[str]:
    """Build the ``docker build`` argv, preferring BuildKit.

    Use this rather than hand-writing ``["docker", "build", ...]``. The
    legacy builder connects to ``unix:///var/run/docker.sock`` directly
    instead of honouring the active ``docker context``, so on any setup
    where the daemon lives elsewhere -- colima, Rancher Desktop, a remote
    DOCKER_HOST -- ``docker info`` reports the daemon up while
    ``docker build`` fails with "failed to connect to the docker API".
    That combination turns a working machine into a hard test failure
    that reads like a broken image.

    ``docker buildx build`` uses the active context, and BuildKit is what
    the container standard specifies anyway. ``--load`` puts the result
    in the local image store so a following ``docker run`` can see it.
    Falls back to the legacy form when buildx is absent.
    """
    if buildx_available():
        cmd = ["docker", "buildx", "build", "--load", "-t", tag, "-f", dockerfile]
    else:
        cmd = ["docker", "build", "-t", tag, "-f", dockerfile]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(context)
    return cmd


@cache
def helm_available() -> bool:
    """Helm CLI installed and responsive."""
    if shutil.which("helm") is None:
        return False
    return _shell_ok(["helm", "version"])


@cache
def kubeconform_available() -> bool:
    """Kubeconform CLI present (lint-only, no health probe)."""
    return shutil.which("kubeconform") is not None


@cache
def kind_available() -> bool:
    """Kind CLI installed and responsive."""
    if shutil.which("kind") is None:
        return False
    return _shell_ok(["kind", "version"])


@cache
def kubectl_available() -> bool:
    """Kubectl client installed and responsive (no server required)."""
    if shutil.which("kubectl") is None:
        return False
    return _shell_ok(["kubectl", "version", "--client"])


# ---------------------------------------------------------------------------
# Tier B env gate
# ---------------------------------------------------------------------------


def tier_b_enabled() -> bool:
    """True iff ``E2E_CLUSTER`` is set to a truthy value."""
    raw = (control_var("E2E_CLUSTER") or "").lower()
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Skip emission (stderr + side-channel log) -> pytest.skip
# ---------------------------------------------------------------------------


def _skip_log_path() -> Path:
    r"""Resolve the side-channel skip log path.

    Linux/macOS/WSL/Git Bash: ``~/.cache/scalo/contract-e2e-skips.log``.
    Native Windows: ``%LOCALAPPDATA%\scalo\Cache\contract-e2e-skips.log``.

    Never ``/tmp`` (AGENT-RULES Rule 4).
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "scalo" / "Cache" / "contract-e2e-skips.log"
    return Path.home() / ".cache" / "scalo" / "contract-e2e-skips.log"


def skip(tier: str, test_name: str, reason: str) -> None:
    """Emit canonical skip line on stderr + best-effort log, then ``pytest.skip``.

    Aggregator parses stderr; log file is advisory and OSError is swallowed.
    Raises ``ValueError`` if ``tier`` is not ``tier-a`` or ``tier-b``.
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
    """Empty Docker creds JSON (write into a tempdir's ``config.json``).

    Emptying ``auths`` is the point -- it makes public base images pull
    anonymously regardless of any credential helper on the host.

    It also has to carry ``cliPluginsExtraDirs`` forward. Pointing
    ``DOCKER_CONFIG`` at a directory holding a bare ``{"auths": {}}``
    silently disables CLI-plugin discovery, because Docker looks for
    plugins under the *config* directory plus whatever that key lists.
    Lose it and ``docker buildx`` stops resolving -- the build then fails
    with "unknown flag: --load", which reads like a broken build command
    rather than a lost plugin path.
    """
    extra_dirs = _cli_plugin_dirs()
    config: dict[str, object] = {"auths": {}}
    if extra_dirs:
        config["cliPluginsExtraDirs"] = extra_dirs
    return json.dumps(config)


@cache
def docker_host() -> str | None:
    """Endpoint of the ACTIVE docker context, e.g. ``unix:///...docker.sock``.

    Returns None when it cannot be determined (then leave DOCKER_HOST unset
    and let docker use its own defaults).

    Needed because pointing ``DOCKER_CONFIG`` at a temp directory -- which
    the build tests do to force anonymous pulls -- also throws away the
    stored *current context*. Docker then falls back to ``default``
    (``unix:///var/run/docker.sock``), so on colima / Rancher Desktop / a
    remote DOCKER_HOST the build tries a socket that does not exist while
    ``docker info`` (run without the override) says the daemon is fine.
    Pinning DOCKER_HOST makes the endpoint explicit and context-independent.
    """
    if shutil.which("docker") is None:
        return None
    try:
        result = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10.0,
        )
    except FileNotFoundError, subprocess.TimeoutExpired, OSError:
        return None
    host = result.stdout.strip()
    return host if result.returncode == 0 and host else None


def docker_env(config_dir: str | Path) -> dict[str, str]:
    """Environment for docker subprocesses in tests.

    Combines the two things a build test needs and that are easy to get
    subtly wrong together:

    - ``DOCKER_CONFIG`` -> ``config_dir``, holding empty ``auths`` so public
      base images pull anonymously whatever credential helper the host has.
    - ``DOCKER_HOST`` -> the active context's endpoint, because the line
      above discards the context (see :func:`docker_host`).

    Write :func:`docker_empty_creds_json` into ``config_dir/config.json``
    first -- it keeps CLI-plugin discovery alive so ``docker buildx``
    still resolves.
    """
    env = {**os.environ, "DOCKER_CONFIG": str(config_dir)}
    host = docker_host()
    if host:
        env["DOCKER_HOST"] = host
    return env


def _cli_plugin_dirs() -> list[str]:
    """Directories holding docker CLI plugins, for ``cliPluginsExtraDirs``.

    Takes whatever the real config already declares, plus the usual
    install locations, and keeps only those that exist.
    """
    candidates: list[str] = []

    real_config = Path(os.environ.get("DOCKER_CONFIG") or Path.home() / ".docker") / "config.json"
    try:
        declared = json.loads(real_config.read_text(encoding="utf-8")).get("cliPluginsExtraDirs")
    except OSError, ValueError, AttributeError:
        declared = None
    if isinstance(declared, list):
        candidates.extend(str(d) for d in declared)

    candidates.extend(
        [
            str(Path.home() / ".docker" / "cli-plugins"),
            "/opt/homebrew/lib/docker/cli-plugins",
            "/usr/local/lib/docker/cli-plugins",
            "/usr/libexec/docker/cli-plugins",
            "/usr/lib/docker/cli-plugins",
        ]
    )

    # Empty strings are dropped explicitly: Path("").is_dir() is True (it
    # resolves to the cwd), so a malformed cliPluginsExtraDirs entry would
    # otherwise be copied through as a bogus plugin directory.
    unique = list(dict.fromkeys(d for d in candidates if d))
    return [d for d in unique if Path(d).is_dir()]


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
    pytest-xdist workers get distinct clusters. ``__enter__`` only checks
    that ``kind``, ``kubectl`` and ``E2E_CLUSTER=1`` are present and creates
    nothing: the test body runs ``kind create cluster --name <guard.name>``
    itself, so it can pass ``--image`` or ``--config``. ``__exit__`` runs
    ``kind delete cluster`` with ``check=False`` so test failures don't
    suppress cleanup.

    Use via :func:`ensure_kind_cluster`, which checks prereqs and skips
    the test cleanly if any are missing.
    """

    test_name: str
    kubeconfig: Path | None = None

    def __post_init__(self) -> None:
        digest = hashlib.sha256(self.test_name.encode("utf-8")).hexdigest()[:12]
        self.name = f"scalo-py-e2e-{digest}"

    def __enter__(self) -> KindClusterGuard:
        if not (kind_available() and kubectl_available() and tier_b_enabled()):
            raise RuntimeError("kind cluster prerequisites not met: requires kind, kubectl, and E2E_CLUSTER=1")
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

    Returns the guard (entered: it creates no cluster and does not check
    whether the name is already used) when all of
    ``kind_available()``, ``kubectl_available()`` and ``tier_b_enabled()``
    are true. Otherwise calls :func:`skip` (which raises
    ``pytest.skip.Exception``).
    """
    missing: list[str] = []
    if not tier_b_enabled():
        missing.append("E2E_CLUSTER=1")
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
    "buildx_available",
    "docker_available",
    "docker_build_cmd",
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
