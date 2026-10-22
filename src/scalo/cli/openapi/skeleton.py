#  Project:   scalo
#  File:      src/scalo/cli/openapi/skeleton.py
#  Purpose:   --generate-cli-skeleton from the request schema, and the --cli-input-json/yaml document
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A command's whole input as one document, after the AWS CLI's ``--cli-input-json``.

The document mirrors where each value goes in the request::

    path:   {source: syslog}
    query:  {dry_run: true}
    header: {If-Match: '"3f2a..."'}
    body:   {...the request body...}

so a parameter and a body field of the same name never collide.
``--generate-cli-skeleton`` prints that document with a ``null`` for every value
the operation takes, read from the parameters and the request body schema:
objects show their writable properties and arrays one item. ``--cli-input-json``
and ``--cli-input-yaml`` read one back, as text or ``file://<path>``, and drop
every ``null`` left in it at any depth, so a placeholder is never sent. Flags
given on the command line win over the document.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scalo._openapi import RefResolver, is_read_only, merge_all_of, non_null_member, non_null_type

from .documents import DocumentError, read_document
from .errors import CliUsageError
from .spec import Operation

SECTIONS = ("path", "query", "header", "body")

_FILE_PREFIX = "file://"
_MAX_DEPTH = 8


def _schema_skeleton(schema: Any, resolver: RefResolver, stack: tuple[str, ...] = ()) -> Any:
    """The placeholder for one schema: its writable properties, one array item, else ``None``."""
    ref = schema.get("$ref") if isinstance(schema, Mapping) else None
    if isinstance(ref, str) and (ref in stack or len(stack) >= _MAX_DEPTH):
        return None
    resolved = resolver.resolve(schema)
    stack = (*stack, ref) if isinstance(ref, str) else stack
    member = non_null_member(resolved, resolver)
    if member is not None:
        return _schema_skeleton(member, resolver, stack)
    if non_null_type(resolved) == "array":
        items = resolved.get("items")
        return [_schema_skeleton(items, resolver, stack)] if items else None
    properties, _ = merge_all_of(resolved, resolver)
    writable = {name: prop for name, prop in properties.items() if not is_read_only(prop, resolver)}
    if not writable:
        return None
    return {name: _schema_skeleton(prop, resolver, stack) for name, prop in writable.items()}


def skeleton(operation: Operation, spec: Mapping[str, Any]) -> dict[str, Any]:
    """The input document for one operation, every value ``null``.

    Args:
        operation: The operation.
        spec: The spec its schemas live in.

    Returns:
        One section per place the operation takes input, sections it has none for left out.
    """
    document: dict[str, Any] = {}
    for field in operation.parameters:
        document.setdefault(field.location, {})[field.name] = None
    if operation.body_schema is not None:
        document["body"] = _schema_skeleton(operation.body_schema, RefResolver(spec))
    return {section: document[section] for section in SECTIONS if section in document}


def prune(value: Any) -> Any:
    """``value`` without its ``null`` values at any depth, ``None`` when nothing is left.

    An object or list given empty stays: only one that pruning emptied goes, so a
    skeleton's untouched placeholders are never sent but an explicit ``{}`` or ``[]`` is.
    """
    if isinstance(value, dict):
        kept = {name: pruned for name, item in value.items() if (pruned := prune(item)) is not None}
        return None if value and not kept else kept
    if isinstance(value, list):
        items = [pruned for item in value if (pruned := prune(item)) is not None]
        return None if value and not items else items
    return value


def read_text_argument(value: str, option: str) -> str:
    """An option's text, or the file a ``file://<path>`` value names.

    Raises:
        CliUsageError: When the file cannot be read.
    """
    if not value.startswith(_FILE_PREFIX):
        return value
    path = Path(value[len(_FILE_PREFIX) :]).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliUsageError(f"{option}: cannot read {path}: {exc.strerror or exc}") from exc


def parse_option(text: str, *, option: str, yaml_allowed: bool) -> Any:
    """Parse an option's JSON, or YAML when allowed, naming the option on failure.

    Raises:
        CliUsageError: When the text does not parse.
    """
    try:
        return read_document(text, yaml_allowed=yaml_allowed)
    except DocumentError as exc:
        raise CliUsageError(f"{option} is {exc}") from exc


def load_input(json_value: str | None, yaml_value: str | None) -> dict[str, Any]:
    """Read ``--cli-input-json`` or ``--cli-input-yaml`` into an input document.

    Raises:
        CliUsageError: When both are given, the text does not parse, or the
            document is not a mapping of :data:`SECTIONS`.
    """
    if json_value is not None and yaml_value is not None:
        raise CliUsageError("give --cli-input-json or --cli-input-yaml, not both")
    if json_value is None and yaml_value is None:
        return {}
    option = "--cli-input-json" if json_value is not None else "--cli-input-yaml"
    raw = json_value if json_value is not None else yaml_value
    document = parse_option(read_text_argument(str(raw), option), option=option, yaml_allowed=yaml_value is not None)
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise CliUsageError(f"{option} must be a mapping of {', '.join(SECTIONS)}")
    unknown = sorted(str(key) for key in document if key not in SECTIONS)
    if unknown:
        raise CliUsageError(f"{option} has unknown section(s) {unknown}: use {', '.join(SECTIONS)}")
    for section in ("path", "query", "header"):
        if section in document and not isinstance(document[section], dict):
            raise CliUsageError(f"{option}: '{section}' must be a mapping")
    return document
