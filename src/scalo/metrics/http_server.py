#  Project:      scalo
#  File:         http_server.py
#  Purpose:      Server-side HTTP request metrics for ASGI apps
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Server-side HTTP request metrics for ASGI apps.

One histogram, ``http_server_request_duration_seconds``, labelled by method, full route
template and status code. Its count gives the request and error rates and its
buckets the latency percentiles. Over OTLP it exports as
``http.server.request.duration``.

fastapi 0.142+ records the same instrument, so pass ``"metrics": False`` in
``FastAPI(telemetry=...)`` or each request is counted twice.

Example:
    >>> app.add_middleware(HttpServerMetricsMiddleware, metrics=metrics_manager)
"""

import time
from collections.abc import Awaitable, Callable, Iterable, MutableMapping
from typing import Any

DURATION_METRIC = "http_server_request_duration_seconds"

# The OTel HTTP semantic-convention boundaries, plus 30 s and 60 s for slow admin calls.
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 30.0, 60.0)

# Probe and scrape traffic would otherwise dominate the request rate.
DEFAULT_SKIP_PATHS = frozenset({"/healthz", "/livez", "/metrics", "/readyz"})

# A request that matched no route, so a scan of random paths cannot mint one series per path.
UNMATCHED_ROUTE = "__unmatched__"

# A matched route whose full template cannot be named without a request value, so it never mints a series per value.
UNRESOLVED_ROUTE = "__unresolved__"

# A mount chain deeper than this is labelled UNRESOLVED_ROUTE rather than walked.
_MAX_MOUNT_DEPTH = 16

_KNOWN_METHODS = frozenset({"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"})

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


def _server_root(scope: Scope) -> str:
    """The root path the server set, before any mount extended it."""
    # A mount extends root_path, so the server's own root is the copy Starlette keeps in app_root_path.
    return str(scope.get("app_root_path", scope.get("root_path", "")) or "")


def _app_path(scope: Scope) -> str:
    """The request path below the server's root path, where the app's own templates start."""
    path = str(scope.get("path", ""))
    root = _server_root(scope=scope)
    if root and path.startswith(root + "/"):
        return path[len(root) :]
    return path


def _mounted_path(scope: Scope) -> str | None:
    """The request path text the mounts consumed, or None where root_path does not show it."""
    if "app_root_path" not in scope:
        return ""
    root = _server_root(scope=scope)
    mounted = str(scope.get("root_path") or "")
    return mounted[len(root) :] if mounted.startswith(root) else None


def _is_mount(route: Any) -> bool:
    """Whether ``route`` is a Starlette ``Mount``, which hands the rest of the path to the routes below it."""
    path_format = getattr(route, "path_format", None)
    has_tree = hasattr(route, "routes") and hasattr(route, "path_regex")
    return has_tree and isinstance(path_format, str) and path_format.endswith("/{path}")


def _mount_chain(scope: Scope, app_path: str, mounted: str) -> tuple[list[Any], dict[str, Any]] | None:
    """The mounts that consumed ``mounted``, walked from the router, with the values they matched.

    Each level takes the first mount whose pattern matches, as Starlette's router does. A
    mount it cannot see, such as one inside FastAPI's included-router wrapper, leaves the
    text unaccounted for, and the chain is None.
    """
    routes = getattr(scope.get("router"), "routes", None)
    remaining, consumed = app_path, 0
    chain: list[Any] = []
    values: dict[str, Any] = {}
    while consumed < len(mounted):
        if routes is None or len(chain) >= _MAX_MOUNT_DEPTH:
            return None
        mount = next((r for r in routes if _is_mount(r) and r.path_regex.match(remaining)), None)
        if mount is None:
            return None
        matched = mount.path_regex.match(remaining).groupdict()
        rest = "/" + matched.pop("path", "")
        text = remaining[: len(remaining) - len(rest)]
        if not mounted.startswith(text, consumed):
            return None
        try:
            values.update({name: mount.param_convertors[name].convert(raw) for name, raw in matched.items()})
        except KeyError, AttributeError, TypeError, ValueError, AssertionError:
            return None
        chain.append(mount)
        routes, remaining, consumed = getattr(mount, "routes", None), rest, consumed + len(text)
    return chain, values


def _render(route: Any, template: str, params: dict[str, Any]) -> str | None:
    """``route``'s own template with its matched values, popping each from ``params``, or None."""
    convertors = getattr(route, "param_convertors", None) or {}
    path_format = getattr(route, "path_format", None)
    rendered = path_format if isinstance(path_format, str) and path_format else template
    for name in [key for key in params if "{" + key + "}" in rendered]:
        try:
            text = convertors[name].to_string(params.pop(name))
        except KeyError, AttributeError, TypeError, ValueError, AssertionError:
            return None
        rendered = rendered.replace("{" + name + "}", text)
    return rendered


def _full_template(scope: Scope, route: Any, template: str) -> str | None:
    """The route's template from the app root, or None where it cannot be named without a value."""
    app_path, mounted = _app_path(scope=scope), _mounted_path(scope=scope)
    if mounted is None or not app_path.startswith(mounted):
        return None
    walked = _mount_chain(scope=scope, app_path=app_path, mounted=mounted) if mounted else ([], {})
    if walked is None:
        return None
    chain, mount_values = walked
    mount_template = "".join(str(mount.path) for mount in chain)
    params = dict(scope.get("path_params") or {})
    # A request with no route below its last mount is labelled by the mounts alone.
    ends_at_mount = _is_mount(route)
    if ends_at_mount and (not chain or chain[-1] is not route):
        return None
    rendered = "" if ends_at_mount else _render(route=route, template=template, params=params)
    if rendered is None:
        return None
    # Any other matched value must be a mount's: a router prefix parameter is a request value.
    if any(key not in mount_values or mount_values[key] != value for key, value in params.items()):
        return None
    if ends_at_mount:
        return mount_template
    route_path = app_path[len(mounted) :]
    if not route_path.endswith(rendered):
        return None
    between = route_path[: len(route_path) - len(rendered)]
    # A router prefix parameter named like a mount's can overwrite it with the same value.
    if between and any(str(value) in between for value in params.values()):
        return None
    return mount_template + between + template


def _route_template(scope: Scope) -> str:
    """The matched route's full template (``/api/items/{item_id}``), never the raw path.

    FastAPI matches an included router lazily, so the route on the scope carries only its
    own router's prefix. Mount paths come from the mounts' own templates, walked from the
    router, because a route parameter of the same name overwrites a mount's value on the
    scope. Router prefixes between the last mount and the route are read off the request
    path, as the part before the route rendered with its matched values.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str):
        return UNMATCHED_ROUTE
    label = _full_template(scope=scope, route=route, template=template)
    return UNRESOLVED_ROUTE if label is None else label


def _method(scope: Scope) -> str:
    """The request method, with anything non-standard folded into ``_OTHER``."""
    method = str(scope.get("method", "")).upper()
    return method if method in _KNOWN_METHODS else "_OTHER"


class HttpServerMetricsMiddleware:
    """
    Pure ASGI middleware recording one duration per HTTP request.

    Register it last so it is outermost and times the whole stack. The route
    template runs from the app root: the route FastAPI leaves on the scope, with
    the router prefixes and mount paths above it. A request no route matched
    records ``UNMATCHED_ROUTE``, and so does every request under a framework that
    leaves no route. One whose full template cannot be named without a request
    value records ``UNRESOLVED_ROUTE``: a parameter in an included router's prefix,
    a mount inside an included router, or a value its convertor rewrites.

    Args:
        app: The ASGI app to wrap.
        metrics: MetricsManager to register the histogram with.
        skip_paths: Request paths that are not recorded.
    """

    def __init__(
        self, app: Callable[..., Awaitable[None]], *, metrics: Any, skip_paths: Iterable[str] = DEFAULT_SKIP_PATHS
    ) -> None:
        self._app = app
        self._skip_paths = frozenset(skip_paths)
        self._duration = metrics.histogram(
            buckets=DURATION_BUCKETS,
            description="HTTP server request duration in seconds",
            labels=["method", "endpoint", "status_code"],
            name=DURATION_METRIC,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http") or (scope["path"] in self._skip_paths):
            await self._app(scope, receive, send)
            return

        # A handler that raises before responding is recorded as the 500 the server sends.
        status = {"code": 500}

        async def recording_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        started = time.perf_counter()
        try:
            await self._app(scope, receive, recording_send)
        finally:
            labelled = self._duration.labels(
                endpoint=_route_template(scope=scope),
                method=_method(scope=scope),
                status_code=str(status["code"]),
            )
            labelled.observe(time.perf_counter() - started)
