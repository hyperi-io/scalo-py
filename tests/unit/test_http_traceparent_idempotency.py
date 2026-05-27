#  Project:   hyperi-pylib
#  File:      tests/unit/test_http_traceparent_idempotency.py
#  Purpose:   Verify HttpClient injects traceparent + Idempotency-Key on retries
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""S7/S8 regression tests: the W3C traceparent header and an
Idempotency-Key passed to the client must ride along on every
attempt of a retried request. Without that, retries of POST/PATCH
silently double-submit and tracing context is lost on the second hop."""

from __future__ import annotations

import re
import uuid

import httpx
import pytest

from hyperi_pylib.http.client import AsyncHttpClient, HttpClient, new_idempotency_key


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


def test_new_idempotency_key_is_unique():
    keys = {new_idempotency_key() for _ in range(20)}
    assert len(keys) == 20  # all unique
    for k in keys:
        uuid.UUID(k)  # parses as a valid UUID
