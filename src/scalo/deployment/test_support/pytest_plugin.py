#  Project:   scalo
#  File:      src/scalo/deployment/test_support/pytest_plugin.py
#  Purpose:   pytest fixtures for the run's shared ClickHouse, Kafka and OpenBao
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""pytest plugin: the run's one ClickHouse, Kafka and OpenBao, shared by every xdist worker.

Load it from the root ``conftest.py``::

    pytest_plugins = ["scalo.deployment.test_support.pytest_plugin"]

and name the repo once, for container names and labels, in the pytest config
(the ``[project]`` name in ``pyproject.toml`` is the fallback)::

    [tool.pytest.ini_options]
    shared_service_repo = "my-app"

The controller names the run before xdist starts its workers and removes the
run's containers once the session ends. The first worker to ask for a service
starts it and the rest join it (:mod:`.shared_service`). A test isolates
itself in a database, topic or secret path of its own, never a server of its
own: :func:`clickhouse_database` and :func:`kafka_topics` make run-prefixed
ones and drop them afterwards.

ClickHouse and Kafka first try the always-present pet the ``HYPERI_TEST_*``
settings name, when :func:`~.shared_service.pets_allowed` and a quick probe
answers, and otherwise start the container. Each says which rung it took.
Without Docker a test skips on a developer's machine and fails in CI or under
the full tier, where a skip is a test that did not run.
"""

import base64
import http.client
import os
import re
import shutil
import socket
import ssl
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlencode

import pytest

from scalo.deployment.test_support import services
from scalo.deployment.test_support.shared_service import (
    LEASE_SECONDS,
    ServiceSpec,
    SharedContainer,
    SharedServiceError,
    Suite,
    acquire,
    begin_run,
    docker,
    locked,
    lookup,
    pets_allowed,
    release_run,
    run_id,
    suite_tier,
)

_REPO_INI = "shared_service_repo"
_OWNS_RUN = pytest.StashKey[Suite]()
_PROBE_SECONDS = 2.0
_CLUSTER_NAME = re.compile(r"[A-Za-z0-9_.-]+")
_DATABASE_ENGINES = frozenset({"Replicated", "Atomic"})
_COORDINATOR_SECONDS = 90.0
_TOPIC_LISTED_SECONDS = 30.0
# Pet object names carry the run and the second it began, so another host's sweep can apply the lease.
_RUN_STARTED_ENV = "HYPERI_TEST_RUN_STARTED"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ini key naming the repo."""
    parser.addini(_REPO_INI, "Repo name for the shared test containers' names and labels.", default="")


def _repo_name(config: pytest.Config) -> str:
    named = str(config.getini(_REPO_INI) or "").strip()
    if named:
        return named
    pyproject = config.rootpath / "pyproject.toml"
    if pyproject.is_file():
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        if project.get("name"):
            return str(project["name"])
    return config.rootpath.name


def suite_for(config: pytest.Config) -> Suite:
    """The :class:`Suite` of this pytest run, rooted at the pytest rootdir."""
    root = config.rootpath
    scratch = root / ".tmp"
    return Suite(
        repo=_repo_name(config), project_dir=root, run_dir=scratch / "shared-services" / run_id(), log_dir=scratch
    )


def pytest_configure(config: pytest.Config) -> None:
    """Name the run in the controller, before xdist starts a worker."""
    if hasattr(config, "workerinput"):
        return
    begin_run()
    os.environ[_RUN_STARTED_ENV] = str(int(time.time()))
    suite = suite_for(config)
    config.stash[_OWNS_RUN] = suite
    # A finished run has removed its run directory, so its log is all it left behind.
    for old_log in suite.log_dir.glob("shared-services-*.log"):
        if not (suite.run_dir.parent / old_log.stem.removeprefix("shared-services-")).exists():
            old_log.unlink(missing_ok=True)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the run's containers and its state, once, in the controller."""
    suite = config.stash.get(_OWNS_RUN, None)
    if suite is None or not suite.run_dir.exists():
        return
    try:
        release_run(suite)
    except SharedServiceError as exc:
        suite.record(f"could not remove the run's containers: {exc}")
    shutil.rmtree(suite.run_dir, ignore_errors=True)


def unavailable(reason: str) -> None:
    """Skip on a developer's machine. Fail in CI or under the full tier, where a skip is a test that did not run."""
    if "CI" in os.environ or suite_tier() == "full":
        pytest.fail(f"{reason}. A test that needs this service must run here.")
    pytest.skip(reason)


def _acquire_or_unavailable(suite: Suite, spec: ServiceSpec) -> SharedContainer:
    if shutil.which("docker") is None or docker("info", "--format", "{{.ServerVersion}}").returncode != 0:
        unavailable(f"no Docker daemon answers for the shared {spec.service}")
    try:
        return acquire(suite, spec)
    except SharedServiceError as exc:
        unavailable(f"the shared {spec.service} did not start: {exc}")
        raise


def _tcp_answers(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=_PROBE_SECONDS).close()
    except OSError:
        return False
    return True


def _object_name(prefix: str, label: str, separator: str) -> str:
    """``<prefix><run><sep><started><sep><label><sep><nonce>``, lowercase and safe for a database or topic."""
    started = os.environ.get(_RUN_STARTED_ENV) or str(int(time.time()))
    slug = re.sub(r"[^a-z0-9]+", separator, label.lower()).strip(separator)[:40]
    return separator.join([f"{prefix}{run_id()}", started, slug, os.urandom(3).hex()])


def _stale(name: str, prefix: str, separator: str, now: int) -> bool:
    """Whether a pet object from another run is past the lease, so its run has ended."""
    parts = name.removeprefix(prefix).split(separator)
    if not name.startswith(prefix) or len(parts) < 2 or not parts[1].isdigit():
        return False
    return parts[0] != run_id() and int(parts[1]) + LEASE_SECONDS < now


def _sweep_once(suite: Suite, what: str, sweep: Callable[[], None]) -> None:
    """Run ``sweep`` in one process of the run only."""
    suite.run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = suite.run_dir / f"{what}.swept"
    with locked(suite.run_dir / f"{what}.lock"):
        if marker.exists():
            return
        sweep()
        marker.touch()


# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClickHouseService:
    """Where the run's ClickHouse is, and who to log in as.

    Attributes:
        host: Host name or address.
        http_port: HTTP (or HTTPS when ``secure``) port.
        native_port: Native protocol port.
        user: User name.
        password: Its password.
        cluster: Cluster to run ``ON CLUSTER`` DDL across.
        secure: Whether the HTTP port speaks TLS.
        ca_file: CA bundle for a TLS port, None for the system store.
        db_prefix: Prefix every run's databases carry.
        rung: ``pet`` or ``container``.
    """

    host: str
    http_port: int
    native_port: int
    user: str
    password: str = field(repr=False)
    cluster: str
    secure: bool = False
    ca_file: str | None = None
    db_prefix: str = "test_"
    rung: str = "container"

    def execute(self, sql: str, params: Mapping[str, str] | None = None, timeout: float = 60.0) -> str:
        """Run one statement over HTTP and return the response body.

        ``params`` binds ``{name:Type}`` placeholders server-side, so a value is
        never spliced into the SQL text.

        Raises:
            SharedServiceError: The server could not be reached, or answered anything but 200.
        """
        if self.secure:
            context = ssl.create_default_context(cafile=self.ca_file)
            # The context verifies the certificate and the host name.
            connection: http.client.HTTPConnection = http.client.HTTPSConnection(  # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
                self.host, self.http_port, timeout=timeout, context=context
            )
        else:
            connection = http.client.HTTPConnection(self.host, self.http_port, timeout=timeout)
        token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        query = {"query": sql} | {f"param_{key}": value for key, value in (params or {}).items()}
        try:
            connection.request("POST", "/?" + urlencode(query), headers={"Authorization": f"Basic {token}"})
            response = connection.getresponse()
            body = response.read().decode("utf-8", "replace")
        except OSError as exc:
            raise SharedServiceError(f"ClickHouse at {self.host}:{self.http_port}: {exc}") from exc
        finally:
            connection.close()
        if response.status != 200:
            raise SharedServiceError(f"ClickHouse refused {sql.split(' ', 2)[:2]}: {body.strip()[:300]}")
        return body

    def database_name(self, label: str) -> str:
        """A database name unique to this run and call, carrying :attr:`db_prefix`."""
        return _object_name(self.db_prefix, label, "_")

    def on_cluster(self) -> str:
        """``ON CLUSTER`` for :attr:`cluster`, which ClickHouse takes only as a literal, never a parameter.

        Raises:
            SharedServiceError: The name holds a character other than a letter, digit, ``_``, ``.`` or ``-``.
        """
        if not _CLUSTER_NAME.fullmatch(self.cluster):
            raise SharedServiceError(f"refusing ClickHouse cluster name {self.cluster!r}")
        return f"ON CLUSTER `{self.cluster}`"

    def create_database(self, name: str, engine: str = "Replicated") -> None:
        """Create database ``name`` across the cluster, the name bound server-side."""
        if engine not in _DATABASE_ENGINES:
            raise SharedServiceError(f"refusing database engine {engine!r}")
        ddl = f"CREATE DATABASE {{db:Identifier}} {self.on_cluster()} ENGINE = {engine}"
        # The name is a bound Identifier, the cluster is checked above, and the engine is one of two.
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.django.security.injection.tainted-sql-string.tainted-sql-string
        self.execute(ddl, {"db": name})

    def drop_database(self, name: str) -> None:
        """Drop database ``name`` across the cluster, the name bound server-side."""
        ddl = f"DROP DATABASE IF EXISTS {{db:Identifier}} {self.on_cluster()} SYNC"
        # The name is a bound Identifier, the cluster is checked above, and the engine is one of two.
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.django.security.injection.tainted-sql-string.tainted-sql-string
        self.execute(ddl, {"db": name})


def _clickhouse_pet(suite: Suite) -> ClickHouseService | None:
    host = lookup(suite, "HYPERI_TEST_CLICKHOUSE_HOST")
    if host is None or not pets_allowed():
        return None
    ca_file = lookup(suite, "HYPERI_TEST_CLICKHOUSE_CA_FILE")
    secure = ca_file is not None and lookup(suite, "HYPERI_TEST_CLICKHOUSE_HTTPS_PORT") is not None
    port_key = "HYPERI_TEST_CLICKHOUSE_HTTPS_PORT" if secure else "HYPERI_TEST_CLICKHOUSE_HTTP_PORT"
    pet = ClickHouseService(
        host=host,
        http_port=int(lookup(suite, port_key) or 8123),
        native_port=int(lookup(suite, "HYPERI_TEST_CLICKHOUSE_NATIVE_PORT") or 9000),
        user=lookup(suite, "HYPERI_TEST_CLICKHOUSE_USER") or "default",
        password=lookup(suite, "HYPERI_TEST_CLICKHOUSE_PASSWORD") or "",
        cluster=lookup(suite, "HYPERI_TEST_CLICKHOUSE_CLUSTER") or services.CLICKHOUSE_CLUSTER,
        secure=secure,
        ca_file=ca_file,
        db_prefix=lookup(suite, "HYPERI_TEST_CLICKHOUSE_DB_PREFIX") or "test_",
        rung="pet",
    )
    try:
        pet.execute("SELECT 1", timeout=_PROBE_SECONDS)
    except SharedServiceError as exc:
        suite.record(f"the ClickHouse pet at {host} did not answer ({exc}), so the run starts a container")
        return None
    return pet


def _sweep_clickhouse(service: ClickHouseService) -> None:
    listed = service.execute(
        "SELECT name FROM system.databases WHERE startsWith(name, {prefix:String})", {"prefix": service.db_prefix}
    )
    now = int(time.time())
    for name in listed.split():
        if _stale(name, service.db_prefix, "_", now):
            service.drop_database(name)


@pytest.fixture(scope="session")
def shared_clickhouse(pytestconfig: pytest.Config) -> ClickHouseService:
    """The run's ClickHouse: the pet when allowed and answering, else the shared container."""
    suite = suite_for(pytestconfig)
    pet = _clickhouse_pet(suite)
    if pet is not None:
        suite.record(f"ClickHouse: pet {pet.host}:{pet.http_port} (tier {suite_tier()})")
        _sweep_once(suite, "clickhouse-pet", lambda: _sweep_clickhouse(pet))
        return pet
    container = _acquire_or_unavailable(suite, services.clickhouse_spec())
    return ClickHouseService(
        host=container.host,
        http_port=container.port(services.CLICKHOUSE_HTTP_PORT),
        native_port=container.port(services.CLICKHOUSE_NATIVE_PORT),
        user=services.CLICKHOUSE_USER,
        password=container.secret,
        cluster=services.CLICKHOUSE_CLUSTER,
    )


@pytest.fixture
def clickhouse_database(shared_clickhouse: ClickHouseService, request: pytest.FixtureRequest) -> Iterator[str]:
    """A ``Replicated`` database of this test's own, made ``ON CLUSTER`` and dropped afterwards."""
    name = shared_clickhouse.database_name(request.node.name)
    shared_clickhouse.create_database(name)
    yield name
    shared_clickhouse.drop_database(name)


# ---------------------------------------------------------------------------
# Kafka
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KafkaService:
    """Where the run's Kafka is.

    Attributes:
        bootstrap: ``host:port`` of the bootstrap broker.
        client_config: librdkafka settings a client needs, security included.
        topic_prefix: Prefix every run's topics carry.
        group_prefix: Prefix every run's consumer groups carry, the one a pet broker grants.
        rung: ``pet`` or ``container``.
    """

    bootstrap: str
    client_config: Mapping[str, str] = field(repr=False)
    topic_prefix: str = "test-"
    group_prefix: str = "test-"
    rung: str = "container"

    def topic_name(self, label: str) -> str:
        """A topic name unique to this run and call, carrying :attr:`topic_prefix`."""
        return _object_name(self.topic_prefix, label, "-")

    def group_name(self, label: str) -> str:
        """A consumer group id unique to this run and call, carrying :attr:`group_prefix`."""
        return _object_name(self.group_prefix, label, "-")


def _kafka_pet(suite: Suite) -> KafkaService | None:
    bootstrap = lookup(suite, "HYPERI_TEST_KAFKA_BOOTSTRAP")
    if bootstrap is None or not pets_allowed():
        return None
    host, _, port = bootstrap.rpartition(":")
    if not port.isdigit() or not _tcp_answers(host, int(port)):
        suite.record(f"the Kafka pet at {bootstrap} did not answer, so the run starts a container")
        return None
    config = {"bootstrap.servers": bootstrap}
    keys = {
        "security.protocol": "HYPERI_TEST_KAFKA_SECURITY_PROTOCOL",
        "sasl.mechanism": "HYPERI_TEST_KAFKA_SASL_MECHANISM",
        "sasl.username": "HYPERI_TEST_KAFKA_USER",
        "sasl.password": "HYPERI_TEST_KAFKA_PASSWORD",
        "ssl.ca.location": "HYPERI_TEST_KAFKA_CA_FILE",
    }
    for setting, key in keys.items():
        if value := lookup(suite, key):
            config[setting] = value
    prefix = lookup(suite, "HYPERI_TEST_KAFKA_TOPIC_PREFIX") or "test-"
    groups = lookup(suite, "HYPERI_TEST_KAFKA_GROUP_PREFIX") or prefix
    return KafkaService(bootstrap=bootstrap, client_config=config, topic_prefix=prefix, group_prefix=groups, rung="pet")


def _admin(service: KafkaService):
    from confluent_kafka.admin import AdminClient

    return AdminClient(dict(service.client_config))


def _sweep_kafka(service: KafkaService) -> None:
    admin = _admin(service)
    now = int(time.time())
    listed = admin.list_topics(timeout=30).topics
    stale = [name for name in listed if _stale(name, service.topic_prefix, "-", now)]
    if stale:
        for future in admin.delete_topics(stale, operation_timeout=30).values():
            future.result()


def _wait_for_group_coordinator(service: KafkaService) -> None:
    """Wait until the broker answers offset requests.

    A new broker makes its offsets topic on the first group request and answers
    ``NOT_COORDINATOR`` until it has, so the first test to read committed offsets
    would otherwise fail on the broker's start-up rather than its own logic.

    Raises:
        SharedServiceError: The coordinator did not answer within the deadline.
    """
    from confluent_kafka import Consumer, KafkaException, TopicPartition

    probe = Consumer({**service.client_config, "group.id": "scalo-test-coordinator-probe"})
    deadline = time.monotonic() + _COORDINATOR_SECONDS
    try:
        while True:
            try:
                probe.committed([TopicPartition("scalo-test-coordinator-probe", 0)], timeout=5)
                return
            except KafkaException as exc:
                if time.monotonic() >= deadline:
                    raise SharedServiceError(f"the Kafka group coordinator did not answer: {exc}") from exc
                time.sleep(0.5)
    finally:
        probe.close()


@pytest.fixture(scope="session")
def shared_kafka(pytestconfig: pytest.Config) -> KafkaService:
    """The run's Kafka: the pet when allowed and answering, else the shared broker."""
    suite = suite_for(pytestconfig)
    pet = _kafka_pet(suite)
    if pet is not None:
        suite.record(f"Kafka: pet {pet.bootstrap} (tier {suite_tier()})")
        _sweep_once(suite, "kafka-pet", lambda: _sweep_kafka(pet))
        return pet
    container = _acquire_or_unavailable(suite, services.kafka_spec())
    bootstrap = container.addr(services.KAFKA_PORT)
    service = KafkaService(bootstrap=bootstrap, client_config={"bootstrap.servers": bootstrap})
    _sweep_once(suite, "kafka-coordinator", lambda: _wait_for_group_coordinator(service))
    return service


def _wait_until_listed(admin, name: str, partitions: int) -> None:
    """Wait until the broker's metadata lists ``name`` with a leader for every partition.

    A create returns once the controller has the topic, which can be before the
    broker a client asks lists it.
    """
    deadline = time.monotonic() + _TOPIC_LISTED_SECONDS
    while True:
        found = admin.list_topics(name, timeout=5).topics.get(name)
        if found is not None and found.error is None and len(found.partitions) == partitions:
            if all(p.leader >= 0 for p in found.partitions.values()):
                return
        if time.monotonic() >= deadline:
            raise SharedServiceError(f"topic {name} was created but never listed with a leader per partition")
        time.sleep(0.1)


@pytest.fixture
def kafka_topics(shared_kafka: KafkaService, request: pytest.FixtureRequest) -> Iterator[Callable[..., str]]:
    """Make run-prefixed topics on the run's Kafka, deleted after the test: ``kafka_topics("orders", partitions=3)``."""
    from confluent_kafka.admin import NewTopic

    admin = _admin(shared_kafka)
    made: list[str] = []

    def make(label: str = "", *, partitions: int = 3) -> str:
        name = shared_kafka.topic_name(label or request.node.name)
        replication = -1 if shared_kafka.rung == "pet" else 1
        topic = NewTopic(name, num_partitions=partitions, replication_factor=replication)
        admin.create_topics([topic], operation_timeout=30)[name].result()
        made.append(name)
        _wait_until_listed(admin, name, partitions)
        return name

    yield make
    if made:
        for future in admin.delete_topics(made, operation_timeout=30).values():
            future.result()


@pytest.fixture
def kafka_group(shared_kafka: KafkaService) -> Callable[[str], str]:
    """Name consumer groups under the run's group prefix, which a pet broker's ACLs grant: ``kafka_group("lag")``."""
    return shared_kafka.group_name


# ---------------------------------------------------------------------------
# OpenBao
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenBaoService:
    """Where the run's OpenBao is, and its root token.

    Attributes:
        address: ``http://host:port``.
        token: The root token.
    """

    address: str
    token: str = field(repr=False)


@pytest.fixture(scope="session")
def shared_openbao(pytestconfig: pytest.Config) -> OpenBaoService:
    """The run's dev-mode OpenBao container."""
    container = _acquire_or_unavailable(suite_for(pytestconfig), services.openbao_spec())
    return OpenBaoService(address=f"http://{container.addr(services.OPENBAO_PORT)}", token=container.secret)


__all__ = [
    "ClickHouseService",
    "KafkaService",
    "OpenBaoService",
    "clickhouse_database",
    "kafka_topics",
    "shared_clickhouse",
    "shared_kafka",
    "shared_openbao",
    "suite_for",
    "unavailable",
]
