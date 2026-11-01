#  Project:   scalo
#  File:      tests/integration/test_ddl_engine_clickhouse.py
#  Purpose:   Engine selection against the run's real ClickHouse, and the server accepting what it renders
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""EngineResolver against a real replicated ClickHouse.

The unit tests answer the sensing queries from a fake. This one sends them to
the run's server (tests/TESTING.md), so a query the server rejects or a system
table that changed shape fails here, and then has the server run the CREATE
TABLE the resolver rendered.
"""

import clickhouse_connect
import pytest

from scalo.ddl import EngineResolver, parse_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def client(shared_clickhouse):
    connected = clickhouse_connect.get_client(
        host=shared_clickhouse.host,
        port=shared_clickhouse.http_port,
        username=shared_clickhouse.user,
        password=shared_clickhouse.password,
        secure=shared_clickhouse.secure,
        ca_cert=shared_clickhouse.ca_file,
    )
    yield connected
    connected.close()


@pytest.fixture
def database(request, shared_clickhouse):
    """A database of this test's own with the engine the parameter names, dropped afterwards."""
    name = shared_clickhouse.database_name(request.node.name)
    shared_clickhouse.create_database(name, engine=request.param)
    yield name
    shared_clickhouse.drop_database(name)


@pytest.mark.parametrize(
    ("database", "engine", "clause", "fans_out"),
    [
        pytest.param("Replicated", "MergeTree", "ReplicatedMergeTree", False, id="replicated-database"),
        pytest.param(
            "Replicated",
            "ReplacingMergeTree(version)",
            "ReplicatedReplacingMergeTree(version)",
            False,
            id="replicated-database-keeps-the-variant",
        ),
        pytest.param("Atomic", "MergeTree", "ReplicatedMergeTree", True, id="atomic-database-on-a-cluster"),
        pytest.param(
            "Atomic",
            "SummingMergeTree(version)",
            "ReplicatedSummingMergeTree(version)",
            True,
            id="atomic-database-keeps-the-variant",
        ),
    ],
    indirect=["database"],
)
def test_the_sensed_engine_is_one_the_server_accepts(client, database, engine, clause, fans_out):
    resolved = EngineResolver(client=client).resolve(parse_engine(engine), database)

    assert (resolved.clause, resolved.origin) == (clause, "sensed")
    assert resolved.on_cluster.startswith(" ON CLUSTER ") is fans_out
    client.command(
        f"CREATE TABLE `{database}`.events{resolved.on_cluster} (id UInt64, version UInt64) "
        f"ENGINE = {resolved.clause} ORDER BY id"
    )
    client.command(f"INSERT INTO `{database}`.events VALUES (1, 1)")
    stored = client.query(
        "SELECT engine FROM system.tables WHERE database = {database:String} AND name = 'events'",
        parameters={"database": database},
    )
    assert stored.result_rows == [(clause.split("(", 1)[0],)]
    assert client.query(f"SELECT count() FROM `{database}`.events").result_rows == [(1,)]


def test_a_hostile_database_name_is_bound_not_spliced(client):
    """The server receives the name as a parameter: a quote in it is data, so sensing still answers."""
    resolved = EngineResolver(client=client).resolve(parse_engine("MergeTree"), "no_such_db'; DROP TABLE x --")

    assert resolved.origin == "sensed"
    assert resolved.clause == "ReplicatedMergeTree"
