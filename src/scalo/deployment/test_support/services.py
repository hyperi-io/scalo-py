#  Project:   scalo
#  File:      src/scalo/deployment/test_support/services.py
#  Purpose:   Pinned specs for the shared ClickHouse, Kafka and OpenBao test containers
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The specs every suite shares for ClickHouse, Kafka and OpenBao.

Each image is pinned here and nowhere else, so a fix to a spec reaches every
suite on its next scalo bump. The images are the releases the services built
on scalo deploy, so a test says something true about production, and they
move deliberately. Hand a spec to
:func:`~scalo.deployment.test_support.shared_service.acquire`.

=============  ==========================================================
ClickHouse     HTTP 8123, native 9000, a generated password for
               ``default``, embedded Keeper and a one-replica cluster
               ``default``, so ``ON CLUSTER`` and the ``Replicated``
               database engine work as they do on a replicated server
Kafka          one KRaft broker, PLAINTEXT on 9092, advertising the host
               port a client here dials, topic auto-create off
OpenBao        dev mode on 8200, the root token generated per run
=============  ==========================================================
"""

from scalo.deployment.test_support.shared_service import HttpReady, LogReady, ServiceSpec, SharedContainer

# renovate: datasource=docker depName=clickhouse/clickhouse-server
CLICKHOUSE_TAG = "26.3.42.3"
CLICKHOUSE_DIGEST = "sha256:21d572843e59539c7d100286b6f5a6053c341fe4b33c2d7b74b1ff7cb24c5399"
CLICKHOUSE_IMAGE = f"clickhouse/clickhouse-server:{CLICKHOUSE_TAG}@{CLICKHOUSE_DIGEST}"
CLICKHOUSE_HTTP_PORT = 8123
CLICKHOUSE_NATIVE_PORT = 9000
CLICKHOUSE_USER = "default"
CLICKHOUSE_CLUSTER = "default"

# The JVM image: apache/kafka-native before 4.4.0 segfaults in getpwuid on about 2% of starts.
# renovate: datasource=docker depName=apache/kafka
KAFKA_TAG = "4.3.1"
KAFKA_DIGEST = "sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837"
KAFKA_IMAGE = f"apache/kafka:{KAFKA_TAG}@{KAFKA_DIGEST}"
KAFKA_PORT = 9092

# renovate: datasource=docker depName=openbao/openbao
OPENBAO_TAG = "2.7.1"
OPENBAO_DIGEST = "sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf"
OPENBAO_IMAGE = f"openbao/openbao:{OPENBAO_TAG}@{OPENBAO_DIGEST}"
OPENBAO_PORT = 8200

# A JVM broker under CI container contention can take most of a minute.
_KAFKA_STARTUP_SECONDS = 180.0
_CLICKHOUSE_STARTUP_SECONDS = 180.0
_OPENBAO_STARTUP_SECONDS = 120.0
_KAFKA_START_SCRIPT = "/opt/kafka/hyperi_start.sh"

_CLICKHOUSE_CLUSTER_CONFIG = f"""<clickhouse>
    <keeper_server>
        <tcp_port>9181</tcp_port>
        <server_id>1</server_id>
        <log_storage_path>/var/lib/clickhouse/coordination/log</log_storage_path>
        <snapshot_storage_path>/var/lib/clickhouse/coordination/snapshots</snapshot_storage_path>
        <raft_configuration>
            <server><id>1</id><hostname>localhost</hostname><port>9234</port></server>
        </raft_configuration>
    </keeper_server>
    <zookeeper><node><host>localhost</host><port>9181</port></node></zookeeper>
    <macros>
        <cluster>{CLICKHOUSE_CLUSTER}</cluster>
        <shard>1</shard>
        <replica>replica-1</replica>
    </macros>
    <remote_servers replace="true">
        <{CLICKHOUSE_CLUSTER}>
            <shard><replica><host>localhost</host><port>{CLICKHOUSE_NATIVE_PORT}</port></replica></shard>
        </{CLICKHOUSE_CLUSTER}>
    </remote_servers>
    <distributed_ddl><path>/clickhouse/task_queue/ddl</path></distributed_ddl>
</clickhouse>
"""


def _clickhouse_files(_host: str) -> list[tuple[str, bytes]]:
    return [("/etc/clickhouse-server/config.d/scalo-test-cluster.xml", _CLICKHOUSE_CLUSTER_CONFIG.encode())]


def clickhouse_spec() -> ServiceSpec:
    """One ClickHouse server shaped like a replicated deployment, for the run.

    ``default`` takes the run's generated password and may manage users, so a
    suite can test row policies and grants on the shared server.
    """
    return ServiceSpec(
        service="clickhouse",
        image=CLICKHOUSE_IMAGE,
        startup_timeout=_CLICKHOUSE_STARTUP_SECONDS,
        ready=HttpReady(port=CLICKHOUSE_HTTP_PORT, path="/ping", body="Ok."),
        ports=(CLICKHOUSE_HTTP_PORT, CLICKHOUSE_NATIVE_PORT),
        env={"CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT": "1"},
        secret_env=("CLICKHOUSE_PASSWORD",),
        files=_clickhouse_files,
    )


def _write_kafka_start_script(container: SharedContainer) -> None:
    """Advertise the published port, which only exists once the container runs."""
    advertised = f"PLAINTEXT://{container.host}:{container.port(KAFKA_PORT)},BROKER://localhost:9093"
    script = f"#!/usr/bin/env bash\nexport KAFKA_ADVERTISED_LISTENERS={advertised}\nexec /etc/kafka/docker/run\n"
    container.exec("sh", "-c", f"printf '%s' '{script}' > {_KAFKA_START_SCRIPT}")


def kafka_spec(host_port: int | None = None) -> ServiceSpec:
    """One single-node KRaft broker, PLAINTEXT on :data:`KAFKA_PORT`.

    It advertises the host port Docker publishes it on, or ``host_port`` when
    given: pin one for a client configured before the broker exists, or for a
    test that stops and starts the broker. Topic auto-create is off, so a test
    creates its topics, as it must on a broker that refuses auto-create.
    """
    wait = f"while [ ! -f {_KAFKA_START_SCRIPT} ]; do sleep 0.1; done; chmod 755 {_KAFKA_START_SCRIPT} && {_KAFKA_START_SCRIPT}"
    env = {
        "KAFKA_LISTENERS": "PLAINTEXT://0.0.0.0:9092,BROKER://0.0.0.0:9093,CONTROLLER://0.0.0.0:9094",
        "CLUSTER_ID": "5L6g3nShT-eMCtK--X86sw",
        "KAFKA_PROCESS_ROLES": "broker,controller",
        "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "BROKER:PLAINTEXT,PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT",
        "KAFKA_INTER_BROKER_LISTENER_NAME": "BROKER",
        "KAFKA_NODE_ID": "1",
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR": "1",
        "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS": "0",
        "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@localhost:9094",
        "KAFKA_AUTO_CREATE_TOPICS_ENABLE": "false",
    }
    ports, pinned = ((), ((KAFKA_PORT, host_port),)) if host_port is not None else ((KAFKA_PORT,), ())
    return ServiceSpec(
        service="kafka",
        image=KAFKA_IMAGE,
        startup_timeout=_KAFKA_STARTUP_SECONDS,
        ready=LogReady("Kafka Server started"),
        ports=ports,
        pinned_ports=pinned,
        env=env,
        entrypoint="bash",
        args=("-c", wait),
        after_start=_write_kafka_start_script,
    )


def openbao_spec() -> ServiceSpec:
    """A dev-mode OpenBao on :data:`OPENBAO_PORT` whose root token is the run's generated secret.

    The ``BAO_`` spellings are required: under ``VAULT_DEV_ROOT_TOKEN_ID`` the
    server issues a random root token instead, and every request is refused.
    """
    return ServiceSpec(
        service="openbao",
        image=OPENBAO_IMAGE,
        startup_timeout=_OPENBAO_STARTUP_SECONDS,
        ready=LogReady("OpenBao server started"),
        ports=(OPENBAO_PORT,),
        env={"BAO_DEV_LISTEN_ADDRESS": f"0.0.0.0:{OPENBAO_PORT}"},
        secret_env=("BAO_DEV_ROOT_TOKEN_ID",),
        args=("server", "-dev"),
    )


__all__ = [
    "CLICKHOUSE_CLUSTER",
    "CLICKHOUSE_DIGEST",
    "CLICKHOUSE_HTTP_PORT",
    "CLICKHOUSE_IMAGE",
    "CLICKHOUSE_NATIVE_PORT",
    "CLICKHOUSE_TAG",
    "CLICKHOUSE_USER",
    "KAFKA_DIGEST",
    "KAFKA_IMAGE",
    "KAFKA_PORT",
    "KAFKA_TAG",
    "OPENBAO_DIGEST",
    "OPENBAO_IMAGE",
    "OPENBAO_PORT",
    "OPENBAO_TAG",
    "clickhouse_spec",
    "kafka_spec",
    "openbao_spec",
]
