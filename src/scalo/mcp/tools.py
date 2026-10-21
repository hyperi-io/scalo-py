#  Project:   scalo
#  File:      src/scalo/mcp/tools.py
#  Purpose:   Read the x-scalo MCP opt-ins out of an OpenAPI spec into tool definitions
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tool definitions read out of an OpenAPI spec.

The spec is the only input. An operation is a tool when its ``x-scalo`` carries an
``mcp`` block, which :func:`scalo.api.annotate_openapi` writes for a route declared
with ``scalo_extra(mcp=McpHints(...))``. A tool's arguments are the operation's
path, query and header parameters, plus ``body`` for a JSON request body:

=================================  ===========================================
``view``                           exposed as ``response_format``
``dry_run``                        on a write, defaults to true: the call
                                   previews
``If-Match``, ``If-None-Match``    never exposed: a write's commit sends the
                                   precondition its ``preview_token`` carries
``preview_token``                  added to every write: the token its preview
                                   returned, which a commit must send back
=================================  ===========================================

Generation refuses, with :class:`McpSpecError`, a spec whose tools could not keep
that contract: two tools with one name, a name MCP does not allow, an
``x-scalo.mcp.read_only`` that disagrees with the operation's, a write without
``dry_run``, or an ``If-Match`` write with no GET on its path to read the current
ETag from.
"""

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from mcp.shared.tool_name_validation import validate_tool_name
from mcp.types import Tool, ToolAnnotations

from scalo._openapi import (
    EXTENSION,
    METHODS,
    RefResolver,
    is_reserved_header,
    json_media,
    merged_parameters,
    unescape_pointer,
)

# The etag a preview returns for a resource that does not exist yet: committing with it creates the resource.
CREATE_ETAG = "*"

_IDEMPOTENT_METHODS = frozenset({"GET", "PUT", "DELETE"})

_SCHEMA_REF = "#/components/schemas/"
_NON_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]+")

# Precondition headers: a write's commit sends the one its preview token carries, and a read takes neither.
_PRECONDITION_HEADERS = frozenset({"if-match", "if-none-match"})

# Argument names the tool contract reserves for itself.
BODY = "body"
DRY_RUN = "dry_run"
PREVIEW_TOKEN = "preview_token"  # noqa: S105
RESPONSE_FORMAT = "response_format"


class McpSpecError(ValueError):
    """The spec's MCP opt-ins cannot be served as tools."""


@dataclass(frozen=True, slots=True)
class Argument:
    """One tool argument that maps onto a request parameter.

    Attributes:
        name: The argument's name in the tool's input schema.
        location: ``path``, ``query`` or ``header``.
        wire: The parameter's name in the request.
    """

    name: str
    location: str
    wire: str


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One MCP tool and the operation it calls.

    Attributes:
        name: The tool name, from ``x-scalo.mcp.tool``.
        title: Display title: the operation's summary.
        description: What the tool does, and how a write previews and commits.
        method: The operation's HTTP method, upper case.
        path: The operation's path template.
        operation_id: The operation's id, for logs.
        input_schema: The JSON Schema 2020-12 the arguments must satisfy.
        read_only: The tool changes nothing.
        destructive: The tool deletes or overwrites.
        task: The operation runs past the request and answers with an operation to poll.
        arguments: Arguments that map onto path, query and header parameters.
        body: The operation takes a JSON body, passed as ``body``.
        dry_run: A write that previews by default through the ``dry_run`` query parameter.
        if_match: A write whose commit carries the previewed ETag as ``If-Match``.
        if_none_match: A write that creates a missing resource under ``If-None-Match: *``.
    """

    name: str
    title: str
    description: str
    method: str
    path: str
    operation_id: str
    input_schema: dict[str, Any]
    read_only: bool
    destructive: bool
    task: bool
    arguments: tuple[Argument, ...]
    body: bool
    dry_run: bool
    if_match: bool
    if_none_match: bool

    @property
    def path_arguments(self) -> tuple[Argument, ...]:
        """The arguments the path template takes."""
        return tuple(argument for argument in self.arguments if argument.location == "path")

    def tool(self) -> Tool:
        """The tool as ``tools/list`` advertises it."""
        return Tool(
            name=self.name,
            title=self.title or None,
            description=self.description,
            input_schema=self.input_schema,
            annotations=ToolAnnotations(
                title=self.title or None,
                read_only_hint=self.read_only,
                destructive_hint=self.destructive,
                idempotent_hint=self.read_only or self.method in _IDEMPOTENT_METHODS,
                open_world_hint=False,
            ),
        )


class _Resolver(RefResolver):
    """Follows local ``$ref`` pointers in one spec, and collects the schemas a tool needs."""

    def __init__(self, spec: Mapping[str, Any]) -> None:
        super().__init__(spec)
        schemas = (spec.get("components") or {}).get("schemas") or {}
        self._schemas: Mapping[str, Any] = schemas if isinstance(schemas, Mapping) else {}

    def localise(self, schema: Any, defs: dict[str, Any]) -> Any:
        """``schema`` with component references pointed at ``$defs``, each referenced schema added to ``defs``."""
        if isinstance(schema, list):
            return [self.localise(item, defs) for item in schema]
        if not isinstance(schema, Mapping):
            return schema
        localised: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "$ref" and isinstance(value, str):
                localised[key] = self._local_ref(value, defs)
            else:
                localised[key] = self.localise(value, defs)
        return localised

    def _local_ref(self, ref: str, defs: dict[str, Any]) -> str:
        if not ref.startswith(_SCHEMA_REF):
            raise McpSpecError(f"schema reference {ref!r} is not under {_SCHEMA_REF}")
        name = unescape_pointer(ref[len(_SCHEMA_REF) :])
        if name not in self._schemas:
            raise McpSpecError(f"schema reference {ref!r} names no schema in the spec")
        if name not in defs:
            # Claim the name before descending, so a schema that references itself ends.
            defs[name] = {}
            defs[name] = self.localise(self._schemas[name], defs)
        return "#/$defs/" + name.replace("~", "~0").replace("/", "~1")


def _argument_name(location: str, wire: str) -> str:
    """The input schema name for a parameter: ``view`` reads as ``response_format``, headers as snake_case."""
    if location == "query" and wire == "view":
        return RESPONSE_FORMAT
    if location == "header":
        return _NON_IDENTIFIER.sub("_", wire).strip("_").lower()
    return wire


def _describe(summary: str, details: str, *, read_only: bool, dry_run: bool, task: bool) -> str:
    """The tool description: what the operation does, then how its call previews and commits."""
    parts = [details.strip() or summary.strip()]
    if not read_only and dry_run:
        parts.append(
            "Previews by default and changes nothing. To commit, call again with the same arguments, "
            "dry_run=false and the preview_token the preview returned."
        )
    if task:
        parts.append("Runs past the request: the result names an operation to poll.")
    return "\n\n".join(part for part in parts if part)


@dataclass(slots=True)
class _Building:
    """One tool's input schema while it is assembled."""

    tool: str
    properties: dict[str, Any]
    required: list[str]

    def add(self, name: str, schema: Any, *, required: bool) -> None:
        if name in self.properties:
            raise McpSpecError(f"tool {self.tool}: two arguments are named {name!r}")
        self.properties[name] = schema
        if required:
            self.required.append(name)


def _parameter_schema(parameter: Mapping[str, Any], resolver: _Resolver, defs: dict[str, Any]) -> dict[str, Any]:
    schema = resolver.localise(parameter.get("schema") or {}, defs)
    schema = dict(schema) if isinstance(schema, Mapping) else {}
    description = parameter.get("description")
    if isinstance(description, str) and description and "description" not in schema:
        schema["description"] = description
    return schema


def _tool(
    path: str,
    method: str,
    item: Mapping[str, Any],
    operation: Mapping[str, Any],
    hints: Mapping[str, Any],
    extension: Mapping[str, Any],
    resolver: _Resolver,
    paths: Mapping[str, Any],
) -> ToolSpec:
    name = hints.get("tool")
    if not isinstance(name, str):
        raise McpSpecError(f"{method.upper()} {path}: x-scalo.mcp carries no tool name")
    verdict = validate_tool_name(name)
    if not verdict.is_valid:
        raise McpSpecError(f"tool name {name!r} is not one MCP allows: {'; '.join(verdict.warnings)}")
    read_only = extension.get("read_only") is True
    if hints.get("read_only", read_only) is not read_only:
        # A hint that disagrees with the operation would advertise a write as safe, or skip its preview.
        raise McpSpecError(f"tool {name}: x-scalo.mcp.read_only disagrees with the operation's x-scalo.read_only")
    destructive = hints.get("destructive") is True

    defs: dict[str, Any] = {}
    building = _Building(tool=name, properties={}, required=[])
    arguments: list[Argument] = []
    dry_run = if_match = if_none_match = False
    for parameter in merged_parameters(item, operation, resolver):
        location, wire = parameter["in"], parameter["name"]
        lower = wire.lower()
        if location not in ("path", "query", "header"):
            continue
        if location == "header" and is_reserved_header(wire):
            continue
        if location == "header" and lower in _PRECONDITION_HEADERS:
            if not read_only:
                if_match = if_match or lower == "if-match"
                if_none_match = if_none_match or lower == "if-none-match"
            continue
        if not read_only and location == "query" and wire == DRY_RUN:
            dry_run = True
            continue
        argument = Argument(name=_argument_name(location, wire), location=location, wire=wire)
        required = location == "path" or parameter.get("required") is True
        building.add(argument.name, _parameter_schema(parameter, resolver, defs), required=required)
        arguments.append(argument)

    request_body = resolver.resolve(operation.get("requestBody"))
    media = json_media(request_body.get("content"))
    if media is not None:
        building.add(
            BODY, resolver.localise(media.get("schema") or {}, defs), required=request_body.get("required") is True
        )

    if not read_only:
        if not dry_run:
            raise McpSpecError(f"tool {name} writes but takes no dry_run, so it cannot preview before it commits")
        if if_match and not isinstance((paths.get(path) or {}).get("get"), Mapping):
            raise McpSpecError(f"tool {name} takes If-Match, but {path} has no GET to read the current ETag from")
        building.add(
            DRY_RUN,
            {"type": "boolean", "default": True, "description": "Preview the change without committing it."},
            required=False,
        )
        building.add(
            PREVIEW_TOKEN,
            {
                "type": "string",
                "description": (
                    "The preview_token a dry run returned. Needed to commit: the commit is refused when its "
                    "arguments differ from the preview's, and fails when the resource has changed since."
                ),
            },
            required=False,
        )

    schema: dict[str, Any] = {
        "type": "object",
        "properties": building.properties,
        "additionalProperties": False,
    }
    if building.required:
        schema["required"] = building.required
    if defs:
        schema["$defs"] = dict(sorted(defs.items()))

    summary = str(operation.get("summary") or "")
    operation_id = operation.get("operationId")
    return ToolSpec(
        name=name,
        title=summary,
        description=_describe(
            summary,
            str(operation.get("description") or ""),
            read_only=read_only,
            dry_run=dry_run,
            task=hints.get("task") is True,
        ),
        method=method.upper(),
        path=path,
        operation_id=operation_id if isinstance(operation_id, str) else f"{method.upper()} {path}",
        input_schema=schema,
        read_only=read_only,
        destructive=destructive,
        task=hints.get("task") is True,
        arguments=tuple(arguments),
        body=media is not None,
        dry_run=dry_run,
        if_match=if_match,
        if_none_match=if_none_match,
    )


def _opted_in(spec: Mapping[str, Any]) -> Iterator[tuple[str, str, Mapping[str, Any], Mapping[str, Any]]]:
    """``(path, method, path item, operation)`` for every operation with an ``x-scalo.mcp`` block."""
    paths = spec.get("paths") or {}
    for path, item in paths.items():
        if not isinstance(item, Mapping):
            continue
        for method in METHODS:
            operation = item.get(method)
            if not isinstance(operation, Mapping):
                continue
            extension = operation.get(EXTENSION)
            if isinstance(extension, Mapping) and isinstance(extension.get("mcp"), Mapping):
                yield str(path), method, item, operation


def tools_from_spec(spec: Mapping[str, Any]) -> tuple[ToolSpec, ...]:
    """Every tool the spec opts in, sorted by name.

    Args:
        spec: An OpenAPI 3.1 document whose operations carry ``x-scalo``, such as
            the ``app.openapi()`` of an app wired with :func:`scalo.api.install`.

    Returns:
        One :class:`ToolSpec` per opted-in operation. The order depends only on
        the names, so every replica lists the same tools in the same order.

    Raises:
        McpSpecError: When two tools share a name, a name breaks MCP's naming
            rules, a tool's read-only hint disagrees with its operation, a write
            takes no ``dry_run``, an ``If-Match`` write has no GET on its path,
            two arguments of one tool share a name, or a schema reference leads
            nowhere.
    """
    resolver = _Resolver(spec)
    paths = spec.get("paths") or {}
    found: dict[str, ToolSpec] = {}
    for path, method, item, operation in _opted_in(spec):
        extension = operation[EXTENSION]
        tool = _tool(path, method, item, operation, extension["mcp"], extension, resolver, paths)
        if tool.name in found:
            other = found[tool.name]
            raise McpSpecError(f"tool {tool.name} names both {other.method} {other.path} and {tool.method} {tool.path}")
        found[tool.name] = tool
    return tuple(found[name] for name in sorted(found))
