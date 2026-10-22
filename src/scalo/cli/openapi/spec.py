#  Project:   scalo
#  File:      src/scalo/cli/openapi/spec.py
#  Purpose:   Load an OpenAPI spec and read every operation into a CLI Operation
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Read an OpenAPI document into the operations the CLI turns into commands.

The spec is the only input: a file, a server's ``/openapi.json``, or a parsed
mapping. An operation's place in the command tree comes from ``x-scalo``
(``hierarchy`` and ``verb``, as :mod:`scalo.api` writes them), else from a dotted
``operationId``, else from its path (:mod:`.naming`). ``x-scalo.cli`` hides an
operation, adds aliases and makes parameters positional. Local ``$ref`` pointers
are followed, so the builder sees concrete parameter and body shapes.
"""

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scalo._openapi import (
    EXTENSION,
    METHODS,
    RefResolver,
    is_read_only,
    is_reserved_header,
    json_media,
    merge_all_of,
    merged_parameters,
    non_null_member,
    non_null_type,
)

from .documents import DocumentError, read_document
from .naming import collection_key, derive_group_and_verb, kebab
from .transport import Transport, UrllibTransport

_LOCATIONS = ("path", "query", "header")

_DOTTED_ID = re.compile(r"^[A-Za-z][\w-]*(\.[A-Za-z][\w-]*)+$")


class SpecError(ValueError):
    """The document is not an OpenAPI spec this CLI can read."""


@dataclass(frozen=True, slots=True)
class Field:
    """One value a command takes: a parameter, or a top-level request body property.

    Attributes:
        name: The name on the wire.
        location: ``path``, ``query``, ``header`` or ``body``.
        type: ``str``, ``int``, ``float``, ``bool``, ``array`` or ``object``.
        required: The API needs it.
        description: Help text.
        default: The spec's default, if any.
        enum: Allowed values, empty for any.
        item_type: For an ``array``, the type of its items.
    """

    name: str
    location: str
    type: str
    required: bool = False
    description: str = ""
    default: Any = None
    enum: tuple[Any, ...] = ()
    item_type: str = "str"


@dataclass(frozen=True, slots=True)
class Operation:
    """One API operation, resolved and placed in the command tree.

    Attributes:
        operation_id: The spec's ``operationId``, or ``<METHOD> <path>`` without one.
        method: The HTTP method, lower case.
        path: The path template.
        hierarchy: Group names from the root, kebab-case.
        verb: The command name.
        summary: One-line help.
        description: Full help.
        tags: The spec's tags, for group help.
        read_only: The operation changes nothing.
        hidden: ``x-scalo.cli.hidden``: leave it out of the CLI.
        aliases: Extra command names.
        positional: Parameters taken as positional arguments, in order.
        parameters: Path, query and header parameters.
        body: Top-level request body properties.
        body_schema: The resolved JSON request body schema, ``None`` without one.
        response_schema: The resolved first 2xx JSON response schema.
        paginated: A token-paged list: ``page_token`` in, ``items`` and
            ``next_page_token`` out.
    """

    operation_id: str
    method: str
    path: str
    hierarchy: tuple[str, ...]
    verb: str
    summary: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    read_only: bool = False
    hidden: bool = False
    aliases: tuple[str, ...] = ()
    positional: tuple[str, ...] = ()
    parameters: tuple[Field, ...] = ()
    body: tuple[Field, ...] = ()
    body_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    paginated: bool = False

    @property
    def command_path(self) -> tuple[str, ...]:
        """The groups and the command name, as typed after the program name."""
        return (*self.hierarchy, self.verb)


def load_spec(
    source: str | Path | Mapping[str, Any], *, transport: Transport | None = None, timeout: float = 30.0
) -> dict[str, Any]:
    """Load an OpenAPI document from a mapping, a file or a URL.

    Args:
        source: A parsed spec, a ``.json``/``.yaml`` file, or an ``http(s)://`` URL
            such as a server's ``/openapi.json``.
        transport: Sends the request for a URL. Defaults to :class:`UrllibTransport`.
        timeout: Seconds to wait for a URL.

    Returns:
        The spec.

    Raises:
        SpecError: When the source is not a JSON or YAML object with ``paths``,
            or a URL answers with an error.
        TransportError: When a URL cannot be reached.
    """
    if isinstance(source, Mapping):
        return _checked(dict(source), "the mapping")
    text = str(source)
    if text.startswith(("http://", "https://")):
        sender = transport or UrllibTransport()
        reply = sender.send(
            "GET", text, headers={"Accept": "application/json"}, credentials={}, content=None, timeout=timeout
        )
        if not reply.ok:
            raise SpecError(f"{text} answered {reply.status} {reply.reason}".rstrip())
        return _checked(_parse(reply.content.decode("utf-8", errors="replace"), text), text)
    path = Path(source)
    return _checked(_parse(path.read_text(encoding="utf-8"), str(path)), str(path))


def _parse(text: str, origin: str) -> Any:
    try:
        return read_document(text)
    except DocumentError as exc:
        raise SpecError(f"{origin} is {exc}") from exc


def _checked(spec: Any, origin: str) -> dict[str, Any]:
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise SpecError(f"{origin} is not an OpenAPI document: it has no 'paths' object")
    return spec


def _non_null(schema: Mapping[str, Any], resolver: RefResolver) -> dict[str, Any]:
    """The one non-null member of an optional (``anyOf``/``oneOf`` with null) schema, else the schema."""
    schema = resolver.resolve(schema)
    member = non_null_member(schema, resolver)
    if member is None:
        return schema
    return {**resolver.resolve(member), **{k: v for k, v in schema.items() if k not in ("anyOf", "oneOf", "type")}}


def _type_name(schema: Mapping[str, Any]) -> str:
    raw = non_null_type(schema)
    if raw == "array":
        return "array"
    if raw == "integer":
        return "int"
    if raw == "number":
        return "float"
    if raw == "boolean":
        return "bool"
    if raw == "object" or "properties" in schema or "allOf" in schema or "additionalProperties" in schema:
        return "object"
    return "str"


def _field(
    name: str, location: str, schema: Any, resolver: RefResolver, *, required: bool, description: str = ""
) -> Field:
    concrete = _non_null(schema or {}, resolver)
    type_name = _type_name(concrete)
    item_type = "str"
    if type_name == "array":
        item_type = _type_name(_non_null(concrete.get("items") or {}, resolver))
    enum = concrete.get("enum")
    if type_name == "array" and not enum:
        enum = _non_null(concrete.get("items") or {}, resolver).get("enum")
    return Field(
        name=name,
        location=location,
        type=type_name,
        required=required,
        description=description or str(concrete.get("description") or concrete.get("title") or ""),
        default=concrete.get("default"),
        enum=tuple(enum) if isinstance(enum, list) else (),
        item_type=item_type,
    )


def _parameters(item: Mapping[str, Any], op: Mapping[str, Any], resolver: RefResolver) -> tuple[Field, ...]:
    """Path, query and header parameters, less the headers the client or a proxy sets."""
    fields = []
    for param in merged_parameters(item, op, resolver):
        location, name = param["in"], param["name"]
        if location not in _LOCATIONS:
            continue
        if location == "header" and is_reserved_header(name):
            continue
        fields.append(
            _field(
                name,
                location,
                param.get("schema"),
                resolver,
                required=bool(param.get("required", location == "path")),
                description=str(param.get("description") or ""),
            )
        )
    return tuple(fields)


def _body(op: Mapping[str, Any], resolver: RefResolver) -> tuple[tuple[Field, ...], dict[str, Any] | None]:
    """The request body's top-level writable properties and its resolved schema."""
    body = resolver.resolve(op.get("requestBody"))
    entry = json_media(body.get("content"))
    if entry is None:
        return (), None
    schema = _non_null(entry.get("schema") or {}, resolver)
    properties, required = merge_all_of(schema, resolver)
    fields = tuple(
        _field(name, "body", prop, resolver, required=name in required)
        for name, prop in properties.items()
        if isinstance(name, str) and not is_read_only(prop, resolver)
    )
    return fields, schema


def _response(op: Mapping[str, Any], resolver: RefResolver) -> dict[str, Any] | None:
    for status, raw in sorted((op.get("responses") or {}).items(), key=lambda pair: str(pair[0])):
        if not str(status).startswith("2"):
            continue
        entry = json_media(resolver.resolve(raw).get("content"))
        return None if entry is None else _non_null(entry.get("schema") or {}, resolver)
    return None


def mapping(value: Any) -> Mapping[str, Any]:
    """``value`` when it is a mapping, else an empty one."""
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _place(
    op: Mapping[str, Any], path: str, method: str, collections: set[str], base_path: str | None
) -> tuple[tuple[str, ...], str]:
    """The group path and verb: ``x-scalo`` first, then a dotted operationId, then the path."""
    extension = op.get(EXTENSION)
    if isinstance(extension, Mapping):
        hierarchy, verb = extension.get("hierarchy"), extension.get("verb")
        if isinstance(hierarchy, list) and isinstance(verb, str) and verb:
            names = _strings(hierarchy)
            if len(names) == len(hierarchy):
                return tuple(kebab(name) for name in names), kebab(verb)
    operation_id = op.get("operationId")
    if isinstance(operation_id, str) and _DOTTED_ID.match(operation_id):
        *groups, verb = operation_id.split(".")
        return tuple(kebab(name) for name in groups), kebab(verb)
    groups, verb = derive_group_and_verb(path, method, collections, base_path)
    return tuple(groups), verb


def _paginated(parameters: tuple[Field, ...], response: dict[str, Any] | None, resolver: RefResolver) -> bool:
    if response is None:
        return False
    query = {field.name for field in parameters if field.location == "query"}
    properties, _ = merge_all_of(response, resolver)
    return "page_token" in query and {"items", "next_page_token"} <= set(properties)


def _operation(
    path: str,
    item: Mapping[str, Any],
    method: str,
    op: Mapping[str, Any],
    resolver: RefResolver,
    collections: set[str],
    base_path: str | None,
) -> Operation:
    hierarchy, verb = _place(op, path, method, collections, base_path)
    extension = mapping(op.get(EXTENSION))
    cli = mapping(extension.get("cli"))
    read_only = extension.get("read_only")
    parameters = _parameters(item, op, resolver)
    body, body_schema = _body(op, resolver)
    response = _response(op, resolver)
    operation_id = op.get("operationId")
    return Operation(
        operation_id=operation_id if isinstance(operation_id, str) and operation_id else f"{method.upper()} {path}",
        method=method,
        path=path,
        hierarchy=hierarchy,
        verb=verb,
        summary=str(op.get("summary") or ""),
        description=str(op.get("description") or ""),
        tags=_strings(op.get("tags")),
        read_only=read_only if isinstance(read_only, bool) else method == "get",
        hidden=cli.get("hidden") is True,
        aliases=tuple(kebab(alias) for alias in _strings(cli.get("aliases"))),
        positional=_strings(cli.get("positional")),
        parameters=parameters,
        body=body,
        body_schema=body_schema,
        response_schema=response,
        paginated=_paginated(parameters, response, resolver),
    )


def iter_operations(spec: Mapping[str, Any], *, base_path: str | None = None) -> Iterator[Operation]:
    """Every operation in the spec, hidden ones included, in spec order.

    Args:
        spec: The OpenAPI document.
        base_path: Prefix the path-derived names leave out, for an operation with
            neither ``x-scalo`` nor a dotted operationId. ``None`` strips
            ``/api/v<N>``.

    Yields:
        One :class:`Operation` per path and method.
    """
    resolver = RefResolver(spec)
    paths = spec.get("paths") or {}
    collections = {key for key in (collection_key(path, base_path) for path in paths) if key is not None}
    for path, raw_item in paths.items():
        item = resolver.resolve(raw_item)
        for method in METHODS:
            op = item.get(method)
            if isinstance(op, Mapping):
                yield _operation(str(path), item, method, op, resolver, collections, base_path)


def tag_descriptions(spec: Mapping[str, Any]) -> dict[str, str]:
    """Each tag's description from the spec's ``tags`` list."""
    found: dict[str, str] = {}
    for tag in spec.get("tags") or ():
        if isinstance(tag, Mapping) and isinstance(tag.get("name"), str) and tag.get("description"):
            found[tag["name"]] = str(tag["description"])
    return found
