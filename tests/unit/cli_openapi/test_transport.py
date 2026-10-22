#  Project:   scalo
#  File:      tests/unit/cli_openapi/test_transport.py
#  Purpose:   The stdlib and scalo.http transports against a real HTTP server on loopback
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Both transports, over real sockets: statuses, bodies, redirects, retries and refusals."""

import socket

import pytest
import stamina

from scalo.cli.openapi import ScaloHttpTransport, TransportError, UrllibTransport


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _send(transport, method: str, url: str, *, credentials=None, content=None):
    return transport.send(
        method, url, headers={"Accept": "application/json"}, credentials=credentials or {}, content=content, timeout=5
    )


@pytest.fixture(autouse=True)
def _no_backoff():
    """Retries happen, but without stamina's waits between them."""
    with stamina.set_testing(True, attempts=3, cap=True):
        yield


@pytest.fixture(params=["urllib", "scalo-http"])
def transport(request):
    return UrllibTransport() if request.param == "urllib" else ScaloHttpTransport(retries=3)


class TestBothTransports:
    """What every transport must do the same way."""

    def test_a_success_and_its_headers(self, transport, http_server):
        server = http_server()
        server.route("GET", "/thing", (200, {"Content-Type": "application/json", "ETag": '"abc"'}, b'{"ok": true}'))

        reply = _send(transport, "GET", f"{server.url}/thing")

        assert (reply.status, reply.ok, reply.json()) == (200, True, {"ok": True})
        assert reply.headers["etag"] == '"abc"'

    def test_an_error_status_is_an_answer_not_an_exception(self, transport, http_server):
        server = http_server()
        server.route("GET", "/thing", (404, {"Content-Type": "application/problem+json"}, b'{"status": 404}'))

        reply = _send(transport, "GET", f"{server.url}/thing")

        assert (reply.status, reply.ok, reply.json()) == (404, False, {"status": 404})

    def test_body_and_credentials_arrive(self, transport, http_server):
        server = http_server()
        server.route("POST", "/thing", (201, {}, b""))

        reply = _send(transport, "POST", f"{server.url}/thing", credentials={"X-API-Key": "k"}, content=b'{"a": 1}')

        assert reply.status == 201
        assert reply.json() is None
        assert server.seen[0]["body"] == b'{"a": 1}'
        assert server.seen[0]["headers"]["x-api-key"] == "k"

    def test_an_unreachable_api(self, transport):
        with pytest.raises(TransportError, match="could not reach"):
            _send(transport, "GET", f"http://127.0.0.1:{_closed_port()}/thing")


class TestUrllib:
    """The stdlib transport's own guarantees."""

    def test_credentials_never_follow_a_redirect(self, http_server):
        first, second = http_server(), http_server()
        first.route("GET", "/moved", (302, {"Location": f"{second.url}/landed"}, b""))
        second.route("GET", "/landed", (200, {}, b"{}"))

        reply = _send(UrllibTransport(), "GET", f"{first.url}/moved", credentials={"Authorization": "Bearer t"})

        assert reply.status == 200
        assert first.seen[0]["headers"]["authorization"] == "Bearer t"
        assert "authorization" not in second.seen[0]["headers"]
        assert second.seen[0]["headers"]["accept"] == "application/json"

    def test_only_http_urls_are_sent(self):
        with pytest.raises(ValueError, match="only http and https"):
            _send(UrllibTransport(), "GET", "file:///etc/hostname")


class TestScaloHttp:
    """The scalo.http transport retries reads and never writes."""

    def test_a_get_is_retried_after_a_server_error(self, http_server):
        server = http_server()
        server.route("GET", "/flaky", (503, {}, b""), (200, {}, b"{}"))

        reply = _send(ScaloHttpTransport(retries=3), "GET", f"{server.url}/flaky")

        assert reply.status == 200
        assert len(server.seen) == 2

    def test_a_post_is_sent_once(self, http_server):
        server = http_server()
        server.route("POST", "/flaky", (503, {}, b""), (200, {}, b"{}"))

        reply = _send(ScaloHttpTransport(retries=3), "POST", f"{server.url}/flaky", content=b"{}")

        assert reply.status == 503
        assert len(server.seen) == 1
