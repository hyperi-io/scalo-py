#  Project:   scalo
#  File:      tests/common/fake_secret_backends.py
#  Purpose:   Local HTTP fakes of an OpenBao health endpoint and an AWS Secrets Manager endpoint
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Two HTTP servers on localhost that a real provider can be pointed at.

``running_fake_vault`` answers ``GET /v1/sys/health`` with the status a test sets, as a sealed or healthy
OpenBao does. ``running_fake_aws`` answers a Secrets Manager ``ListSecrets`` call with an empty list, or with
an AWS JSON error a test sets. Both speak plain HTTP, which is what the providers' ``address`` and
``endpoint_url`` settings allow for a local store.
"""

import http.server
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class FakeBackend:
    """The URL of a running fake, and the answer it gives now."""

    url: str
    status: int = 200
    error_code: str = "AccessDeniedException"
    error_message: str = "the caller may not list secrets"


@contextmanager
def _serving(handler: type[http.server.BaseHTTPRequestHandler], backend: FakeBackend) -> Iterator[FakeBackend]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    backend.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield backend
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _reply(handler: http.server.BaseHTTPRequestHandler, status: int, content_type: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


@contextmanager
def running_fake_vault() -> Iterator[FakeBackend]:
    """Serve ``/v1/sys/health`` on localhost, answering ``backend.status`` until the block exits."""
    backend = FakeBackend(url="")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            sealed = backend.status == 503
            _reply(self, backend.status, "application/json", {"initialized": True, "sealed": sealed})

        def log_message(self, format: str, *args: object) -> None:
            pass

    with _serving(Handler, backend):
        yield backend


@contextmanager
def running_fake_aws() -> Iterator[FakeBackend]:
    """Serve Secrets Manager on localhost: an empty ``ListSecrets`` at 200, else an AWS JSON error."""
    backend = FakeBackend(url="")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            content_type = "application/x-amz-json-1.1"
            if backend.status == 200:
                _reply(self, 200, content_type, {"SecretList": []})
            else:
                _reply(
                    self, backend.status, content_type, {"__type": backend.error_code, "Message": backend.error_message}
                )

        def log_message(self, format: str, *args: object) -> None:
            pass

    with _serving(Handler, backend):
        yield backend
