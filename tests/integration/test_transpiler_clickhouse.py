#  Project:   scalo
#  File:      tests/integration/test_transpiler_clickhouse.py
#  Purpose:   A pushed-down filter gives the run's ClickHouse the answer CEL gives in process
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The SQL ``transpile_to_clickhouse`` emits, run by a real ClickHouse, matches ``evaluate``.

Each case groups operators where dropped parentheses change the answer, so a
transpiler that loses the grouping fails here rather than in a query that
returns the wrong rows.
"""

import clickhouse_connect
import pytest

from scalo.expression import TranspileError, evaluate, transpile_to_clickhouse

pytestmark = pytest.mark.integration

ROW = {"a": 8.0, "b": 4.0, "c": 2.0, "i": 7, "j": 5, "k": 3, "n": -7, "m": -2, "t": True, "f": False}

_SELECT_ROW = (
    "SELECT 8.0 AS a, 4.0 AS b, 2.0 AS c, toInt64(7) AS i, toInt64(5) AS j, toInt64(3) AS k,"
    " toInt64(-7) AS n, toInt64(-2) AS m, true AS t, false AS f"
)


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


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("a - (b - c)", id="subtract-a-difference"),
        pytest.param("(a - b) - c", id="subtract-left-grouped"),
        pytest.param("a - (b + c)", id="subtract-a-sum"),
        pytest.param("a / (b * 2.0)", id="divide-by-a-product"),
        pytest.param("a / (b / 2.0)", id="divide-by-a-quotient"),
        pytest.param("a / double(b)", id="divide-by-a-converted-double"),
        pytest.param("i / 2", id="int-divide"),
        pytest.param("n / 2", id="int-divide-negative-truncates-toward-zero"),
        pytest.param("i / -2", id="int-divide-by-a-negative"),
        pytest.param("n / int(m)", id="int-divide-two-negatives"),
        pytest.param("(n - 1) / 2", id="int-divide-a-difference"),
        pytest.param("i - n / 2", id="int-divide-inside-a-difference"),
        pytest.param("n / 2 * 2", id="int-divide-then-multiply"),
        pytest.param("-n / 2", id="int-divide-a-negation"),
        pytest.param("n % 3", id="modulo-negative-dividend"),
        pytest.param("i % -3", id="modulo-negative-divisor"),
        pytest.param("(a + b) * c", id="sum-times"),
        pytest.param("a * (b - c)", id="times-a-difference"),
        pytest.param("a + b * c", id="precedence-unbracketed"),
        pytest.param("-(a - b)", id="negate-a-difference"),
        pytest.param("i % (j % k)", id="modulo-of-a-modulo"),
        pytest.param("i - (j - k) > 4", id="comparison-over-a-difference"),
        pytest.param("(a > b) == t", id="compare-a-comparison"),
        pytest.param("t == (a < b)", id="compare-to-a-comparison"),
        pytest.param("!(t && f)", id="not-a-conjunction"),
        pytest.param("t && (f || t)", id="and-a-disjunction"),
        pytest.param("(t && f) || t", id="or-a-conjunction"),
    ],
)
def test_the_pushed_down_filter_agrees_with_the_in_process_one(client, expr):
    sql = transpile_to_clickhouse(expr)
    pushed_down = client.query(f"SELECT {sql} FROM ({_SELECT_ROW})").result_rows[0][0]
    in_process = evaluate(expr, ROW)
    # ClickHouse answers a comparison as 0 or 1.
    want = int(in_process) if isinstance(in_process, bool) else in_process
    assert pushed_down == pytest.approx(want), f"{expr!r} became {sql!r}"


@pytest.mark.parametrize(
    "expr",
    [
        pytest.param("i / j", id="two-int-fields"),
        pytest.param("a / b", id="two-double-fields"),
        pytest.param("(i + j) / k", id="fields-all-the-way-down"),
    ],
)
def test_a_division_with_no_fixed_type_is_left_to_evaluate(expr):
    """CEL divides ints as integers and doubles as doubles, so with no typed operand only the data decides."""
    with pytest.raises(TranspileError, match="no fixed type"):
        transpile_to_clickhouse(expr)
    assert evaluate(expr, ROW) is not None
