#  Project:      scalo
#  File:         http_server.py
#  Purpose:      Server-side HTTP request metrics for ASGI apps
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Server-side HTTP request metrics for ASGI apps.

One histogram, ``http_server_request_duration_seconds``, labelled by method, route
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

_KNOWN_METHODS = frozenset({"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"})

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


def _route_template(scope: Scope) -> str:
    """The matched route's template (``/items/{item_id}``), never the raw path."""
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else UNMATCHED_ROUTE


def _method(scope: Scope) -> str:
    """The request method, with anything non-standard folded into ``_OTHER``."""
    method = str(scope.get("method", "")).upper()
    return method if method in _KNOWN_METHODS else "_OTHER"


class HttpServerMetricsMiddleware:
    """
    Pure ASGI middleware recording one duration per HTTP request.

    Register it last so it is outermost and times the whole stack. The route
    template is the one FastAPI leaves on the scope once it has routed the
    request; under a framework that leaves none, every request records
    ``UNMATCHED_ROUTE``.

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
