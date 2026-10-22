#  Project:   scalo
#  File:      src/scalo/cli/openapi/output.py
#  Purpose:   Output formats (json, yaml, table, text) and the JMESPath --query
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Render an API answer for the terminal, after the AWS CLI's formatter set.

``--query`` (JMESPath) applies before formatting. Without ``--output`` the format
follows the verb on a terminal, ``get`` as YAML, ``list`` as a table, anything else
as JSON, and is always JSON off a terminal so a script reads a stable shape.
"""

import io
import json
from collections.abc import Callable
from typing import Any

import jmespath
import jmespath.exceptions
import yaml

from .errors import CliUsageError
from .vendor import table as _table
from .vendor import text as _text

FORMATS = ("json", "yaml", "table", "text")


def _default_json(value: Any) -> Any:
    """Encode the stray non-JSON value a response model can carry."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def plain(data: Any) -> Any:
    """``data`` as plain JSON types, through a JSON round trip."""
    return json.loads(json.dumps(data, default=_default_json))


def format_json(data: Any, stream: Any) -> None:
    """Write ``data`` as indented JSON."""
    json.dump(data, stream, indent=2, default=_default_json, ensure_ascii=False)
    stream.write("\n")


def format_yaml(data: Any, stream: Any) -> None:
    """Write ``data`` as YAML, keys in the answer's order."""
    yaml.safe_dump(plain(data), stream, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _rows_for_table(data: Any) -> list[dict[str, Any]]:
    """The answer as rows: a page's items, a list, or one object as one row."""
    if isinstance(data, dict):
        data = data["items"] if isinstance(data.get("items"), list) else [data]
    if not isinstance(data, list):
        return [{"value": data}]
    return [row if isinstance(row, dict) else {"value": row} for row in data]


def _scalar_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Keys holding a scalar in at least one row, in first-seen order."""
    columns: list[str] = []
    for row in rows:
        for key, value in row.items():
            if not isinstance(value, dict | list) and key not in columns:
                columns.append(key)
    return columns


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        return json.dumps(value, default=_default_json)
    return str(value)


def format_table(data: Any, stream: Any) -> None:
    """Write ``data`` as a table of its scalar columns, or as JSON when it has none.

    A page cut short ends with a ``next_page_token: <token>`` line, so a table
    still says where ``--starting-token`` resumes.
    """
    rows = _rows_for_table(data)
    columns = _scalar_columns(rows)
    if rows and not columns:
        format_json(data, stream)
        return
    if not rows:
        stream.write("\n")
    else:
        multitable = _table.MultiTable()
        multitable.add_row_header(columns)
        for row in rows:
            multitable.add_row([_cell(row.get(column, "")) for column in columns])
        multitable.render(stream)
    if isinstance(data, dict) and isinstance(data.get("items"), list) and data.get("next_page_token"):
        stream.write(f"next_page_token: {data['next_page_token']}\n")


def format_text(data: Any, stream: Any) -> None:
    """Write ``data`` as the AWS CLI's tab-delimited text."""
    _text.format_text(plain(data), stream)


_FORMATTERS: dict[str, Callable[[Any, Any], None]] = {
    "json": format_json,
    "yaml": format_yaml,
    "table": format_table,
    "text": format_text,
}


def default_format(verb: str, *, is_tty: bool) -> str:
    """The format used when ``--output`` is not given."""
    if not is_tty:
        return "json"
    if verb == "get":
        return "yaml"
    if verb == "list":
        return "table"
    return "json"


def render(data: Any, output: str) -> str:
    """``data`` rendered in one of :data:`FORMATS`.

    Raises:
        CliUsageError: On an unknown format.
    """
    formatter = _FORMATTERS.get(output)
    if formatter is None:
        raise CliUsageError(f"unknown output format {output!r}: use one of {', '.join(FORMATS)}")
    buffer = io.StringIO()
    formatter(data, buffer)
    return buffer.getvalue()


def apply_query(data: Any, expression: str | None) -> Any:
    """Apply a JMESPath ``--query`` to the answer.

    Raises:
        CliUsageError: When the expression does not parse.
    """
    if not expression:
        return data
    try:
        return jmespath.search(expression, plain(data))
    except jmespath.exceptions.JMESPathError as exc:
        raise CliUsageError(
            f"invalid --query {expression!r}: {exc}",
            input={"query": expression},
            suggestion="check the JMESPath expression",
        ) from exc
