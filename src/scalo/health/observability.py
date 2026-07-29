#  Project:   scalo
#  File:      src/scalo/health/observability.py
#  Purpose:   Dedicated observability HTTP server (health probes + metrics)
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Dedicated observability listener for health probes and metrics.

The container standard puts health and metrics on their own port, separate
from the port carrying user traffic, so that exposing the application never
exposes the operator surface. ``ServiceApp`` advertises that port
(``--metrics-addr``, default ``0.0.0.0:9090``); this module is what actually
answers on it.

Deliberately stdlib-only (``http.server``). Every scalo service gets the
observability surface regardless of which optional extras it installed --
pulling FastAPI or uvicorn in just to answer three fixed routes would make
the surface conditional on an extra, which is how it ends up inert. The
metrics manager is injected, so a service with no metrics extra still serves
health.

It runs on its own daemon thread and so does not care whether the service
itself is sync or async, and cannot block the event loop.

Paths served::

    GET /metrics        Prometheus text (404 when no metrics manager)
    GET /livez          liveness   (200 alive / 503 not)
    GET /readyz         readiness  (200 ready / 503 not)

These three are the whole surface. There are no aliases: a second path meaning
the same thing eventually stops meaning the same thing, and an alias that keeps
answering 200 hides a probe still pointed at the old name.

The ``*z`` suffix keeps probe routes visually distinct from application routes,
and scalo-rs serves the same names. ``/livez`` and ``/readyz`` follow the
Kubernetes API server and etcd convention.

There is no startup path. A ``startupProbe`` targets ``/livez`` -- Kubernetes
suspends liveness until the startup probe passes, so one path gives both a
generous boot budget and a tight liveness period without the two drifting.

Liveness answers "is this process wedged" and MUST NOT check dependencies:
restarting will not fix someone else's datastore, it just destroys warm state
mid-outage. Dependency checks belong in readiness.

Usage::

    from scalo.health import HealthManager, serve_observability

    health = HealthManager()
    server = serve_observability(health, metrics, "0.0.0.0:9090")
    health.set_started()
    health.set_ready()
    ...
    server.stop()
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .manager import HealthManager

DEFAULT_OBSERVABILITY_ADDR = "0.0.0.0:9090"
"""Default bind address -- matches ``ServiceApp``'s ``--metrics-addr``."""

LIVENESS_PATH = "/livez"
READINESS_PATH = "/readyz"
METRICS_PATH = "/metrics"

_JSON = "application/json"

REQUEST_TIMEOUT_SECONDS = 15.0
"""Per-connection socket timeout for the observability listener."""


def _log_exception(message: str) -> None:
    """Log a handler failure to the service log, never to the HTTP caller.

    Imported lazily so this module keeps working for a service that has not
    initialised the logger, and so importing ``scalo.health`` does not drag
    the logger in.
    """
    try:
        from scalo.logger import logger

        logger.exception(message)
    except Exception:  # pragma: no cover - logging must never break a probe
        pass


def parse_addr(addr: str, *, default_port: int = 9090) -> tuple[str, int]:
    """Split a ``host:port`` bind string into its parts.

    Accepts ``0.0.0.0:9090``, a bare ``:9090``, a bare host, and the
    bracketed IPv6 form ``[::]:9090``. A bare ``0`` port is preserved so
    callers (mainly tests) can bind an ephemeral port.

    Raises:
        ValueError: If the port is present but not an integer.
    """
    text = addr.strip()
    if not text:
        return "0.0.0.0", default_port

    if text.startswith("["):
        # [::]:9090 / [::1]:8080 -- bracketed IPv6 literal.
        close = text.find("]")
        if close == -1:
            raise ValueError(f"malformed IPv6 bind address: {addr!r}")
        host = text[1:close]
        rest = text[close + 1 :]
        if rest.startswith(":") and rest[1:]:
            return host, _port(rest[1:], addr)
        return host, default_port

    if ":" not in text:
        return text, default_port

    host, _, port_text = text.rpartition(":")
    if not port_text:
        return host or "0.0.0.0", default_port
    return host or "0.0.0.0", _port(port_text, addr)


def _port(text: str, addr: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"invalid port in bind address: {addr!r}") from None


class ObservabilityServer:
    """Small HTTP server answering health probes and metrics scrapes.

    Not started on construction -- call :meth:`start`, or use
    :func:`serve_observability` which does both.
    """

    def __init__(
        self,
        health: HealthManager | None = None,
        metrics: Any | None = None,
        addr: str = DEFAULT_OBSERVABILITY_ADDR,
    ) -> None:
        self.health = health if health is not None else HealthManager()
        self.metrics = metrics
        self.addr = addr
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ---- lifecycle ------------------------------------------------------

    def start(self) -> ObservabilityServer:
        """Bind the address and serve on a daemon thread.

        Raises:
            OSError: If the address cannot be bound. Deliberately NOT
                swallowed -- a service that silently fails to open its
                observability port is the exact defect this module exists
                to remove, and the operator would have no signal.
        """
        if self._httpd is not None:
            return self

        host, port = parse_addr(self.addr)
        handler = _make_handler(self.health, self.metrics)
        httpd = ThreadingHTTPServer((host, port), handler)
        httpd.daemon_threads = True

        thread = threading.Thread(
            target=httpd.serve_forever,
            name="scalo-observability",
            daemon=True,
        )
        thread.start()

        self._httpd = httpd
        self._thread = thread
        return self

    def stop(self, timeout: float = 5.0) -> None:
        """Shut the listener down and join the serving thread. Idempotent."""
        httpd, thread = self._httpd, self._thread
        self._httpd = self._thread = None
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        if thread is not None:
            thread.join(timeout=timeout)

    @property
    def bound_address(self) -> tuple[str, int] | None:
        """Actual ``(host, port)`` bound, or None when not started.

        Read the port from here rather than from ``addr`` when binding port
        0 -- that is the only way to learn the ephemeral port.
        """
        if self._httpd is None:
            return None
        host, port = self._httpd.server_address[:2]
        return str(host), int(port)

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    def __enter__(self) -> ObservabilityServer:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def serve_observability(
    health: HealthManager | None = None,
    metrics: Any | None = None,
    addr: str = DEFAULT_OBSERVABILITY_ADDR,
) -> ObservabilityServer:
    """Create and start an :class:`ObservabilityServer`.

    Pass the SAME ``HealthManager`` the application marks ready on, or its
    ``/readyz`` and the app's notion of readiness will drift apart.
    """
    return ObservabilityServer(health=health, metrics=metrics, addr=addr).start()


def _run(coro: Coroutine[Any, Any, dict]) -> dict:
    """Run a probe coroutine to completion on this request's thread.

    The probe responses have sync and async variants. We deliberately take
    the ASYNC ones: only they enforce ``per_check_timeout``, and an
    unbounded check is exactly what a probe endpoint must not have -- a
    hung readiness check would otherwise pin this handler thread forever
    while the kubelet keeps retrying.

    Each request already gets its own thread (``ThreadingHTTPServer``), so a
    fresh loop here is cheap and cannot touch the service's own loop.
    """
    return asyncio.run(coro)


def _make_handler(health: HealthManager, metrics: Any | None) -> type[BaseHTTPRequestHandler]:
    """Build a handler class bound to this server's health + metrics."""

    class _Handler(BaseHTTPRequestHandler):
        # Kubelet probes every few seconds; the default handler logs every
        # request to stderr, which would bury the service's own output.
        # Signature is fixed by BaseHTTPRequestHandler, including the name
        # `format` shadowing the builtin.
        def log_message(self, format: str, *args: Any) -> None:
            return

        server_version = "scalo-observability"
        sys_version = ""

        # Bound how long one connection can hold its thread. ThreadingHTTPServer
        # starts a thread per connection, so a client that opens sockets and
        # then dribbles (or never sends) would otherwise pin threads
        # indefinitely and starve real probes. Generous next to a kubelet's
        # timeoutSeconds, tight enough that a stalled peer cannot camp.
        timeout = REQUEST_TIMEOUT_SECONDS

        # Name is fixed by BaseHTTPRequestHandler's dispatch, not our choice.
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/") or "/"

            if path == METRICS_PATH:
                self._metrics()
            elif path == LIVENESS_PATH:
                self._probe(_run(health.liveness_response_async()), "alive")
            elif path == READINESS_PATH:
                self._probe(_run(health.readiness_response_async()), "ready")
            else:
                self._send(404, b'{"error":"not found"}', _JSON)

        def _metrics(self) -> None:
            if metrics is None:
                self._send(404, b'{"error":"metrics not configured"}', _JSON)
                return
            try:
                body = metrics.get_metrics()
                content_type = metrics.get_content_type()
            except Exception:
                # Generic body on purpose. This port is unauthenticated, and
                # an exception string can carry file paths, config values or
                # a connection string. The detail goes to the service log,
                # where it is scrubbed and access-controlled; the caller gets
                # only the status.
                _log_exception("failed to render metrics")
                self._send(500, b'{"error":"metrics unavailable"}', _JSON)
                return
            if isinstance(body, str):
                body = body.encode("utf-8")
            self._send(200, body, content_type)

        def _probe(self, payload: dict, ok_status: str) -> None:
            code = 200 if payload.get("status") == ok_status else 503
            self._send(code, json.dumps(payload).encode("utf-8"), _JSON)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            # Strip CR/LF before it goes in a header. The value comes from our
            # own metrics backend today, but a newline reaching a header is
            # response splitting, and this is the one place it could.
            self.send_header("Content-Type", content_type.replace("\r", "").replace("\n", ""))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _Handler


__all__ = [
    "DEFAULT_OBSERVABILITY_ADDR",
    "LIVENESS_PATH",
    "METRICS_PATH",
    "READINESS_PATH",
    "ObservabilityServer",
    "parse_addr",
    "serve_observability",
]
