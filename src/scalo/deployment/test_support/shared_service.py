#  Project:   scalo
#  File:      src/scalo/deployment/test_support/shared_service.py
#  Purpose:   One container per backing service per test run, owned by one process
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""One container per backing service per test run, shared by every test process.

The run's controller calls :func:`begin_run` before any worker starts, which
sets ``HYPERI_TEST_RUN_ID`` and ``HYPERI_TEST_RUN_OWNER`` for every process the
run spawns. :func:`acquire` then gives each process the same container: the
first to ask creates it under a run-scoped name while holding a lock file in
the run directory, and writes where it is to a state file beside the lock.
Every later process reads that file and joins. The owner removes the run's
containers with :func:`release_run`, and a detached watcher started with each
container removes it if the owner exits first. Nothing here names a repo,
image or port: the caller passes a :class:`Suite` and a :class:`ServiceSpec`.

Ports publish on the daemon host's loopback, never a wildcard. A daemon
reached over ssh gets an ``ssh -L`` tunnel per port, on the same port number
at both ends, so an address a service advertises resolves here too. A remote
``tcp://`` daemon needs ``HYPERI_TEST_DOCKER_BIND``.

Every container carries the ``io.hyperi.test.*`` labels of :func:`labels`. A
create first sweeps the suite's containers whose owner has gone
(:func:`sweep_removes`): on the owner's host and PID namespace once the owner
process has exited, anywhere else once its lease has lapsed.

The pet rung lives here too: :func:`lookup` reads ``HYPERI_TEST_*`` settings
from the process environment, then the project ``.env``, then the file named
by ``HYPERI_TEST_ENV_FILE``, and :func:`pets_allowed` says when a run may use
them.

POSIX only: process identity comes from ``/proc`` or ``ps``, and the lock from
``fcntl``.

Example::

    suite = Suite(repo="my-app", project_dir=root, run_dir=shared_dir, log_dir=root / ".tmp")
    spec = ServiceSpec(
        service="redis",
        image="redis:8.2.2@sha256:<digest>",
        startup_timeout=60,
        ports=(6379,),
        ready=LogReady("Ready to accept connections"),
    )
    redis = acquire(suite, spec)
    address = redis.addr(6379)
"""

import fcntl
import http.client
import json
import os
import re
import secrets
import socket
import string
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import dotenv_values

LEASE_SECONDS = 4 * 3600
"""How long a container stays another host's after its owner labels it: past
the longest full run, so a sweep from elsewhere never takes a live one."""

RUN_ID_ENV = "HYPERI_TEST_RUN_ID"
RUN_OWNER_ENV = "HYPERI_TEST_RUN_OWNER"
LABEL = "io.hyperi.test"

_POLL_SECONDS = 0.25
# A first pull of a database image can take minutes, and comes before the startup deadline.
_CREATE_TIMEOUT_SECONDS = 600.0
_DOCKER_TIMEOUT_SECONDS = 120.0
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
_WILDCARD = frozenset({"0.0.0.0", "::", "[::]", "*"})
_SECRET_ALPHABET = string.ascii_letters + string.digits
_SECRET_LENGTH = 24
_LOG_TAIL_LINES = 40


class SharedServiceError(RuntimeError):
    """A shared container could not be started, joined or reached. The message says why."""


# ---------------------------------------------------------------------------
# Run identity and the HYPERI_TEST_* lookup
# ---------------------------------------------------------------------------


def begin_run() -> None:
    """Name a new run and make this process its owner, for every process it spawns.

    Call it in the run's controller before any worker starts. A worker inherits
    both variables and must not call it.
    """
    os.environ[RUN_ID_ENV] = secrets.token_hex(4)
    os.environ[RUN_OWNER_ENV] = str(os.getpid())


def run_id() -> str:
    """Short id of this test run: :data:`RUN_ID_ENV`, else this process as ``p<pid>``."""
    cleaned = "".join(c for c in os.environ.get(RUN_ID_ENV, "") if c.isascii() and c.isalnum())
    return cleaned[:8] or f"p{os.getpid()}"


def run_owner_pid() -> int:
    """The process whose exit ends the run: :data:`RUN_OWNER_ENV`, else this process."""
    raw = os.environ.get(RUN_OWNER_ENV, "")
    return int(raw) if raw.isdigit() else os.getpid()


def _file_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    return dotenv_values(path).get(key)


def suite_tier() -> str:
    """The test tier hyperi-ci exports as ``HYPERCI_TEST_TIER``, ``core`` when unset."""
    return (os.environ.get("HYPERCI_TEST_TIER") or "core").strip().lower()


def pets_allowed() -> bool:
    """Whether this run may use a pet: never in CI, never under the full tier."""
    return "CI" not in os.environ and suite_tier() != "full"


# ---------------------------------------------------------------------------
# Suite and spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Suite:
    """The repo whose suite starts the containers.

    Attributes:
        repo: Repo name, for container names, labels and the run log.
        project_dir: Directory holding the project ``.env`` that :func:`lookup` reads.
        run_dir: A directory every process of one run shares, for the lock and state files.
        log_dir: Where the run log goes.
    """

    repo: str
    project_dir: Path
    run_dir: Path
    log_dir: Path

    def label(self) -> str:
        """Value of the ``io.hyperi.test.suite`` label: ``<repo>-integration``."""
        return f"{self.repo}-integration"

    def prefix(self) -> str:
        """Container name prefix: ``HYPERI_TEST_CONTAINER_PREFIX``, else ``<repo>-test``."""
        return lookup(self, "HYPERI_TEST_CONTAINER_PREFIX") or f"{self.repo}-test"

    def log_path(self) -> Path:
        """The run log every creator and watcher appends to."""
        return self.log_dir / f"shared-services-{run_id()}.log"

    def record(self, line: str) -> None:
        """Write ``line`` to stderr and to the run log."""
        print(f"shared-service: {line}", file=sys.stderr, flush=True)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with self.log_path().open("a", encoding="utf-8", newline="\n") as log:
                log.write(line + "\n")
        except OSError:
            pass  # the stderr line still carries it


def lookup(suite: Suite, key: str) -> str | None:
    """A ``HYPERI_TEST_*`` setting: the environment, the project ``.env``, then ``HYPERI_TEST_ENV_FILE``.

    Empty counts as unset. ``HYPERI_TEST_ENV_FILE`` itself is read from the
    environment, then the project ``.env``.
    """
    project_env = suite.project_dir / ".env"
    value = os.environ.get(key) or _file_value(project_env, key)
    if not value:
        user_file = os.environ.get("HYPERI_TEST_ENV_FILE") or _file_value(project_env, "HYPERI_TEST_ENV_FILE")
        if user_file:
            value = _file_value(Path(user_file).expanduser(), key)
    return value or None


@dataclass(frozen=True, slots=True)
class HttpReady:
    """``GET path`` on container ``port`` answers 200 with ``body``, compared trimmed."""

    port: int
    path: str
    body: str


@dataclass(frozen=True, slots=True)
class LogReady:
    """The container log carries ``line``."""

    line: str


@dataclass(frozen=True, slots=True)
class ExecReady:
    """``argv`` run inside the container prints ``stdout``, compared trimmed."""

    argv: tuple[str, ...]
    stdout: str


type Ready = HttpReady | LogReady | ExecReady


@dataclass(frozen=True, slots=True)
class SharedContainer:
    """A running container and where its ports are reachable from this machine.

    Attributes:
        name: Container name.
        host: Host the ports are reachable on.
        ports: Container port to host port.
        secret: The password or token the container was started with, empty when none.
    """

    name: str
    host: str
    ports: Mapping[int, int]
    secret: str = field(default="", repr=False)

    def port(self, container_port: int) -> int:
        """Host port that ``container_port`` is published on.

        Raises:
            SharedServiceError: The spec did not publish ``container_port``.
        """
        try:
            return self.ports[container_port]
        except KeyError:
            raise SharedServiceError(f"{self.name} does not publish port {container_port}") from None

    def addr(self, container_port: int) -> str:
        """``host:port`` for ``container_port``."""
        return f"{self.host}:{self.port(container_port)}"

    def exec(self, *argv: str) -> str:
        """Run a command inside the container and return its stdout.

        Raises:
            SharedServiceError: The command exits non-zero.
        """
        out = docker("exec", self.name, *argv)
        if out.returncode != 0:
            raise SharedServiceError(f"{argv[0]} in {self.name}: {out.stderr.strip()}")
        return out.stdout

    def read_file(self, path: str) -> str:
        """Text of a file inside the container."""
        return self.exec("cat", path)


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    """One backing service a suite starts.

    Attributes:
        service: Service name, in the container name and the service label.
        image: Image reference, pinned by tag and digest.
        startup_timeout: Seconds for start and readiness together, after the create.
        ready: The readiness signal.
        ports: Container ports to publish, each on a free host port.
        pinned_ports: ``(container, host)`` pairs to publish on a given host port instead.
        env: Environment for the container.
        secret_env: Variables that get the run's generated password, passed to
            ``docker`` through its environment so the value is never on a command line.
        entrypoint: Entrypoint override, when the image's own cannot be used.
        args: Arguments after the image.
        files: ``(path, bytes)`` pairs copied in before start, built from the
            endpoint host. A path ending in ``/`` creates that directory first.
        after_start: Runs once the ports are known, before the readiness wait.
    """

    service: str
    image: str
    startup_timeout: float
    ready: Ready
    ports: tuple[int, ...] = ()
    pinned_ports: tuple[tuple[int, int], ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    secret_env: tuple[str, ...] = ()
    entrypoint: str | None = None
    args: tuple[str, ...] = ()
    files: Callable[[str], Sequence[tuple[str, bytes]]] | None = None
    after_start: Callable[[SharedContainer], None] | None = None

    def all_ports(self) -> tuple[int, ...]:
        """Every container port the spec publishes."""
        return self.ports + tuple(container for container, _ in self.pinned_ports)


# ---------------------------------------------------------------------------
# The docker daemon
# ---------------------------------------------------------------------------


def docker(
    *args: str, env: Mapping[str, str] | None = None, timeout: float = _DOCKER_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    """Run the docker CLI and return what it printed.

    Raises:
        SharedServiceError: ``docker`` is not on PATH, or did not finish within ``timeout``.
    """
    try:
        return subprocess.run(
            ["docker", *args],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(env) if env is not None else None,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SharedServiceError("the docker CLI is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise SharedServiceError(f"docker {args[0]} did not finish within {timeout:.0f} s") from exc


@dataclass(frozen=True, slots=True)
class LocalDaemon:
    """A local socket, or ``tcp://`` on loopback."""


@dataclass(frozen=True, slots=True)
class SshDaemon:
    """A daemon over ssh: ports bind to its loopback and arrive here through a tunnel."""

    target: str
    port: int | None = None


@dataclass(frozen=True, slots=True)
class TcpDaemon:
    """``tcp://`` to another host."""

    host: str


type Daemon = LocalDaemon | SshDaemon | TcpDaemon


def _split_host_port(host_port: str) -> tuple[str, int | None]:
    if host_port.startswith("["):
        host, _, rest = host_port.partition("]")
        port_text = rest.removeprefix(":")
        return f"{host}]", int(port_text) if port_text.isdigit() else None
    host, colon, port_text = host_port.rpartition(":")
    if not colon:
        return host_port, None
    return host, int(port_text) if port_text.isdigit() else None


def parse_daemon(endpoint: str) -> Daemon:
    """The daemon a Docker endpoint URL names."""
    scheme, sep, rest = endpoint.partition("://")
    if not sep:
        return LocalDaemon()
    authority = rest.split("/", 1)[0]
    user, at, host_port = authority.rpartition("@")
    if not at:
        user, host_port = "", authority
    host, port = _split_host_port(host_port)
    if scheme == "ssh":
        return SshDaemon(target=f"{user}@{host}" if user else host, port=port)
    if scheme in ("tcp", "http", "https") and host not in _LOOPBACK:
        return TcpDaemon(host=host)
    return LocalDaemon()


def current_daemon() -> Daemon:
    """The daemon ``DOCKER_HOST`` names, else the current docker context's."""
    endpoint = os.environ.get("DOCKER_HOST", "")
    if not endpoint:
        out = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}")
        endpoint = out.stdout.strip()
    return parse_daemon(endpoint)


def binding(daemon: Daemon, suite: Suite) -> tuple[str, str]:
    """The address ports bind to on the daemon host, and the host clients here connect to.

    Raises:
        SharedServiceError: A remote ``tcp://`` daemon without ``HYPERI_TEST_DOCKER_BIND``,
            or with a wildcard there: the services carry test credentials.
    """
    if not isinstance(daemon, TcpDaemon):
        return "127.0.0.1", "127.0.0.1"
    bind = lookup(suite, "HYPERI_TEST_DOCKER_BIND")
    if bind is None:
        raise SharedServiceError(
            f"Docker at tcp://{daemon.host} would publish the test services to its network. "
            "Set HYPERI_TEST_DOCKER_BIND to a private address on that host, or reach the daemon over ssh."
        )
    if bind in _WILDCARD:
        raise SharedServiceError(f"HYPERI_TEST_DOCKER_BIND must name one address, not {bind}")
    return bind, bind


# ---------------------------------------------------------------------------
# Owners, labels and the stale sweep
# ---------------------------------------------------------------------------


def host_id() -> str:
    """Hostname and machine id, so two machines with one hostname still differ."""
    try:
        machine = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
    except OSError:
        machine = ""
    return f"{socket.gethostname()}/{machine}"


def _pid_namespace() -> str:
    try:
        return os.readlink("/proc/self/ns/pid")
    except OSError:
        return "none"


def process_start(pid: int) -> str | None:
    """Start time of ``pid``, ``/proc/<pid>/stat`` field 22, or None when no such process exists."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        if Path("/proc/self").exists():
            return None
    else:
        # Field 22 counts from the pid, and the command name before it is
        # parenthesised and may hold spaces.
        fields = stat.rpartition(")")[2].split()
        return fields[19] if len(fields) > 19 else None
    out = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return out.stdout.strip() or None


def labels(suite: Suite, service: str, owner_pid: int) -> dict[str, str]:
    """Labels on every container: suite, repo, service, run, owner and lease."""
    return {
        f"{LABEL}.suite": suite.label(),
        f"{LABEL}.repo": suite.repo,
        f"{LABEL}.service": service,
        f"{LABEL}.run": run_id(),
        f"{LABEL}.owner-host": host_id(),
        f"{LABEL}.owner-pidns": _pid_namespace(),
        f"{LABEL}.owner-pid": str(owner_pid),
        f"{LABEL}.owner-start": process_start(owner_pid) or "",
        f"{LABEL}.lease-until": str(int(time.time()) + LEASE_SECONDS),
    }


@dataclass(frozen=True, slots=True)
class Labelled:
    """The owner labels a container carries, as read back for a sweep."""

    name: str
    host: str = ""
    pid_ns: str = ""
    pid: int | None = None
    start: str = ""
    lease_until: int | None = None


def sweep_removes(
    container: Labelled, here_host: str, here_pid_ns: str, now: int, start_of: Callable[[int], str | None]
) -> bool:
    """Whether a sweep from ``here_host`` and ``here_pid_ns`` at ``now`` removes ``container``.

    On the owner's own host and PID namespace it goes once the owner process is
    gone or its start time no longer matches. Anywhere else the owner cannot be
    seen, so it goes only once its lease has lapsed. A container with no owner
    labels is never taken.
    """
    if container.host == here_host and container.pid_ns == here_pid_ns:
        if container.pid is None:
            return False
        start = start_of(container.pid)
        return start is None or start != container.start
    return container.lease_until is not None and now > container.lease_until


def _int_or_none(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def parse_listing(listing: str) -> list[Labelled]:
    """The tab-separated listing :func:`reap_dead_owners` asks Docker for."""
    found = []
    for line in listing.splitlines():
        fields = [*line.split("\t"), "", "", "", "", ""]
        if not fields[0]:
            continue
        found.append(
            Labelled(
                name=fields[0],
                host=fields[1].strip(),
                pid_ns=fields[2].strip(),
                pid=_int_or_none(fields[3].strip()),
                start=fields[4].strip(),
                lease_until=_int_or_none(fields[5].strip()),
            )
        )
    return found


def reap_dead_owners(suite: Suite) -> None:
    """Remove this suite's containers whose owner has gone, by :func:`sweep_removes`."""
    columns = ("owner-host", "owner-pidns", "owner-pid", "owner-start", "lease-until")
    template = "\t".join(["{{.Names}}", *(f'{{{{.Label "{LABEL}.{c}"}}}}' for c in columns)])
    out = docker("ps", "--all", "--filter", f"label={LABEL}.suite={suite.label()}", "--format", template)
    here_host, here_ns, now = host_id(), _pid_namespace(), int(time.time())
    for container in parse_listing(out.stdout):
        if sweep_removes(container, here_host, here_ns, now, process_start):
            docker("rm", "--force", "--volumes", container.name)
            suite.record(f"swept {container.name}: its owner has gone")


_WATCHER = r"""(
while kill -0 "$1" 2>/dev/null; do sleep 1; done
if [ -n "$4" ]; then kill "$4" 2>/dev/null; fi
if [ -n "$2" ] && docker rm --force --volumes "$2" >/dev/null 2>&1; then
  printf '%s removed %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$2" >> "$3"
fi
) </dev/null >/dev/null 2>&1 &"""


def spawn_watcher(suite: Suite, owner: int, container: str | None = None, process: int | None = None) -> None:
    """Start a detached process that, once ``owner`` exits, removes ``container`` and ends ``process``.

    The shell backgrounds the watcher and exits, so the watcher is reparented
    rather than left for this process to reap, and it runs in a session of its
    own so a Ctrl-C to the run does not reach it.

    Raises:
        SharedServiceError: ``sh`` cannot be run, or the watcher did not start.
    """
    suite.log_dir.mkdir(parents=True, exist_ok=True)
    argv = ["sh", "-c", _WATCHER, "shared-service-watcher", str(owner), container or "", str(suite.log_path())]
    argv.append(str(process) if process is not None else "")
    try:
        started = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            timeout=_DOCKER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SharedServiceError(f"start the shared-container watcher: {exc}") from exc
    if started.returncode != 0:
        raise SharedServiceError(f"the shared-container watcher did not start: exit {started.returncode}")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# Starting a container
# ---------------------------------------------------------------------------


def _state(name: str) -> str:
    """``running``, another Docker status, or ``absent``."""
    out = docker("inspect", "--format", "{{.State.Status}}", name)
    if out.returncode == 0:
        return out.stdout.strip()
    lower = out.stderr.lower()
    if "no such object" in lower or "no such container" in lower:
        return "absent"
    raise SharedServiceError(f"Docker is needed for the shared test containers: {out.stderr.strip()}")


def generate_secret() -> str:
    """A random 24-character alphanumeric password, about 143 bits."""
    return "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(_SECRET_LENGTH))


def _create(suite: Suite, spec: ServiceSpec, name: str, daemon: Daemon, owner: int, secret: str) -> bool:
    """Create the container. False when a container already holds ``name``."""
    reap_dead_owners(suite)
    bind, _ = binding(daemon, suite)
    args = ["create", "--name", name]
    for key, value in labels(suite, spec.service, owner).items():
        args += ["--label", f"{key}={value}"]
    for port in spec.ports:
        args += ["--publish", f"{bind}::{port}"]
    for port, host_port in spec.pinned_ports:
        args += ["--publish", f"{bind}:{host_port}:{port}"]
    for key, value in spec.env.items():
        args += ["--env", f"{key}={value}"]
    # A bare --env NAME takes the value from the docker CLI's own environment.
    for key in spec.secret_env:
        args += ["--env", key]
    if spec.entrypoint:
        args += ["--entrypoint", spec.entrypoint]
    args += [spec.image, *spec.args]
    env = {**os.environ, **dict.fromkeys(spec.secret_env, secret)} if spec.secret_env else None
    out = docker(*args, env=env, timeout=_CREATE_TIMEOUT_SECONDS)
    if out.returncode == 0:
        return True
    if "already in use" in out.stderr or "Conflict" in out.stderr:
        return False
    raise SharedServiceError(f"docker create {name}: {out.stderr.strip()}")


def _stage_files(spec: ServiceSpec, name: str, host: str) -> None:
    if spec.files is None:
        return
    with tempfile.TemporaryDirectory(prefix="shared-service-") as staging:
        for index, (target, content) in enumerate(spec.files(host)):
            staged = Path(staging) / str(index)
            if target.endswith("/"):
                staged.mkdir(mode=0o755)
                staged.chmod(0o755)
            else:
                staged.write_bytes(content)
                staged.chmod(0o644)
            copied = docker("cp", str(staged), f"{name}:{target.rstrip('/')}")
            if copied.returncode != 0:
                raise SharedServiceError(f"copy {target} into {name}: {copied.stderr.strip()}")


def _published(name: str, host: str, ports: Sequence[int], deadline: float) -> SharedContainer:
    """The published host ports, waiting for Docker to report every one."""
    mapped: dict[int, int] = {}
    for port in ports:
        while True:
            out = docker("port", name, f"{port}/tcp")
            found = [line.rpartition(":")[2].strip() for line in out.stdout.splitlines()]
            host_port = next((int(p) for p in found if p.isdigit()), None)
            if host_port is not None:
                mapped[port] = host_port
                break
            if time.monotonic() >= deadline:
                raise SharedServiceError(f"{name} never published port {port}")
            time.sleep(_POLL_SECONDS)
    return SharedContainer(name=name, host=host, ports=mapped)


def bound_addresses(name: str) -> list[str]:
    """The addresses each published port of container ``name`` is bound to on the daemon host."""
    out = docker("port", name)
    found = []
    for line in out.stdout.splitlines():
        _, arrow, bound = line.partition(" -> ")
        if arrow:
            found.append(bound.rpartition(":")[0])
    return found


def _open_tunnel(daemon: SshDaemon, container: SharedContainer) -> int:
    """Forward each published port to the daemon host's loopback on the same number, and return the ssh pid.

    ``ControlPath=none`` gives the tunnel a connection of its own: a forward
    added to a shared master outlives the process that asked for it.
    """
    args = ["-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ControlPath=none"]
    if daemon.port is not None:
        args += ["-p", str(daemon.port)]
    for host_port in container.ports.values():
        args += ["-L", f"127.0.0.1:{host_port}:127.0.0.1:{host_port}"]
    args.append(daemon.target)
    out = subprocess.run(
        ["sh", "-c", 'ssh "$@" </dev/null >/dev/null 2>&1 & echo $!', "shared-service-tunnel", *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pid = out.stdout.strip()
    if not pid.isdigit():
        raise SharedServiceError(f"no pid for the ssh tunnel to {daemon.target}")
    return int(pid)


def _http_ok(host: str, port: int, path: str, body: str) -> bool:
    connection = http.client.HTTPConnection(host, port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status == 200 and response.read().decode("utf-8", "replace").strip() == body
    except OSError, http.client.HTTPException:
        return False
    finally:
        connection.close()


def _log_tail(container: SharedContainer) -> str:
    logs = docker("logs", "--tail", str(_LOG_TAIL_LINES), container.name)
    text = logs.stdout + logs.stderr
    return text.replace(container.secret, "[redacted]") if container.secret else text


def _wait_ready(container: SharedContainer, ready: Ready, deadline: float) -> None:
    while True:
        match ready:
            case HttpReady(port=port, path=path, body=body):
                up = _http_ok(container.host, container.port(port), path, body)
            case LogReady(line=line):
                logs = docker("logs", container.name)
                up = line in logs.stdout or line in logs.stderr
            case ExecReady(argv=argv, stdout=expected):
                ran = docker("exec", container.name, *argv)
                up = ran.returncode == 0 and ran.stdout.strip() == expected
        if up:
            return
        if time.monotonic() >= deadline:
            raise SharedServiceError(
                f"{container.name} not ready by its deadline. Last log lines:\n{_log_tail(container)}"
            )
        time.sleep(_POLL_SECONDS)


def _wait_reachable(container: SharedContainer, deadline: float, tunnel: int | None) -> None:
    """Wait until every published port accepts a connection here, which through a tunnel can lag readiness."""
    for port in container.ports.values():
        while True:
            try:
                socket.create_connection((container.host, port), timeout=1).close()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise SharedServiceError(
                        f"{container.name} port {port} is not reachable at {container.host}: "
                        "a tunnel that did not open, or a local port already in use"
                    ) from None
                time.sleep(_POLL_SECONDS)
    if tunnel is not None and not _pid_alive(tunnel):
        raise SharedServiceError(
            f"the ssh tunnel for {container.name} exited: a local port it forwards is already in use"
        )


def _start_owned(
    suite: Suite, spec: ServiceSpec, name: str, daemon: Daemon, host: str, owner: int, secret: str
) -> tuple[SharedContainer, int | None]:
    """Copy the files in, start the container, open its tunnel and hand both to a watcher that ends them when ``owner`` exits."""
    spawn_watcher(suite, owner, container=name)
    deadline = time.monotonic() + spec.startup_timeout
    _stage_files(spec, name, host)
    started = docker("start", name)
    if started.returncode != 0:
        raise SharedServiceError(f"start {name}: {started.stderr.strip()}")
    container = replace(_published(name, host, spec.all_ports(), deadline), secret=secret)
    tunnel = None
    if isinstance(daemon, SshDaemon):
        tunnel = _open_tunnel(daemon, container)
        spawn_watcher(suite, owner, process=tunnel)
    if spec.after_start is not None:
        spec.after_start(container)
    _wait_ready(container, spec.ready, deadline)
    _wait_reachable(container, deadline, tunnel)
    return container, tunnel


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on ``path`` across the run's processes, waiting for it."""
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _write_state(path: Path, container: SharedContainer, tunnel: int | None) -> None:
    """Record the container for the run's other processes, atomically and readable by this user only."""
    state = {
        "name": container.name,
        "host": container.host,
        "ports": {str(c): h for c, h in container.ports.items()},
        "secret": container.secret,
        "tunnel": {"pid": tunnel, "start": process_start(tunnel)} if tunnel is not None else None,
    }
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
        json.dump(state, out)
    os.replace(tmp, path)


def _read_state(path: Path) -> SharedContainer:
    state = json.loads(path.read_text(encoding="utf-8"))
    ports = {int(c): int(h) for c, h in state["ports"].items()}
    return SharedContainer(name=state["name"], host=state["host"], ports=ports, secret=state["secret"])


def shared_name(suite: Suite, service: str) -> str:
    """Name of the run's container for ``service``: ``<prefix>-integration-<service>-r<run>``."""
    return f"{suite.prefix()}-integration-{_slug(service)}-r{run_id()}"


def acquire(suite: Suite, spec: ServiceSpec) -> SharedContainer:
    """The run's container for ``spec``, created if no process of the run has yet.

    Raises:
        SharedServiceError: Docker is unreachable, the container cannot be
            created, or it is not ready within ``spec.startup_timeout``.
    """
    name = shared_name(suite, spec.service)
    daemon = current_daemon()
    _, host = binding(daemon, suite)
    suite.run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path = suite.run_dir / f"{spec.service}.json"
    with locked(suite.run_dir / f"{spec.service}.lock"):
        if state_path.exists():
            status = _state(name)
            if status != "running":
                raise SharedServiceError(f"the run's {spec.service} container {name} is {status}")
            return _read_state(state_path)
        if _state(name) != "absent":
            docker("rm", "--force", "--volumes", name)
        owner = run_owner_pid()
        secret = generate_secret() if spec.secret_env else ""
        if not _create(suite, spec, name, daemon, owner, secret):
            raise SharedServiceError(f"{name} reappeared while this process held the run's lock")
        container, tunnel = _start_owned(suite, spec, name, daemon, host, owner, secret)
        _write_state(state_path, container, tunnel)
        suite.record(
            f"started {spec.service} container {name} for run {run_id()} (owner pid {owner}): "
            f"1 {spec.service} container this run"
        )
        return container


def release_run(suite: Suite) -> list[str]:
    """Remove the run's containers and end their tunnels. Called once, by the run's owner.

    Returns:
        The names of the containers removed.
    """
    for state_path in suite.run_dir.glob("*.json"):
        tunnel = json.loads(state_path.read_text(encoding="utf-8")).get("tunnel")
        # A matching start time keeps a reused pid from being taken for the tunnel.
        if tunnel and tunnel["start"] and process_start(tunnel["pid"]) == tunnel["start"]:
            try:
                os.kill(tunnel["pid"], 15)
            except ProcessLookupError:
                pass
    filters = ["--filter", f"label={LABEL}.suite={suite.label()}", "--filter", f"label={LABEL}.run={run_id()}"]
    names = docker("ps", "--all", *filters, "--format", "{{.Names}}").stdout.split()
    for name in names:
        docker("rm", "--force", "--volumes", name)
        suite.record(f"removed {name} at the end of run {run_id()}")
    return names


# ---------------------------------------------------------------------------
# A container one test holds alone
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "-", text.lower())


def container_name(suite: Suite, test: str | None, service: str) -> str:
    """Name for a container one test starts for itself: ``<prefix>-integration-<test>-<service>-p<pid>``.

    Without ``test`` it is one started once for a whole process. Lowercase, with
    every character Docker refuses collapsed to ``-``. The pid keeps two runs of
    one test on one daemon from asking for the same name.
    """
    pid = os.getpid()
    middle = f"{_slug(test)}-{_slug(service)}" if test else _slug(service)
    return f"{suite.prefix()}-integration-{middle}-p{pid}"


@dataclass(slots=True)
class OwnedContainer:
    """A container one test holds alone, removed with its tunnel on :meth:`close`."""

    container: SharedContainer
    tunnel: int | None

    def close(self) -> None:
        """Remove the container and end its tunnel."""
        docker("rm", "--force", "--volumes", self.container.name)
        if self.tunnel is not None and _pid_alive(self.tunnel):
            os.kill(self.tunnel, 15)

    def __enter__(self) -> OwnedContainer:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def start_alone(suite: Suite, spec: ServiceSpec, name: str) -> OwnedContainer:
    """A container named ``name`` that this process holds alone. Name it with :func:`container_name`.

    Raises:
        SharedServiceError: As :func:`acquire`, and when ``name`` is already taken.
    """
    daemon = current_daemon()
    _, host = binding(daemon, suite)
    owner = os.getpid()
    secret = generate_secret() if spec.secret_env else ""
    if not _create(suite, spec, name, daemon, owner, secret):
        raise SharedServiceError(f"{name} already exists: a second container for one test")
    container, tunnel = _start_owned(suite, spec, name, daemon, host, owner, secret)
    return OwnedContainer(container=container, tunnel=tunnel)


__all__ = [
    "LABEL",
    "LEASE_SECONDS",
    "RUN_ID_ENV",
    "RUN_OWNER_ENV",
    "Daemon",
    "ExecReady",
    "HttpReady",
    "Labelled",
    "LocalDaemon",
    "LogReady",
    "OwnedContainer",
    "Ready",
    "ServiceSpec",
    "SharedContainer",
    "SharedServiceError",
    "SshDaemon",
    "Suite",
    "TcpDaemon",
    "acquire",
    "begin_run",
    "binding",
    "bound_addresses",
    "container_name",
    "current_daemon",
    "docker",
    "generate_secret",
    "host_id",
    "labels",
    "locked",
    "lookup",
    "parse_daemon",
    "parse_listing",
    "pets_allowed",
    "process_start",
    "reap_dead_owners",
    "release_run",
    "run_id",
    "run_owner_pid",
    "shared_name",
    "spawn_watcher",
    "start_alone",
    "suite_tier",
    "sweep_removes",
]
