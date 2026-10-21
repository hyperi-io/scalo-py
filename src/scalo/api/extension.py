#  Project:   scalo
#  File:      src/scalo/api/extension.py
#  Purpose:   The x-scalo OpenAPI extension: route declarations and the permission hook
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The ``x-scalo`` OpenAPI vendor extension.

A route declares what its path cannot say through ``openapi_extra``::

    @router.get("/{source}/preview", response_model=Preview,
                openapi_extra=scalo_extra(verb="preview", cli=CliHints(hidden=True)))

and its RBAC dependency names the action it checks, without scalo knowing any
role::

    def require_action(action: str):
        @permission(action)
        async def check(request: Request) -> None: ...
        return check

:func:`scalo.api.annotate_openapi` then writes the full extension onto every
operation in the spec.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from scalo._openapi import EXTENSION

# Attribute a dependency carries to name the RBAC action it checks.
ACTION_ATTRIBUTE = "__scalo_action__"


@dataclass(frozen=True, slots=True)
class CliHints:
    """How the generated CLI presents an operation.

    Attributes:
        hidden: Leave the operation out of the CLI.
        aliases: Extra command names for the verb.
        positional: Parameters taken as positional arguments, in order.
    """

    hidden: bool = False
    aliases: tuple[str, ...] = ()
    positional: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """The hints as the JSON object ``x-scalo.cli`` carries."""
        return {"hidden": self.hidden, "aliases": list(self.aliases), "positional": list(self.positional)}


@dataclass(frozen=True, slots=True)
class McpHints:
    """Opt an operation in as an MCP tool, with the hints a client reads.

    Attributes:
        tool: Tool name. ``None`` derives it from the operation id.
        read_only: The tool changes nothing. ``None`` follows the operation.
        destructive: The tool deletes or overwrites. ``None`` means only a DELETE.
        task: The tool runs past the request and answers with an operation.
    """

    tool: str | None = None
    read_only: bool | None = None
    destructive: bool | None = None
    task: bool = False

    def as_dict(self) -> dict[str, Any]:
        """The declared hints, leaving out each one left to its derived default."""
        declared: dict[str, Any] = {"task": self.task}
        for key in ("tool", "read_only", "destructive"):
            value = getattr(self, key)
            if value is not None:
                declared[key] = value
        return declared


def scalo_extra(
    *,
    verb: str | None = None,
    public: bool = False,
    action: str | None = None,
    read_only: bool | None = None,
    cli: CliHints | None = None,
    mcp: McpHints | None = None,
) -> dict[str, Any]:
    """Build a route's ``openapi_extra`` carrying its ``x-scalo`` declarations.

    Args:
        verb: The action a GET names, or a verb the path cannot derive.
        public: The route takes no permission check.
        action: The RBAC action the handler itself checks, for a route whose
            check is not a :func:`permission` dependency.
        read_only: The operation changes nothing. ``None`` reads it from the
            method, so only a POST that changes nothing needs it.
        cli: CLI presentation hints.
        mcp: Opt the operation in as an MCP tool.

    Returns:
        ``{"x-scalo": {...}}`` holding only what was declared. Merge other
        ``openapi_extra`` keys into it as needed.

    Raises:
        ValueError: When a route is declared both public and behind an action.
    """
    if public and action:
        raise ValueError(f"a public route checks no action, but action {action!r} was given")
    declared: dict[str, Any] = {}
    if verb:
        declared["verb"] = verb
    if public:
        declared["public"] = True
    if action:
        declared["action"] = action
    if read_only is not None:
        declared["read_only"] = read_only
    if cli is not None:
        declared["cli"] = cli.as_dict()
    if mcp is not None:
        declared["mcp"] = mcp.as_dict()
    return {EXTENSION: declared}


def permission[F: Callable[..., Any]](action: str) -> Callable[[F], F]:
    """Mark a dependency as the check for one RBAC action.

    The spec then carries the action as ``x-scalo.action`` on every route the
    dependency guards, so a UI, CLI or MCP client can hide what a caller cannot
    do. The check itself stays the consumer's.

    Args:
        action: The consumer's action name, such as ``source:write``.

    Returns:
        A decorator that tags the dependency and returns it unchanged.

    Raises:
        ValueError: On an empty action.
    """
    if not action:
        raise ValueError("permission() needs a non-empty action name")

    def mark(dependency: F) -> F:
        setattr(dependency, ACTION_ATTRIBUTE, action)
        return dependency

    return mark


def declared_extension(openapi_extra: Any) -> dict[str, Any]:
    """The ``x-scalo`` declarations in a route's ``openapi_extra``, empty when there are none."""
    if not isinstance(openapi_extra, dict):
        return {}
    declared = openapi_extra.get(EXTENSION)
    return declared if isinstance(declared, dict) else {}


def dependency_actions(dependant: Any) -> list[str]:
    """Every RBAC action the dependencies under ``dependant`` declare, in first-seen order.

    Args:
        dependant: A FastAPI ``Dependant``, walked through every sub-dependency.

    Returns:
        The distinct actions found.
    """
    found: list[str] = []
    pending = list(getattr(dependant, "dependencies", None) or ())
    while pending:
        dependency = pending.pop(0)
        action = getattr(getattr(dependency, "call", None), ACTION_ATTRIBUTE, None)
        if isinstance(action, str) and action not in found:
            found.append(action)
        pending.extend(getattr(dependency, "dependencies", None) or ())
    return found
