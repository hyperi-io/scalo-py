#  Project:   scalo
#  File:      src/scalo/api/openapi.py
#  Purpose:   Write x-scalo onto every spec operation and wire an app to the conventions
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Write ``x-scalo`` onto every operation of a FastAPI app's spec.

Each operation gets::

    x-scalo:
      group: sources              # the root resource
      resource: rules             # the resource the verb acts on
      hierarchy: [sources, rules]
      verb: list
      read_only: true
      cli: {hidden: false, aliases: [], positional: []}
      mcp: {tool: sources_rules_list, read_only: true, destructive: false, task: false}  # opted in only
      action: rule:read           # or public: true

:func:`install` wires an app in one call: problem+json handlers, and an
``app.openapi`` that annotates the spec it generates.
"""

from collections.abc import Iterator, Sequence
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.routing import BaseRoute

from .extension import EXTENSION, declared_extension, dependency_actions
from .hierarchy import Hierarchy, OperationName
from .problems import declare_problem_responses, install_problem_handlers

_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def api_routes(routes: Sequence[BaseRoute]) -> Iterator[RouteContext]:
    """Every API route in the spec, with its included routers' prefixes and dependencies applied.

    Args:
        routes: ``app.routes``, included routers unexpanded.

    Yields:
        The context of each ``APIRoute`` that is included in the schema.
    """
    for context in iter_route_contexts(routes):
        if isinstance(context.original_route, APIRoute) and context.include_in_schema:
            yield context


def route_actions(context: RouteContext) -> list[str]:
    """The RBAC actions a route checks: its declared action, else its permission dependencies."""
    declared = declared_extension(context.openapi_extra).get("action")
    if isinstance(declared, str) and declared:
        return [declared]
    return dependency_actions(context.dependant)


def operation_extension(
    name: OperationName, declared: dict[str, Any], actions: list[str], hierarchy: Hierarchy
) -> dict[str, Any]:
    """The ``x-scalo`` object for one operation.

    Args:
        name: The operation's derived name.
        declared: The route's own ``x-scalo`` declarations.
        actions: The RBAC actions the route checks.
        hierarchy: The naming model, for the MCP tool name.

    Returns:
        A new dict, sharing nothing with ``declared``.
    """
    read_only = declared.get("read_only")
    if not isinstance(read_only, bool):
        read_only = name.method in _READ_ONLY_METHODS
    cli = {"hidden": False, "aliases": [], "positional": [], **(declared.get("cli") or {})}
    extension: dict[str, Any] = {
        "group": name.group,
        "resource": name.resource,
        "hierarchy": list(name.hierarchy),
        "verb": name.verb,
        "read_only": read_only,
        "cli": {key: list(value) if isinstance(value, list) else value for key, value in cli.items()},
    }
    mcp = declared.get("mcp")
    if isinstance(mcp, dict):
        extension["mcp"] = {
            "tool": hierarchy.tool_name(name),
            "read_only": read_only,
            "destructive": name.method == "DELETE",
            **mcp,
        }
    if declared.get("public") is True:
        extension["public"] = True
    if actions:
        extension["action"] = actions[0] if len(actions) == 1 else sorted(actions)
    return extension


def annotate_openapi(spec: dict[str, Any], routes: Sequence[BaseRoute], hierarchy: Hierarchy) -> dict[str, Any]:
    """Write ``x-scalo`` onto every operation in ``spec`` that a route in ``routes`` serves.

    Idempotent. Call it from a custom ``app.openapi`` after ``get_openapi``, or let
    :func:`install` do it.

    Args:
        spec: The generated OpenAPI document, updated in place.
        routes: The application's routes.
        hierarchy: The naming model.

    Returns:
        ``spec``.
    """
    paths = spec.get("paths", {})
    for context in api_routes(routes):
        path = context.path_format or ""
        declared = declared_extension(context.openapi_extra)
        verb = declared.get("verb")
        actions = route_actions(context)
        for method in sorted(context.methods or ()):
            operation = paths.get(path, {}).get(method.lower())
            if operation is None:
                continue
            name = hierarchy.parse(path, method, verb=verb if isinstance(verb, str) else None)
            operation[EXTENSION] = operation_extension(name, declared, actions, hierarchy)
    return spec


def install(app: FastAPI, hierarchy: Hierarchy, *, problem_handlers: bool = True, catch_unhandled: bool = True) -> None:
    """Hold an app to the conventions: annotated spec, and problem+json errors.

    Wraps whatever ``app.openapi`` is at the time of the call, so a custom
    ``app.openapi`` must be assigned first.

    Args:
        app: The application, built with ``generate_unique_id_function=hierarchy.unique_id``.
        hierarchy: The naming model.
        problem_handlers: Install :func:`scalo.api.install_problem_handlers` and
            declare problem+json responses in the spec.
        catch_unhandled: With ``problem_handlers``, also answer an unhandled
            exception with a 500 problem.

    Raises:
        ValueError: When the app names its operations some other way.
    """
    configured = app.router.generate_unique_id_function
    if getattr(configured, "value", configured) != hierarchy.unique_id:
        raise ValueError("build the app with FastAPI(generate_unique_id_function=hierarchy.unique_id)")
    if problem_handlers:
        install_problem_handlers(app, catch_unhandled=catch_unhandled)

    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        spec = annotate_openapi(generate(), app.routes, hierarchy)
        if problem_handlers:
            declare_problem_responses(spec)
        app.openapi_schema = spec
        return spec

    app.openapi = openapi  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
