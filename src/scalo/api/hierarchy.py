#  Project:   scalo
#  File:      src/scalo/api/hierarchy.py
#  Purpose:   Resource hierarchy and operation ids derived from route paths
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Resource hierarchy and operation ids, derived from a route's path and method.

The path is the single source of every name. Resource names alternate collection
and id after Google AIP-122 (``sources/{source}/rules/{rule}``), collections are
plural and kebab-case, and a singleton is a resource with no id
(``deployment``, ``orgs/{org}/usage``). The operation id is the resource names
followed by the verb::

    GET    /api/v1/sources                        sources.list
    GET    /api/v1/sources/{source}               sources.get
    PUT    /api/v1/sources/{source}               sources.apply
    DELETE /api/v1/sources/{source}               sources.delete
    GET    /api/v1/sources/{source}/rules         sources.rules.list
    POST   /api/v1/sources/{source}/deploy        sources.deploy
    POST   /api/v1/sources/{source}/rules/order   sources.rules.order

A trailing literal is an action (an AIP-136 custom method) when it follows a
collection that has no id, or when it is POSTed below another resource and is
not a plural noun. Anything the path cannot say, such as a GET action, is
declared with ``scalo_extra(verb=...)``.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .extension import declared_extension

# Verbs for a resource addressed by its id, or a singleton.
_ITEM_VERBS = {"GET": "get", "PUT": "apply", "PATCH": "update", "DELETE": "delete"}

# Methods an action may use.
_ACTION_METHODS = frozenset({"GET", "POST"})

# The method that names a multi-method route's operation id, most specific first.
_METHOD_ORDER = ("GET", "PUT", "PATCH", "DELETE", "POST")

# Plural nouns that do not end in "s".
DEFAULT_PLURALS = frozenset({"children", "criteria", "data", "indices", "media", "metadata", "people"})

_KEBAB = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TOOL_PREFIX = re.compile(r"^[a-z0-9_]*$")


def _kebab(name: str) -> str:
    """``name`` in kebab-case (``backing_services`` and ``backingServices`` both give ``backing-services``)."""
    spaced = _CAMEL_BOUNDARY.sub("-", name).lower()
    return _NON_ALNUM.sub("-", spaced).strip("-")


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}") and segment.count("{") == 1


def _primary_method(methods: Iterable[str]) -> str:
    """The method that names a multi-method route: GET, PUT, PATCH, DELETE, POST, else the first sorted, else GET."""
    upper = {method.upper() for method in methods}
    for method in _METHOD_ORDER:
        if method in upper:
            return method
    return min(upper) if upper else "GET"


@dataclass(frozen=True, slots=True)
class OperationName:
    """The resource hierarchy and verb one route method names.

    Attributes:
        path: The route path as declared, base path included.
        method: The HTTP method, upper case.
        hierarchy: Resource names from the root, kebab-case.
        verb: The standard method (``list``, ``get``, ``apply``, ``update``,
            ``delete``, ``create``) or the action's name.
        problems: Every hierarchy rule the path breaks, empty when it breaks none.
            Depth is not among them: compare :attr:`depth` with the hierarchy's
            ``max_depth``.
    """

    path: str
    method: str
    hierarchy: tuple[str, ...]
    verb: str
    problems: tuple[str, ...]

    @property
    def operation_id(self) -> str:
        """``<root>.<child...>.<verb>``, the one name the API, CLI and MCP share."""
        return ".".join([*self.hierarchy, self.verb])

    @property
    def group(self) -> str:
        """The root resource, which groups the operation in the CLI and the MCP tool list."""
        return self.hierarchy[0]

    @property
    def resource(self) -> str:
        """The resource the verb acts on."""
        return self.hierarchy[-1]

    @property
    def depth(self) -> int:
        """How many resource levels the path names."""
        return len(self.hierarchy)


@dataclass(slots=True)
class _Level:
    name: str
    singleton: bool
    has_id: bool = False


class Hierarchy:
    """The naming model one API is held to, shared by its spec, CLI and MCP tools.

    Pass :meth:`unique_id` to ``FastAPI(generate_unique_id_function=...)`` so every
    operation id is derived here and none is written by hand.

    Args:
        base_path: Prefix every API path carries, such as ``/api/v1``. It is part
            of no name.
        singletons: Resource names that have no id, such as ``deployment`` or
            ``usage``. A singleton may have children.
        roots: Root resources the API may declare. ``None`` allows any.
        max_depth: Most resource levels a path may name.
        plurals: Plural collection names that do not end in ``s``, added to
            :data:`DEFAULT_PLURALS`.
        tool_prefix: Prefix of the MCP tool name derived from an operation id.

    Raises:
        ValueError: On a ``max_depth`` below 1, a singleton, root or plural that
            is not kebab-case, or a ``tool_prefix`` outside ``[a-z0-9_]``.
    """

    __slots__ = ("_base", "_max_depth", "_plurals", "_roots", "_singletons", "_tool_prefix")

    def __init__(
        self,
        *,
        base_path: str = "",
        singletons: Iterable[str] = (),
        roots: Iterable[str] | None = None,
        max_depth: int = 3,
        plurals: Iterable[str] = (),
        tool_prefix: str = "",
    ) -> None:
        if max_depth < 1:
            raise ValueError(f"max_depth must be at least 1, not {max_depth}")
        if not _TOOL_PREFIX.match(tool_prefix):
            raise ValueError(f"tool_prefix {tool_prefix!r} may hold only a-z, 0-9 and _")
        stripped = base_path.strip("/")
        self._base = f"/{stripped}" if stripped else ""
        self._singletons = _kebab_set(singletons, "singleton")
        self._roots = None if roots is None else _kebab_set(roots, "root")
        self._plurals = DEFAULT_PLURALS | _kebab_set(plurals, "plural")
        self._max_depth = max_depth
        self._tool_prefix = tool_prefix

    @property
    def base_path(self) -> str:
        """The normalised base path, ``""`` when there is none."""
        return self._base

    @property
    def max_depth(self) -> int:
        """Most resource levels a path may name."""
        return self._max_depth

    def is_plural(self, name: str) -> bool:
        """Whether a kebab-case collection name reads as a plural noun.

        Its last word ends in ``s`` but not ``ss``, ``us`` or ``is``, or the name or
        its last word is one of the configured plurals.
        """
        word = name.rsplit("-", 1)[-1]
        if word in self._plurals or name in self._plurals:
            return True
        return word.endswith("s") and not word.endswith(("ss", "us", "is"))

    def tool_name(self, name: OperationName) -> str:
        """The MCP tool name for an operation: the prefix, then the id with ``_`` separators."""
        return self._tool_prefix + name.operation_id.replace(".", "_").replace("-", "_")

    def unique_id(self, route: Any) -> str:
        """Operation id for a FastAPI route, for ``generate_unique_id_function``.

        Never raises: a path that breaks the rules still gets an id, and
        :func:`scalo.api.check_conformance` reports the problem.

        Args:
            route: The ``APIRoute``, or the included-route context, FastAPI passes.

        Returns:
            The route's operation id under its primary method.
        """
        method = _primary_method(getattr(route, "methods", None) or ())
        verb = declared_extension(getattr(route, "openapi_extra", None)).get("verb")
        path = str(getattr(route, "path_format", "") or "")
        return self.parse(path, method, verb=verb if isinstance(verb, str) else None).operation_id

    def parse(self, path: str, method: str, *, verb: str | None = None) -> OperationName:
        """Read the resource hierarchy and verb out of a route path and method.

        Args:
            path: The route path template, such as ``/api/v1/sources/{source}``.
            method: The HTTP method.
            verb: A declared verb. It names the action when it equals the trailing
                literal, and otherwise replaces the derived verb.

        Returns:
            The operation's name, with every rule the path breaks in ``problems``.
        """
        method = method.upper()
        problems: list[str] = []
        segments = self._segments(path, problems)
        declared = _kebab(verb) if verb else ""

        action = ""
        if declared and segments and not _is_param(segments[-1]) and _kebab(segments[-1]) == declared:
            action = declared
            segments = segments[:-1]

        levels, trailing = self._walk(segments, problems)
        action = action or trailing
        if not action and method == "POST" and self._posted_action(levels, segments):
            action = levels.pop().name

        if not levels:
            problems.append("the path names no resource")
            levels = [_Level("root", singleton=True)]

        if action:
            derived = action
            if method not in _ACTION_METHODS:
                problems.append(f"action '{action}' uses {method}: an action is a GET or a POST")
        else:
            derived = self._standard_verb(levels[-1], method, problems)

        self._check_levels(levels, problems)
        return OperationName(
            path=path,
            method=method,
            hierarchy=tuple(level.name for level in levels),
            verb=declared or derived,
            problems=tuple(problems),
        )

    def _segments(self, path: str, problems: list[str]) -> list[str]:
        """The path's segments below the base path."""
        base = self._base
        if base and (path == base or path.startswith(f"{base}/")):
            path = path[len(base) :]
        elif base:
            problems.append(f"the path is outside the base path {base}")
        return [segment for segment in path.split("/") if segment]

    def _walk(self, segments: list[str], problems: list[str]) -> tuple[list[_Level], str]:
        """Resource levels in order, and a trailing literal that follows a collection with no id."""
        levels: list[_Level] = []
        for index, segment in enumerate(segments):
            previous = levels[-1] if levels else None
            if _is_param(segment):
                if previous is None or previous.singleton or previous.has_id:
                    problems.append(f"parameter {segment} does not follow a collection")
                else:
                    previous.has_id = True
                continue
            if "{" in segment or "}" in segment:
                problems.append(f"segment '{segment}' mixes text and a parameter")
            name = _kebab(segment) or "root"
            if name != segment:
                problems.append(f"segment '{segment}' is not kebab-case")
            if previous is not None and not previous.singleton and not previous.has_id:
                if index == len(segments) - 1:
                    return levels, name
                problems.append(f"'{segment}' follows collection '{previous.name}' with no id between them")
            levels.append(_Level(name, singleton=name in self._singletons))
        return levels, ""

    def _posted_action(self, levels: list[_Level], segments: list[str]) -> bool:
        """Whether a POST's trailing literal names an action on the resource above it."""
        if len(levels) < 2 or _is_param(segments[-1]):
            return False
        last = levels[-1]
        return not last.singleton and not last.has_id and not self.is_plural(last.name)

    def _standard_verb(self, level: _Level, method: str, problems: list[str]) -> str:
        """The standard method a verb-less operation names on its last resource."""
        if level.singleton or level.has_id:
            verb = _ITEM_VERBS.get(method)
            if verb is None:
                problems.append(f"{method} on a single resource needs an action segment")
                return _kebab(method)
            return verb
        if method == "GET":
            return "list"
        if method == "POST":
            return "create"
        problems.append(f"{method} on collection '{level.name}' names no standard method")
        return _kebab(method)

    def _check_levels(self, levels: list[_Level], problems: list[str]) -> None:
        """Record plural and root problems."""
        for level in levels:
            if not level.singleton and not self.is_plural(level.name):
                problems.append(f"collection '{level.name}' is not plural: name it as one, or declare a singleton")
        if self._roots is not None and levels[0].name not in self._roots:
            problems.append(f"root '{levels[0].name}' is not a declared root")


def _kebab_set(names: Iterable[str], what: str) -> frozenset[str]:
    """``names`` as a set, refusing any that is not already kebab-case."""
    found = frozenset(names)
    bad = sorted(name for name in found if not _KEBAB.match(name))
    if bad:
        raise ValueError(f"{what} names must be kebab-case: {bad}")
    return found
