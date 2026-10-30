#  Project:   scalo
#  File:      tests/unit/test_http_traceparent_idempotency.py
#  Purpose:   Verify HttpClient injects traceparent + Idempotency-Key on retries
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""S7/S8 regression tests: the W3C traceparent header and an
Idempotency-Key passed to the client must ride along on every
attempt of a retried request. Without that, retries of POST/PATCH
silently double-submit and tracing context is lost on the second hop."""

from __future__ import annotations

import http.server
import re
import socket
import threading
import uuid

import httpx
import pytest
import stamina

from scalo.http.client import AsyncHttpClient, HttpClient, new_idempotency_key


def _flaky_transport(seen_headers: list[dict[str, str]]):
    """Mock httpx transport: fail once with 503, succeed second time.
    Records the headers seen on each attempt."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(503, content=b"upstream busy")
        return httpx.Response(200, content=b"ok")

    return httpx.MockTransport(handler)


def _ok_transport(seen_headers: list[dict[str, str]]):
    """Mock transport that succeeds first try (no retry path)."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        return httpx.Response(200, content=b"ok")

    return httpx.MockTransport(handler)


def test_traceparent_rides_every_retry():
    """Same traceparent on attempt 1 (fails) and attempt 2 (succeeds)."""
    seen: list[dict[str, str]] = []
    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    client = HttpClient(transport=_flaky_transport(seen))
    try:
        r = client.get("https://example.com/", traceparent=tp)
        assert r.status_code == 200
    finally:
        client.close()

    assert len(seen) == 2
    assert seen[0]["traceparent"] == tp
    assert seen[1]["traceparent"] == tp


def test_idempotency_key_rides_every_retry():
    seen: list[dict[str, str]] = []
    key = new_idempotency_key()
    assert re.match(r"^[0-9a-f-]{36}$", key)

    client = HttpClient(transport=_flaky_transport(seen))
    try:
        r = client.post("https://example.com/charge", idempotency_key=key, json={"amt": 100})
        assert r.status_code == 200
    finally:
        client.close()

    assert seen[0]["idempotency-key"] == key
    assert seen[1]["idempotency-key"] == key


def test_no_headers_when_not_requested():
    """Default behaviour unchanged: no traceparent/idempotency-key headers."""
    seen: list[dict[str, str]] = []
    client = HttpClient(transport=_ok_transport(seen))
    try:
        client.get("https://example.com/")
    finally:
        client.close()

    assert "traceparent" not in seen[0]
    assert "idempotency-key" not in seen[0]


@pytest.mark.asyncio
async def test_async_client_traceparent_rides_every_retry():
    seen: list[dict[str, str]] = []
    tp = "00-1111111111111111111111111111aaaa-2222222222222222-01"
    client = AsyncHttpClient(transport=_flaky_transport(seen))
    try:
        r = await client.get("https://example.com/", traceparent=tp)
        assert r.status_code == 200
    finally:
        await client.aclose()

    assert seen[0]["traceparent"] == tp
    assert seen[1]["traceparent"] == tp


class _ApplyThenFail(http.server.BaseHTTPRequestHandler):
    """Apply the request, then answer 503 (path /503) or drop the connection (path /drop)."""

    hits: list[str]

    def _handle(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.hits.append(self.command)
        if self.path == "/drop":
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.send_response(503)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # Names fixed by BaseHTTPRequestHandler's dispatch.
    def do_GET(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def apply_then_fail():
    """A real local server that applies every request and then fails it, recording each one it applied."""
    hits: list[str] = []
    handler = type("_Handler", (_ApplyThenFail,), {"hits": hits})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stamina.set_testing(True, attempts=3)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", hits
    finally:
        stamina.set_testing(False)
        server.shutdown()
        server.server_close()


_MUTATION_CASES = [
    pytest.param("POST", "/503", {}, {}, 1, id="post-503-not-retried"),
    pytest.param("PATCH", "/drop", {}, {}, 1, id="patch-dropped-not-retried"),
    pytest.param("POST", "/drop", {}, {"idempotency_key": "k-1"}, 3, id="post-with-key-retried"),
    pytest.param("PATCH", "/503", {}, {"headers": {"Idempotency-Key": "k-2"}}, 3, id="patch-with-key-header-retried"),
    pytest.param("POST", "/503", {"retry_non_idempotent": True}, {}, 3, id="post-opted-in-retried"),
    pytest.param("PUT", "/503", {}, {}, 3, id="put-replayable-retried"),
    pytest.param("GET", "/drop", {}, {}, 3, id="get-replayable-retried"),
]


@pytest.mark.parametrize(("method", "path", "client_kwargs", "request_kwargs", "want_hits"), _MUTATION_CASES)
def test_sync_client_resends_a_mutation_only_when_it_is_safe(
    apply_then_fail, method, path, client_kwargs, request_kwargs, want_hits
):
    base, hits = apply_then_fail
    with HttpClient(base_url=base, timeout=5.0, **client_kwargs) as client, pytest.raises(httpx.HTTPError):
        client._request(method, path, **request_kwargs)

    assert len(hits) == want_hits, f"the server applied the {method} {len(hits)} times"


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "client_kwargs", "request_kwargs", "want_hits"), _MUTATION_CASES)
async def test_async_client_resends_a_mutation_only_when_it_is_safe(
    apply_then_fail, method, path, client_kwargs, request_kwargs, want_hits
):
    base, hits = apply_then_fail
    async with AsyncHttpClient(base_url=base, timeout=5.0, **client_kwargs) as client:
        with pytest.raises(httpx.HTTPError):
            await client._request(method, path, **request_kwargs)

    assert len(hits) == want_hits, f"the server applied the {method} {len(hits)} times"


def test_new_idempotency_key_is_unique():
    keys = {new_idempotency_key() for _ in range(20)}
    assert len(keys) == 20  # all unique
    for k in keys:
        uuid.UUID(k)  # parses as a valid UUID
