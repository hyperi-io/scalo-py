#  Project:   scalo
#  File:      src/scalo/api/conformance.py
#  Purpose:   Check every API operation against the conventions, with an allow-list to adopt them gradually
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Check every operation of an app against the API conventions.

One test holds an API to them::

    def test_api_conformance():
        assert_conformant(app, HIERARCHY, allow=KNOWN_VIOLATIONS, exempt=["/scim/*", "/.well-known/*"])

``allow`` lists today's violations so a consumer can adopt the conventions
router by router. Each entry is a pattern over a violation's key,
``"<rule> <METHOD> <path>"``, so ``"* * /api/v1/sigma/*"`` allows a whole
router. An entry that matches nothing fails the check, which keeps the list
shrinking. ``exempt`` names paths the conventions never apply to, such as
SCIM or OIDC, whose shape a protocol fixes.

The rules:

==========================  =====================================================
``operation-id``            missing, not ``<root>.<child...>.<verb>``, or not the
                            id the hierarchy derives
``duplicate-operation-id``  the same id on two operations
``hierarchy``               the path breaks a resource-name rule
``depth``                   more resource levels than the hierarchy allows
``extension``               ``x-scalo`` missing, or not what the route declares
``response-model``          no response model on a response with a body
``summary``                 neither a summary nor a docstring
``permission``              no ``x-scalo.action`` and not declared public
``pagination``              a list without ``page_size``, ``page_token`` and a
                            ``next_page_token`` in its response
``dry-run``                 a mutation without the ``dry_run`` query parameter
``if-match``                a PUT, PATCH or DELETE without the ``If-Match`` header
==========================  =====================================================
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from fastapi import FastAPI
from fastapi.routing import RouteContext

from .extension import EXTENSION, declared_extension
from .hierarchy import Hierarchy, OperationName
from .openapi import api_routes, operation_extension, route_actions

_OPERATION_ID = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*(\.[a-z][a-z0-9]*(-[a-z0-9]+)*)+$")
_SPEC_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
_NO_BODY_STATUS = frozenset({204, 205, 304})
_PRECONDITION_METHODS = frozenset({"PUT", "PATCH", "DELETE"})
_MAX_REF_HOPS = 16


@dataclass(frozen=True, slots=True)
class Violation:
    """One operation breaking one rule.

    Attributes:
        rule: The rule's name, such as ``pagination``.
        method: The HTTP method.
        path: The route path.
        operation_id: The operation's id in the spec, if it has one.
        message: What is wrong, and how to fix it.
    """

    rule: str
    method: str
    path: str
    operation_id: str | None
    message: str

    @property
    def key(self) -> str:
        """``"<rule> <METHOD> <path>"``, which an allow-list entry matches."""
        return f"{self.rule} {self.method} {self.path}"


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """The outcome of :func:`check_conformance`.

    Attributes:
        violations: Violations no allow-list entry covers.
        allowed: Violations an allow-list entry covers.
        unused_allowances: Allow-list entries that matched no violation.
        checked: Operations checked.
        exempt: Operations skipped as exempt.
    """

    violations: tuple[Violation, ...]
    allowed: tuple[Violation, ...]
    unused_allowances: tuple[str, ...]
    checked: int
    exempt: int

    @property
    def ok(self) -> bool:
        """No uncovered violation and no unused allow-list entry."""
        return not self.violations and not self.unused_allowances

    def allow_list(self) -> list[str]:
        """The keys of every violation, allowed or not: the allow-list that would pass today."""
        return sorted({violation.key for violation in (*self.violations, *self.allowed)})

    def format(self) -> str:
        """A readable report naming each violation and the allow-list entry that would cover it."""
        lines = [
            f"API conformance -- violations: {len(self.violations)}, allowed: {len(self.allowed)}, "
            f"unused allow-list entries: {len(self.unused_allowances)}, checked: {self.checked}, exempt: {self.exempt}"
        ]
        for violation in self.violations:
            lines.append(f"  {violation.key}: {violation.message}")
        if self.unused_allowances:
            lines.append("  allow-list entries that match nothing, to remove:")
            lines.extend(f"    {entry!r}" for entry in self.unused_allowances)
        return "\n".join(lines)


def _resolve(schema: Any, schemas: dict[str, Any]) -> dict[str, Any]:
    """``schema`` with its ``$ref`` chain followed into the components."""
    for _ in range(_MAX_REF_HOPS):
        if not isinstance(schema, dict) or "$ref" not in schema:
            break
        schema = schemas.get(str(schema["$ref"]).rsplit("/", 1)[-1])
    return schema if isinstance(schema, dict) else {}


def _properties(schema: Any, schemas: dict[str, Any], hops: int = 0) -> set[str]:
    """Property names of an object schema, through ``$ref`` and ``allOf``."""
    resolved = _resolve(schema, schemas)
    names = set(resolved.get("properties") or {})
    if hops < _MAX_REF_HOPS:
        for member in resolved.get("allOf") or ():
            names |= _properties(member, schemas, hops + 1)
    return names


def _success_properties(operation: dict[str, Any], schemas: dict[str, Any]) -> set[str]:
    """Property names of the first 2xx JSON response."""
    for status, response in sorted((operation.get("responses") or {}).items()):
        if str(status).startswith("2") and isinstance(response, dict):
            content = (response.get("content") or {}).get("application/json") or {}
            return _properties(content.get("schema"), schemas)
    return set()


def _parameters(operation: dict[str, Any]) -> set[tuple[str, str]]:
    """``(location, lower-case name)`` for every parameter."""
    found: set[tuple[str, str]] = set()
    for parameter in operation.get("parameters") or ():
        if isinstance(parameter, dict):
            found.add((str(parameter.get("in", "")), str(parameter.get("name", "")).lower()))
    return found


def _extension_drift(actual: Any, expected: dict[str, Any]) -> str | None:
    """Why the spec's ``x-scalo`` is not the expected one, or None when it is."""
    if not isinstance(actual, dict):
        return f"no {EXTENSION}: wire the app with scalo.api.install(), or call annotate_openapi() on its spec"
    differing = sorted(key for key in {*actual, *expected} if actual.get(key) != expected.get(key))
    if not differing:
        return None
    return f"{EXTENSION} disagrees with the route on {differing}: it is written by annotate_openapi(), never by hand"


@dataclass(frozen=True, slots=True)
class _Expected:
    """What one route method should look like in the spec."""

    operation_id: str
    name: OperationName
    extension: dict[str, Any]


def _operation_problems(
    operation: dict[str, Any],
    expected: _Expected,
    context: RouteContext,
    hierarchy: Hierarchy,
    id_counts: Counter[Any],
    schemas: dict[str, Any],
) -> list[tuple[str, str]]:
    """``(rule, message)`` for every rule one operation breaks."""
    problems: list[tuple[str, str]] = []
    name, extension = expected.name, expected.extension
    operation_id = operation.get("operationId")
    params = _parameters(operation)

    if not isinstance(operation_id, str) or not operation_id:
        problems.append(("operation-id", f"no operationId: the hierarchy derives {expected.operation_id!r}"))
    elif not _OPERATION_ID.match(operation_id):
        problems.append(("operation-id", f"{operation_id!r} is not <root>.<child...>.<verb>"))
    elif operation_id != expected.operation_id:
        problems.append(
            (
                "operation-id",
                f"{operation_id!r} is not the derived {expected.operation_id!r}: build the app with "
                "generate_unique_id_function=hierarchy.unique_id and set no operation_id by hand",
            )
        )
    if isinstance(operation_id, str) and id_counts[operation_id] > 1:
        problems.append(("duplicate-operation-id", f"{operation_id!r} names {id_counts[operation_id]} operations"))
    if name.problems:
        problems.append(("hierarchy", "; ".join(name.problems)))
    if name.depth > hierarchy.max_depth:
        problems.append(("depth", f"{name.depth} resource levels, over the limit of {hierarchy.max_depth}"))
    drift = _extension_drift(operation.get(EXTENSION), extension)
    if drift:
        problems.append(("extension", drift))
    if context.response_model is None and context.status_code not in _NO_BODY_STATUS:
        problems.append(("response-model", "no response model: set response_model or annotate the return type"))
    if not (context.summary or context.description):
        problems.append(("summary", "neither a summary nor a docstring"))
    if "action" not in extension and not extension.get("public"):
        problems.append(
            (
                "permission",
                f"no {EXTENSION}.action and not public: guard it with a permission() dependency, "
                "or declare scalo_extra(public=True)",
            )
        )
    if name.verb == "list":
        missing = [key for key in ("page_size", "page_token") if ("query", key) not in params]
        if missing:
            problems.append(
                ("pagination", f"a list without the {' and '.join(missing)} query parameter: use ListParams")
            )
        if "next_page_token" not in _success_properties(operation, schemas):
            problems.append(("pagination", "a list whose response carries no next_page_token: answer a Page"))
    if not extension["read_only"]:
        if ("query", "dry_run") not in params:
            problems.append(("dry-run", "a mutation without the dry_run query parameter: take DryRun"))
        if name.method in _PRECONDITION_METHODS and ("header", "if-match") not in params:
            problems.append(("if-match", "a write without the If-Match header: take PreconditionHeaders"))
    return problems


def check_conformance(
    app: FastAPI,
    hierarchy: Hierarchy,
    *,
    allow: Iterable[str] = (),
    exempt: Iterable[str] = (),
    spec: dict[str, Any] | None = None,
) -> ConformanceReport:
    """Check every operation the app serves against the API conventions.

    Args:
        app: The application.
        hierarchy: The naming model the app is held to.
        allow: Patterns over violation keys (``"<rule> <METHOD> <path>"``) for
            violations accepted for now.
        exempt: Patterns over route paths the conventions do not apply to.
        spec: The spec to check, such as a committed copy. Defaults to ``app.openapi()``.

    Returns:
        The report. Its :attr:`~ConformanceReport.ok` is the pass condition.
    """
    spec = app.openapi() if spec is None else spec
    paths: dict[str, Any] = spec.get("paths") or {}
    schemas: dict[str, Any] = (spec.get("components") or {}).get("schemas") or {}
    allow_patterns = tuple(dict.fromkeys(allow))
    exempt_patterns = tuple(exempt)
    id_counts = Counter(
        operation.get("operationId")
        for item in paths.values()
        for method, operation in item.items()
        if method in _SPEC_METHODS and isinstance(operation, dict)
    )

    found: list[Violation] = []
    checked = exempted = 0
    for context in api_routes(app.routes):
        path = context.path_format or ""
        methods = sorted(context.methods or ())
        if any(fnmatchcase(path, pattern) for pattern in exempt_patterns):
            exempted += len(methods)
            continue
        declared = declared_extension(context.openapi_extra)
        verb = declared.get("verb")
        actions = route_actions(context)
        expected_id = hierarchy.unique_id(context)
        for method in methods:
            checked += 1
            operation = paths.get(path, {}).get(method.lower())
            if not isinstance(operation, dict):
                found.append(Violation("operation-id", method, path, None, "the spec carries no operation for it"))
                continue
            name = hierarchy.parse(path, method, verb=verb if isinstance(verb, str) else None)
            expected = _Expected(expected_id, name, operation_extension(name, declared, actions, hierarchy))
            operation_id = operation.get("operationId")
            for rule, message in _operation_problems(operation, expected, context, hierarchy, id_counts, schemas):
                found.append(
                    Violation(rule, method, path, operation_id if isinstance(operation_id, str) else None, message)
                )

    violations: list[Violation] = []
    allowed: list[Violation] = []
    used: set[str] = set()
    for violation in found:
        matched = [pattern for pattern in allow_patterns if fnmatchcase(violation.key, pattern)]
        used.update(matched)
        (allowed if matched else violations).append(violation)
    return ConformanceReport(
        violations=tuple(violations),
        allowed=tuple(allowed),
        unused_allowances=tuple(pattern for pattern in allow_patterns if pattern not in used),
        checked=checked,
        exempt=exempted,
    )


def assert_conformant(
    app: FastAPI,
    hierarchy: Hierarchy,
    *,
    allow: Iterable[str] = (),
    exempt: Iterable[str] = (),
    spec: dict[str, Any] | None = None,
    strict: bool = True,
) -> ConformanceReport:
    """Fail a test when the app breaks the conventions, for use under pytest.

    Args:
        app: The application.
        hierarchy: The naming model the app is held to.
        allow: Patterns over violation keys accepted for now.
        exempt: Patterns over route paths the conventions do not apply to.
        spec: The spec to check. Defaults to ``app.openapi()``.
        strict: Also fail on an allow-list entry that matches nothing.

    Returns:
        The report, when it passes.

    Raises:
        AssertionError: With the formatted report, on any uncovered violation,
            or on an unused allow-list entry when ``strict``.
    """
    report = check_conformance(app, hierarchy, allow=allow, exempt=exempt, spec=spec)
    if report.violations or (strict and report.unused_allowances):
        raise AssertionError(report.format())
    return report
