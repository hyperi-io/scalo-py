#  Project:   scalo
#  File:      tests/unit/test_http_retry_log_redaction.py
#  Purpose:   Retry instrumentation names the error class and status, never the request URL
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Retry instrumentation names the error class and status, never the request URL.

A real local HTTP server answers 503 on a path that carries a user id, so the
URL an ``HTTPStatusError`` repr would print holds a value that must not reach
the logs. stamina's own logging hook is installed explicitly, the hook it picks
when structlog is absent.
"""

import logging
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import stamina
from stamina.instrumentation import LoggingOnRetryHook, set_on_retry_hooks

from scalo.http import AsyncHttpClient, HttpClient

USER_ID = "sentinel-user-7f3a9c"

both_paths = pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(503 if self.path.startswith("/users/") else 404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def one_retry_logged_by_stamina() -> Iterator[None]:
    set_on_retry_hooks([LoggingOnRetryHook])
    with stamina.set_testing(True, attempts=2):
        yield
    set_on_retry_hooks(None)


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _get(base_url: str, path: str, *, use_async: bool) -> httpx.Response:
    if use_async:
        async with AsyncHttpClient(base_url=base_url, retries=2, crypto_profile=None) as client:
            return await client.get(path)
    with HttpClient(base_url=base_url, retries=2, crypto_profile=None) as client:
        return client.get(path)


def _retry_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "stamina" and r.getMessage() == "stamina.retry_scheduled"]


@both_paths
async def test_a_retried_5xx_logs_class_and_status_only(server, caplog, use_async):
    caplog.set_level(logging.WARNING, logger="stamina")

    with pytest.raises(httpx.HTTPStatusError) as caught:
        await _get(server, f"/users/{USER_ID}/manager", use_async=use_async)

    assert caught.value.response.status_code == 503
    [record] = _retry_records(caplog)
    assert getattr(record, "stamina.caused_by") == "HTTPStatusError(status=503)"
    assert USER_ID not in " ".join(str(v) for v in vars(record).values())


@both_paths
async def test_a_retried_transport_error_logs_class_only(caplog, use_async):
    caplog.set_level(logging.WARNING, logger="stamina")

    with pytest.raises(httpx.ConnectError):
        await _get(f"http://127.0.0.1:{_closed_port()}", f"/users/{USER_ID}/manager", use_async=use_async)

    [record] = _retry_records(caplog)
    assert getattr(record, "stamina.caused_by") == "ConnectError"


@both_paths
async def test_a_4xx_is_raised_at_once_without_a_retry(server, caplog, use_async):
    caplog.set_level(logging.WARNING, logger="stamina")

    with pytest.raises(httpx.HTTPStatusError) as caught:
        await _get(server, "/missing", use_async=use_async)

    assert caught.value.response.status_code == 404
    assert _retry_records(caplog) == []
