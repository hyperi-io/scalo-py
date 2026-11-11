#  Project:   scalo
#  File:      tests/integration/test_transpiler_json_clickhouse.py
#  Purpose:   A pushed-down filter on a mixed-type JSON path selects the rows CEL selects
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Filters on a ClickHouse ``JSON`` column, run by a real server, match ``evaluate_condition`` row by row.

ClickHouse infers each path's type per row, so ``doc.a`` below holds an Int64, a
Float64, a String, an Array, a Bool and a UInt64 in different rows. A filter that
reads the path as one type fails the whole query, so every case here runs on
every row.
"""

import json

import clickhouse_connect
import pytest

from scalo.expression import evaluate_condition, transpile_to_clickhouse

pytestmark = pytest.mark.integration

ROWS: dict[int, dict] = {
    1: {"a": 42, "s": "x", "p": "8080", "t": ["x", "y"], "q": True, "n": {"m": 1}},
    2: {"a": 4.5, "s": "y", "p": 8080, "t": [1, 2], "q": False},
    3: {"a": "forty", "s": "forty", "t": "ab"},
    4: {"a": [1, 2.5], "s": "z", "t": []},
    5: {"a": True, "s": "w"},
    6: {"s": "v"},
    7: {"a": 18446744073709551615},
    8: {"a": -3, "n": {"m": "one"}},
}

EXPRESSIONS = [
    "doc.a == 42",
    "doc.a != 42",
    "!(doc.a == 42)",
    "doc.a == 42.0",
    "doc.a == 4.5",
    "doc.a > 10",
    "!(doc.a > 10)",
    "doc.a >= -3",
    "doc.a < 5",
    "10 < doc.a",
    "42 == doc.a",
    'doc.a == "forty"',
    'doc.a != "forty"',
    'doc.s > "w"',
    "doc.p == 8080",
    'doc.p == "8080"',
    "doc.a in [1, 42]",
    'doc.a in ["forty", "x"]',
    'doc.a in [4.5, 42, "forty"]',
    "!(doc.a in [42])",
    'doc.a.contains("ort")',
    '!doc.a.contains("ort")',
    'doc.s.startsWith("f")',
    'doc.s.endsWith("y")',
    "doc.q",
    "!doc.q",
    "doc.q == true",
    "doc.a == true",
    "doc.a != true",
    "has(doc.a)",
    "size(doc.t) > 0",
    "size(doc.t) == 2",
    "size(doc.a) == 5",
    "int(doc.a) > 3",
    "uint(doc.a) > 3",
    "double(doc.a) > 10.0",
    'string(doc.a) == "42"',
    "doc.a + 1 > 10",
    "doc.a % 2 == 0",
    "doc.a / 2 > 1",
    "doc.a * 1.5 > 6.0",
    "doc.n.m == 1",
    'doc.n.m == "one"',
    'doc.a > 10 || doc.a == "forty"',
    "doc.q && doc.a == 42",
    "doc.q ? doc.a == 42 : false",
]


def _sql_string(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


@pytest.fixture(scope="module")
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


@pytest.fixture(scope="module")
def events(client, shared_clickhouse):
    """A table whose ``doc`` column holds ``ROWS``, as the server infers them from JSON text."""
    database = shared_clickhouse.database_name("transpiler_json")
    shared_clickhouse.create_database(database, engine="Atomic")
    table = f"`{database}`.events"
    client.command(f"CREATE TABLE {table} (n UInt8, doc JSON) ENGINE = MergeTree ORDER BY n")
    values = ", ".join(f"({n}, {_sql_string(json.dumps(row))})" for n, row in ROWS.items())
    client.command(f"INSERT INTO {table} VALUES {values}")
    yield table
    shared_clickhouse.drop_database(database)


@pytest.mark.parametrize("expr", EXPRESSIONS)
def test_the_pushed_down_filter_selects_the_rows_cel_selects(client, events, expr):
    sql = transpile_to_clickhouse(expr, json_columns=["doc"])
    selected = [row[0] for row in client.query(f"SELECT n FROM {events} WHERE {sql} ORDER BY n").result_rows]
    matched = [n for n, row in ROWS.items() if evaluate_condition(expr, {"doc": row})]
    assert selected == matched, f"{expr!r} became {sql!r}"


def test_the_rows_hold_every_type_the_cases_rely_on(client, events):
    stored = client.query(f"SELECT groupUniqArray(dynamicType(doc.a)) FROM {events}").result_rows[0][0]
    assert set(stored) >= {"Int64", "UInt64", "Float64", "String", "Bool", "Array(Nullable(Float64))"}
