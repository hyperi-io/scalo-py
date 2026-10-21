#  Project:   scalo
#  File:      tests/unit/mcp/test_server.py
#  Purpose:   scalo.mcp driven end to end by the MCP SDK's own client against a scalo.api service
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The MCP SDK's client against a scalo.api service with ``scalo.mcp`` mounted, over streamable HTTP.

Every request reaches the service through an ASGI transport, so the client, the
MCP endpoint and the in-process API calls all run as they would on a server.
"""

import base64
import copy
import hashlib
import hmac
import json
import logging

import httpx2
import pytest
from common.mcp_service import (
    BASE_URL,
    CRASH_SECRET,
    HIERARCHY,
    ISSUER,
    OTHER_WRITER,
    READER,
    TOOLS,
    WRITER,
    Peer,
    Recorder,
    RoundRobin,
    Source,
    Store,
    Verifier,
    build_app,
    http_client,
    mcp_client,
    running,
)
from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError

from scalo.api import EXTENSION, assert_conformant, etag_of
from scalo.logger import logger
from scalo.mcp import CREATE_ETAG, DEFAULT_TOOLS_TTL_MS, PROTOCOL_VERSION, McpSpecError, mount

_CHALLENGE = f'resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource/mcp"'


def _store(**sizes: int) -> Store:
    return Store(sources={name: Source(name=name, size=size) for name, size in sizes.items()})


async def _call(client, name: str, arguments: dict | None = None) -> tuple[dict, bool]:
    result = await client.call_tool(name, arguments or {})
    return result.structured_content, result.is_error


async def _list(http: httpx2.AsyncClient) -> httpx2.Response:
    return await _list_at(http, "/mcp")


async def _list_at(http: httpx2.AsyncClient, path: str) -> httpx2.Response:
    return await http.post(path, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


async def _raw_call(http: httpx2.AsyncClient, name: str, arguments: str) -> httpx2.Response:
    """A 2026-07-28 tools/call with ``arguments`` as raw JSON text, for input the SDK client will not encode."""
    payload = (
        f'{{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{{"name":"{name}","arguments":{arguments},'
        f'"_meta":{{"io.modelcontextprotocol/protocolVersion":"{PROTOCOL_VERSION}",'
        '"io.modelcontextprotocol/clientInfo":{"name":"raw","version":"1"},'
        '"io.modelcontextprotocol/clientCapabilities":{}}}}'
    )
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Mcp-Method": "tools/call",
        "Mcp-Name": name,
    }
    return await http.post("/mcp", content=payload, headers=headers)


def _alpha_apply(etag: str) -> str:
    """The request ``svc_sources_apply`` sends for ``alpha`` at size 5, in the form a preview token covers."""
    return json.dumps(
        [etag, "PUT", "/api/v1/sources/alpha", {}, {}, {"size": 5}],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class TestToolList:
    """The tools are exactly the operations that opt in, in an order every replica agrees on."""

    async def test_the_list_is_exactly_the_opt_ins_sorted_by_name(self):
        app, _ = build_app(_store())
        opted_in = {
            operation[EXTENSION]["mcp"]["tool"]
            for item in app.openapi()["paths"].values()
            for operation in item.values()
            if "mcp" in operation[EXTENSION]
        }

        async with running(app), mcp_client(app) as client:
            listed = [tool.name for tool in (await client.list_tools()).tools]

        assert listed == TOOLS
        assert set(listed) == opted_in

    async def test_operations_that_did_not_opt_in_are_not_tools(self):
        app, server = build_app(_store())

        async with running(app):
            names = {tool.name for tool in server.tools}

        assert "svc_sources_preview" not in names
        assert "svc_deployment_get" not in names

    async def test_every_replica_lists_the_same_tools_in_the_same_order(self):
        store = _store()
        first, _ = build_app(store)
        second, _ = build_app(store)

        async with running(first, second), mcp_client(first) as one, mcp_client(second) as two:
            listings = [(await client.list_tools()).model_dump() for client in (one, two)]

        assert listings[0]["tools"] == listings[1]["tools"]

    async def test_the_list_is_cacheable_for_every_caller(self):
        app, _ = build_app(_store())

        async with running(app), mcp_client(app) as client:
            listing = await client.list_tools()

        assert listing.ttl_ms == DEFAULT_TOOLS_TTL_MS
        assert listing.cache_scope == "public"
        assert listing.next_cursor is None


class TestStateless:
    """The 2026-07-28 revision: no session, no initialize, any replica answers any request."""

    async def test_discover_negotiates_2026_07_28_with_no_initialize_and_no_session(self):
        app, _ = build_app(_store(alpha=1))
        recorder = Recorder(app)

        async with running(app), mcp_client(recorder) as client:
            await client.list_tools()
            await client.call_tool("svc_sources_get", {"source": "alpha"})
            version = client.protocol_version

        methods = [exchange.rpc for exchange in recorder.exchanges]
        assert version == PROTOCOL_VERSION
        assert methods == ["server/discover", "tools/list", "tools/call"]
        assert all("mcp-session-id" not in exchange.headers for exchange in recorder.exchanges)

    async def test_two_replicas_with_no_session_affinity_serve_one_client(self):
        store = _store(alpha=1)
        first, _ = build_app(store)
        second, _ = build_app(store)
        balancer = RoundRobin(first, second)

        async with running(first, second), mcp_client(balancer) as client:
            listed = [tool.name for tool in (await client.list_tools()).tools]
            preview, _ = await _call(client, "svc_sources_apply", {"source": "alpha", "body": {"size": 2}})
            commit, failed = await _call(
                client,
                "svc_sources_apply",
                {"source": "alpha", "body": {"size": 2}, "dry_run": False, "preview_token": preview["preview_token"]},
            )

        assert listed == TOOLS
        assert not failed
        assert commit["status"] == 200
        assert store.sources["alpha"].size == 2
        # discover, list, preview and commit alternate, so the commit reached the other replica from its preview.
        assert balancer.served == [0, 1, 0, 1]

    async def test_a_handshake_era_client_is_served_without_a_session(self):
        store = _store()
        first, _ = build_app(store)
        second, _ = build_app(store)
        recorder = Recorder(RoundRobin(first, second))

        async with running(first, second), mcp_client(recorder, mode="legacy") as client:
            listed = [tool.name for tool in (await client.list_tools()).tools]
            _, failed = await _call(client, "svc_sources_list")

        assert listed == TOOLS
        assert not failed
        assert store.seen == [("GET", "/api/v1/sources", f"Bearer {WRITER}")]
        assert "initialize" in [exchange.rpc for exchange in recorder.exchanges]
        assert all("mcp-session-id" not in exchange.headers for exchange in recorder.exchanges)


class TestInProcessCalls:
    """A call runs inside the process, through the app, as the caller."""

    async def test_a_call_runs_in_process_with_the_callers_own_token(self):
        store = _store(alpha=1)
        app, _ = build_app(store)
        recorder = Recorder(app)

        async with running(app), mcp_client(recorder, READER) as client:
            answer, failed = await _call(client, "svc_sources_get", {"source": "alpha"})

        assert not failed
        assert answer["body"] == {"name": "alpha", "size": 1}
        assert {exchange.path for exchange in recorder.exchanges} == {"/mcp"}
        assert store.seen == [("GET", "/api/v1/sources/alpha", f"Bearer {READER}")]

    async def test_a_caller_without_the_permission_gets_the_apps_own_403(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app, READER) as reader:
            preview, failed = await _call(reader, "svc_sources_apply", {"source": "alpha", "body": {"size": 9}})

        assert failed
        assert preview["status"] == 403
        assert preview["body"]["code"] == "forbidden"
        assert "preview_token" not in preview
        assert store.sources["alpha"].size == 1

    async def test_a_request_with_no_token_gets_the_rfc_9728_challenge(self):
        app, _ = build_app(_store())

        async with running(app), http_client(app, token=None) as http:
            response = await _list(http)

        assert response.status_code == 401
        challenge = response.headers["www-authenticate"]
        assert challenge.startswith("Bearer ")
        assert _CHALLENGE in challenge
        assert 'scope="svc"' in challenge
        assert "error=" not in challenge
        assert response.json()["code"] == "unauthenticated"

    async def test_the_app_sees_the_mcp_requests_peer_address(self):
        store = _store()
        app, _ = build_app(store)

        async with running(app), mcp_client(Peer(app, ("10.1.2.3", 4567))) as client:
            await _call(client, "svc_sources_list")

        assert store.peers == [("10.1.2.3", 4567)]

    async def test_an_mcp_request_with_no_peer_reaches_the_app_with_no_peer(self):
        store = _store()
        app, _ = build_app(store)

        async with running(app), mcp_client(Peer(app, None)) as client:
            await _call(client, "svc_sources_list")

        assert store.peers == [None]


class TestTokenVerifier:
    """With a verifier, every request's token is checked before any MCP handling."""

    async def test_an_invalid_token_gets_401_before_any_mcp_handling(self):
        store = _store()
        verifier = Verifier()
        app, _ = build_app(store, token_verifier=verifier)

        async with running(app), http_client(app, token="forged-token") as http:
            response = await _list(http)

        assert response.status_code == 401
        challenge = response.headers["www-authenticate"]
        assert 'error="invalid_token"' in challenge
        assert _CHALLENGE in challenge
        assert verifier.checked == ["forged-token"]
        assert store.seen == []

    async def test_an_expired_token_gets_401(self):
        app, _ = build_app(_store(), token_verifier=Verifier(expired=True))

        async with running(app), http_client(app, token=WRITER) as http:
            response = await _list(http)

        assert response.status_code == 401
        assert 'error="invalid_token"' in response.headers["www-authenticate"]

    async def test_a_token_the_verifier_accepts_reaches_the_tools(self):
        verifier = Verifier()
        app, _ = build_app(_store(alpha=1), token_verifier=verifier)

        async with running(app), mcp_client(app, READER) as client:
            listed = [tool.name for tool in (await client.list_tools()).tools]
            answer, failed = await _call(client, "svc_sources_get", {"source": "alpha"})

        assert listed == TOOLS
        assert not failed
        assert answer["body"] == {"name": "alpha", "size": 1}
        assert set(verifier.checked) == {READER}

    def test_a_verifier_needs_an_issuer(self):
        with pytest.raises(ValueError, match="token_verifier needs an issuer"):
            mount(FastAPI(), token_verifier=Verifier())


class TestAppUnauthorised:
    """The app's own 401 on a tool call becomes the endpoint's HTTP 401 and challenge."""

    async def test_a_token_the_app_refuses_gets_http_401_and_the_challenge(self):
        store = _store()
        app, _ = build_app(store)
        recorder = Recorder(app)

        async with running(app), mcp_client(recorder, "unknown-token") as client:
            with pytest.raises(MCPError):
                await client.call_tool("svc_sources_list", {})

        last = recorder.exchanges[-1]
        assert last.rpc == "tools/call"
        assert last.status == 401
        assert 'error="invalid_token"' in last.headers["www-authenticate"]
        assert _CHALLENGE in last.headers["www-authenticate"]
        assert store.seen == [("GET", "/api/v1/sources", "Bearer unknown-token")]

    async def test_without_an_issuer_the_apps_401_gets_http_401_and_a_bare_challenge(self):
        store = _store()
        app, _ = build_app(store, issuer=None)
        recorder = Recorder(app)

        async with running(app), mcp_client(recorder, "unknown-token") as client:
            with pytest.raises(MCPError):
                await client.call_tool("svc_sources_list", {})

        last = recorder.exchanges[-1]
        assert last.rpc == "tools/call"
        assert last.status == 401
        assert last.headers["www-authenticate"] == "Bearer"
        assert store.seen == [("GET", "/api/v1/sources", "Bearer unknown-token")]

    async def test_the_apps_403_stays_a_tool_error(self):
        app, _ = build_app(_store(alpha=1))
        recorder = Recorder(app)

        async with running(app), mcp_client(recorder, READER) as client:
            answer, failed = await _call(client, "svc_sources_delete", {"source": "alpha"})

        assert failed
        assert answer["status"] == 403
        assert recorder.exchanges[-1].status == 200


class TestOrigin:
    """A browser origin that is not allowed is refused, against DNS rebinding."""

    async def test_an_origin_that_is_not_allowed_gets_403(self):
        store = _store()
        app, _ = build_app(store)

        async with running(app), http_client(app, headers={"Origin": "https://evil.example"}) as http:
            response = await _list(http)

        assert response.status_code == 403
        assert response.json()["code"] == "origin_not_allowed"
        assert store.seen == []

    async def test_an_allowed_origin_is_served(self):
        app, _ = build_app(_store(), allowed_origins=["https://console.example.com", "http://localhost:*"])

        for origin in ("https://console.example.com", "HTTP://LOCALHOST:5173", "http://localhost"):
            async with running(app), mcp_client(app, headers={"Origin": origin}) as client:
                listed = [tool.name for tool in (await client.list_tools()).tools]
            assert listed == TOOLS, origin

    async def test_the_sdks_settings_add_their_origins_and_check_the_host(self):
        settings = TransportSecuritySettings(
            allowed_hosts=["svc.example.com"], allowed_origins=["https://console.example.com"]
        )
        app, server = build_app(_store(), security_settings=settings)

        async with running(app), http_client(app, headers={"Origin": "https://console.example.com"}) as http:
            response = await _list(http)

        assert server.allowed_origins == frozenset({"https://console.example.com"})
        assert response.status_code == 421

    def test_an_allowed_origin_must_be_an_origin(self):
        with pytest.raises(ValueError, match="allowed origin"):
            mount(FastAPI(), allowed_origins=["https://console.example.com/app"])

    @pytest.mark.parametrize(
        "origin",
        ["http://localhost:3000.evil.com", "http://localhost:", "http://localhost:3000/", "http://localhost.evil.com"],
    )
    async def test_a_port_wildcard_matches_the_host_and_a_port_only(self, origin):
        store = _store()
        app, _ = build_app(store, allowed_origins=["http://localhost:*"])

        async with running(app), http_client(app, headers={"Origin": origin}) as http:
            response = await _list(http)

        assert response.status_code == 403
        assert store.seen == []

    async def test_the_metadata_route_refuses_a_host_the_sdks_settings_do_not_allow(self):
        settings = TransportSecuritySettings(allowed_hosts=["svc.example.com"])
        app, _ = build_app(_store(), security_settings=settings)

        async with running(app), http_client(app, token=None) as http:
            response = await http.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 421

    async def test_the_metadata_route_refuses_an_origin_that_is_not_allowed(self):
        app, _ = build_app(_store())

        async with running(app), http_client(app, token=None, headers={"Origin": "https://evil.example"}) as http:
            response = await http.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 403
        assert response.json()["code"] == "origin_not_allowed"


class TestWrites:
    """A write previews by default, and commits only the request its preview named."""

    async def test_a_write_previews_by_default_and_changes_nothing(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            preview, failed = await _call(client, "svc_sources_apply", {"source": "alpha", "body": {"size": 5}})

        assert not failed
        assert preview["dry_run"] is True
        assert preview["etag"] == etag_of(Source(name="alpha", size=1))
        assert preview["preview_token"]
        assert preview["body"]["before"] == {"name": "alpha", "size": 1}
        assert preview["body"]["after"] == {"name": "alpha", "size": 5}
        assert "dry_run=false" in preview["next"]
        assert store.sources["alpha"].size == 1

    async def test_a_commit_without_the_preview_token_is_refused_before_the_api(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(
                client, "svc_sources_apply", {"source": "alpha", "body": {"size": 5}, "dry_run": False}
            )

        assert failed
        assert "dry_run=true first" in answer["error"]
        assert store.sources["alpha"].size == 1
        assert store.seen == []

    async def test_a_commit_with_the_previews_token_lands(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            preview, _ = await _call(client, "svc_sources_apply", {"source": "alpha", "body": {"size": 5}})
            commit, failed = await _call(
                client,
                "svc_sources_apply",
                {"source": "alpha", "body": {"size": 5}, "dry_run": False, "preview_token": preview["preview_token"]},
            )

        assert not failed
        assert commit == {
            "status": 200,
            "dry_run": False,
            "body": {"dry_run": False, "before": {"name": "alpha", "size": 1}, "after": {"name": "alpha", "size": 5}},
            "etag": etag_of(Source(name="alpha", size=5)),
        }
        assert store.sources["alpha"].size == 5

    @pytest.mark.parametrize(
        "changed",
        [{"body": {"size": 9}}, {"source": "beta"}],
        ids=["another-body", "another-resource"],
    )
    async def test_a_commit_that_differs_from_its_preview_is_refused_with_412(self, changed):
        store = _store(alpha=1, beta=1)
        app, _ = build_app(store)
        previewed = {"source": "alpha", "body": {"size": 5}}

        async with running(app), mcp_client(app) as client:
            preview, _ = await _call(client, "svc_sources_apply", previewed)
            writes_before = list(store.seen)
            commit, failed = await _call(
                client,
                "svc_sources_apply",
                {**previewed, **changed, "dry_run": False, "preview_token": preview["preview_token"]},
            )

        assert failed
        assert commit["status"] == 412
        assert commit["body"]["code"] == "preview_mismatch"
        assert store.seen == writes_before
        assert (store.sources["alpha"].size, store.sources["beta"].size) == (1, 1)

    async def test_a_token_minted_under_one_authorization_is_refused_under_another(self):
        store = _store(alpha=1)
        app, _ = build_app(store)
        arguments = {"source": "alpha", "body": {"size": 5}}

        async with running(app), mcp_client(app, WRITER) as writer, mcp_client(app, OTHER_WRITER) as other:
            preview, _ = await _call(writer, "svc_sources_apply", arguments)
            writes_before = list(store.seen)
            commit, failed = await _call(
                other, "svc_sources_apply", {**arguments, "dry_run": False, "preview_token": preview["preview_token"]}
            )

        assert failed
        assert commit["status"] == 412
        assert commit["body"]["code"] == "preview_mismatch"
        assert store.seen == writes_before
        assert store.sources["alpha"].size == 1
        assert WRITER not in str((preview, commit))

    async def test_a_token_recomputed_without_the_key_is_refused(self):
        store = _store(alpha=1)
        app, _ = build_app(store)
        etag = etag_of(store.sources["alpha"])
        digest = hashlib.sha256(_alpha_apply(etag).encode()).digest()
        forged = f"{_b64url(etag.encode())}.{_b64url(digest)}"
        arguments = {"source": "alpha", "body": {"size": 5}, "dry_run": False, "preview_token": forged}

        async with running(app), mcp_client(app, WRITER) as client:
            commit, failed = await _call(client, "svc_sources_apply", arguments)

        assert failed
        assert commit["status"] == 412
        assert commit["body"]["code"] == "preview_mismatch"
        assert store.seen == []
        assert store.sources["alpha"].size == 1

    async def test_a_commit_with_no_authorization_is_refused_before_the_api(self):
        store = _store(alpha=1)
        app, _ = build_app(store, issuer=None)
        etag = etag_of(store.sources["alpha"])
        # An HMAC with an empty key is as computable as a plain hash.
        digest = hmac.new(b"", _alpha_apply(etag).encode(), hashlib.sha256).digest()
        forged = f"{_b64url(etag.encode())}.{_b64url(digest)}"
        arguments = {"source": "alpha", "body": {"size": 5}, "dry_run": False, "preview_token": forged}

        async with running(app), mcp_client(app, token=None) as client:
            commit, failed = await _call(client, "svc_sources_apply", arguments)

        assert failed
        assert "Authorization" in commit["error"]
        assert store.seen == []
        assert store.sources["alpha"].size == 1

    async def test_a_preview_with_no_authorization_still_reaches_the_app(self):
        store = _store(alpha=1)
        app, _ = build_app(store, issuer=None)

        async with running(app), mcp_client(app, token=None) as client:
            with pytest.raises(MCPError):
                await client.call_tool("svc_sources_apply", {"source": "alpha", "body": {"size": 5}})

        assert store.seen == [("GET", "/api/v1/sources/alpha", "")]

    async def test_a_stale_etag_gets_412_and_the_other_write_survives(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            preview, _ = await _call(client, "svc_sources_apply", {"source": "alpha", "body": {"size": 5}})
            async with http_client(app) as http:
                other = await http.put("/api/v1/sources/alpha", json={"size": 7}, headers={"If-Match": preview["etag"]})
            commit, failed = await _call(
                client,
                "svc_sources_apply",
                {"source": "alpha", "body": {"size": 5}, "dry_run": False, "preview_token": preview["preview_token"]},
            )

        assert other.status_code == 200
        assert failed
        assert commit["status"] == 412
        assert commit["body"]["code"] == "etag_mismatch"
        assert store.sources["alpha"].size == 7

    async def test_a_missing_resource_previews_as_a_create_that_commits_once(self):
        store = _store()
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            preview, _ = await _call(client, "svc_sources_apply", {"source": "beta", "body": {"size": 3}})
            arguments = {
                "source": "beta",
                "body": {"size": 3},
                "dry_run": False,
                "preview_token": preview["preview_token"],
            }
            created, created_failed = await _call(client, "svc_sources_apply", arguments)
            again, again_failed = await _call(client, "svc_sources_apply", arguments)

        assert preview["etag"] == CREATE_ETAG
        assert preview["body"]["before"] is None
        assert not created_failed
        assert created["status"] == 200
        assert again_failed
        assert again["status"] == 412
        assert again["body"]["code"] == "resource_exists"
        assert store.sources["beta"].size == 3

    async def test_a_delete_previews_then_commits_against_the_etag(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            preview, _ = await _call(client, "svc_sources_delete", {"source": "alpha"})
            kept = "alpha" in store.sources
            commit, failed = await _call(
                client,
                "svc_sources_delete",
                {"source": "alpha", "dry_run": False, "preview_token": preview["preview_token"]},
            )

        assert kept
        assert preview["dry_run"] is True
        assert not failed
        assert commit["status"] == 200
        assert "alpha" not in store.sources

    async def test_a_delete_of_a_missing_resource_answers_the_apps_404(self):
        app, _ = build_app(_store())

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_sources_delete", {"source": "ghost"})

        assert failed
        assert answer["status"] == 404
        assert answer["dry_run"] is True
        assert "preview_token" not in answer

    async def test_a_write_without_if_match_commits_with_its_preview_token(self):
        app, _ = build_app(_store(alpha=1))

        async with running(app), mcp_client(app) as client:
            preview, _ = await _call(client, "svc_sources_deploy", {"source": "alpha"})
            commit, failed = await _call(
                client,
                "svc_sources_deploy",
                {"source": "alpha", "dry_run": False, "preview_token": preview["preview_token"]},
            )

        assert "etag" not in preview
        assert preview["body"]["dry_run"] is True
        assert not failed
        assert commit["body"] == {"operation": "operations/deploy-alpha", "dry_run": False}


class TestAppFailures:
    """An exception in the app is the app's own 500, logged once, never the MCP layer's failure."""

    @pytest.fixture
    def scalo_errors(self):
        messages: list[str] = []
        handler = logger.add(lambda message: messages.append(message.record["message"]), level="ERROR")
        yield messages
        logger.remove(handler)

    async def test_an_unhandled_exception_is_a_tool_error_carrying_the_apps_500(self, scalo_errors, caplog):
        app, _ = build_app(_store())

        with caplog.at_level(logging.ERROR, logger="mcp"):
            async with running(app), mcp_client(app) as client:
                answer, failed = await _call(client, "svc_faults_get", {"fault": "crash"})

        assert failed
        assert answer["status"] == 500
        assert (answer["body"]["status"], answer["body"]["title"]) == (500, "Internal Server Error")
        assert CRASH_SECRET not in str(answer)
        assert scalo_errors == ["Unhandled exception"]
        assert [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR] == []

    async def test_an_app_timeout_error_is_not_the_calls_timeout(self):
        app, _ = build_app(_store())

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_faults_get", {"fault": "timeout"})

        assert failed
        assert answer["status"] == 500
        assert "error" not in answer

    async def test_an_app_that_leaves_exceptions_to_the_server_still_logs_one(self, scalo_errors):
        app, _ = build_app(_store(), catch_unhandled=False)

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_faults_get", {"fault": "crash"})

        assert failed
        assert (answer["status"], answer["body"]) == (500, "Internal Server Error")
        assert scalo_errors == ["Unhandled exception in an MCP tool call"]


class TestAnnotations:
    """The hints a client reads before it calls."""

    @pytest.fixture
    async def tools(self) -> dict:
        app, _ = build_app(_store())
        async with running(app), mcp_client(app) as client:
            return {tool.name: tool for tool in (await client.list_tools()).tools}

    async def test_a_delete_is_destructive(self, tools):
        assert tools["svc_sources_delete"].annotations.destructive_hint is True
        assert tools["svc_sources_delete"].annotations.read_only_hint is False

    async def test_every_get_is_read_only(self, tools):
        for name in ("svc_sources_list", "svc_sources_get", "svc_delays_get"):
            assert tools[name].annotations.read_only_hint is True, name
            assert tools[name].annotations.destructive_hint is False, name

    async def test_an_apply_writes_but_does_not_destroy(self, tools):
        hints = tools["svc_sources_apply"].annotations
        assert (hints.read_only_hint, hints.destructive_hint, hints.idempotent_hint) == (False, False, True)
        assert tools["svc_sources_deploy"].annotations.idempotent_hint is False

    async def test_a_write_says_how_it_previews_and_a_task_how_it_answers(self, tools):
        assert "dry_run=false and the preview_token the preview returned" in tools["svc_sources_apply"].description
        assert "operation to poll" in tools["svc_sources_deploy"].description
        assert tools["svc_sources_get"].title == "Get Source"
        assert tools["svc_sources_get"].description == "Get a source."


class TestProtectedResourceMetadata:
    """RFC 9728 metadata names the issuer whose tokens the app accepts."""

    async def test_the_metadata_names_the_issuer(self):
        app, _ = build_app(_store())

        async with running(app), http_client(app, token=None) as http:
            response = await http.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 200
        assert response.json() == {
            "resource": f"{BASE_URL}/mcp",
            "authorization_servers": [ISSUER],
            "scopes_supported": ["svc"],
            "bearer_methods_supported": ["header"],
            "resource_name": "svc",
        }

    async def test_there_is_no_metadata_at_the_root_for_a_resource_with_a_path(self):
        app, _ = build_app(_store())

        async with running(app), http_client(app, token=None) as http:
            response = await http.get("/.well-known/oauth-protected-resource")

        assert response.status_code == 404

    async def test_a_resource_read_from_the_request_is_never_cached_for_another_host(self):
        app, _ = build_app(_store())

        async with running(app), http_client(app, token=None) as http:
            response = await http.get("/.well-known/oauth-protected-resource/mcp")

        assert response.headers["cache-control"].startswith("private")
        assert response.headers["vary"] == "Host"

    async def test_a_configured_resource_url_is_the_resource(self):
        app, _ = build_app(_store(), resource_url="https://svc.example.com/mcp")

        async with running(app), http_client(app, token=None) as http:
            metadata = await http.get("/.well-known/oauth-protected-resource/mcp")
            challenge = (await http.post("/mcp", json={})).headers["www-authenticate"]

        assert metadata.json()["resource"] == "https://svc.example.com/mcp"
        assert metadata.headers["cache-control"] == "public, max-age=3600"
        assert 'resource_metadata="https://svc.example.com/.well-known/oauth-protected-resource/mcp"' in challenge

    async def test_behind_a_path_prefix_the_challenge_points_at_the_origin_and_the_app_serves_below_the_prefix(self):
        app, _ = build_app(_store())
        transport = httpx2.ASGITransport(app=app, root_path="/tenant")

        async with running(app), httpx2.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            challenge = (await _list_at(http, "/tenant/mcp")).headers["www-authenticate"]
            served = await http.get("/tenant/.well-known/oauth-protected-resource/mcp")

        assert f'resource_metadata="{BASE_URL}/.well-known/oauth-protected-resource/tenant/mcp"' in challenge
        assert served.json()["resource"] == f"{BASE_URL}/tenant/mcp"

    async def test_without_an_issuer_there_is_no_metadata_and_no_challenge(self):
        app, _ = build_app(_store(), issuer=None)

        async with running(app), http_client(app, token=None) as http:
            metadata = await http.get("/.well-known/oauth-protected-resource/mcp")
        async with running(app), mcp_client(app, token=None) as client:
            listed = [tool.name for tool in (await client.list_tools()).tools]

        assert metadata.status_code == 404
        assert listed == TOOLS

    def test_the_mcp_routes_stay_out_of_the_spec(self):
        app, _ = build_app(_store())

        paths = app.openapi()["paths"]

        assert not any(path.startswith(("/mcp", "/.well-known")) for path in paths)
        assert_conformant(app, HIERARCHY)


class TestArguments:
    """Arguments are checked before any request reaches the API."""

    async def test_an_argument_of_the_wrong_type_never_reaches_the_api(self):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_sources_apply", {"source": "alpha", "body": {"size": "big"}})

        assert failed
        assert answer["error"].startswith("invalid argument body.size")
        assert store.seen == []

    async def test_an_argument_the_tool_does_not_take_is_refused(self):
        app, _ = build_app(_store(alpha=1))

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_sources_get", {"source": "alpha", "verbose": True})

        assert failed
        assert "verbose" in answer["error"]

    @pytest.mark.parametrize("value", ["alpha/rules", "..", "."])
    async def test_a_path_argument_cannot_reach_another_route(self, value):
        store = _store(alpha=1)
        app, _ = build_app(store)

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(
                client, "svc_sources_delete", {"source": value, "dry_run": False, "preview_token": "x.y"}
            )

        assert failed
        assert "one path segment" in answer["error"]
        assert store.seen == []

    async def test_a_preview_token_cannot_smuggle_a_header(self):
        store = _store(alpha=1)
        app, _ = build_app(store)
        smuggled = _b64url(b'"x"\r\nX-Role: admin')
        arguments = {"source": "alpha", "body": {"size": 2}, "dry_run": False, "preview_token": f"{smuggled}.AAAA"}

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_sources_apply", arguments)

        assert failed
        assert "control characters" in answer["error"]
        assert store.seen == []

    async def test_a_preview_token_that_is_not_one_is_refused(self):
        store = _store(alpha=1)
        app, _ = build_app(store)
        arguments = {"source": "alpha", "body": {"size": 2}, "dry_run": False, "preview_token": "no-separator"}

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_sources_apply", arguments)

        assert failed
        assert "not one a dry run returned" in answer["error"]
        assert store.seen == []

    async def test_a_lone_surrogate_in_an_argument_is_a_tool_error_naming_it(self, caplog):
        store = _store(alpha=1)
        app, _ = build_app(store)
        arguments = '{"source":"alpha","body":{"size":5,"note":"\\ud800"}}'

        with caplog.at_level(logging.ERROR):
            async with running(app), http_client(app) as http:
                response = await _raw_call(http, "svc_sources_apply", arguments)

        result = response.json()["result"]
        assert result["isError"] is True
        assert "body.note" in result["structuredContent"]["error"]
        assert store.seen == []
        assert [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR] == []

    async def test_response_format_is_the_apis_view(self):
        app, _ = build_app(_store(alpha=4))

        async with running(app), mcp_client(app) as client:
            basic, _ = await _call(client, "svc_sources_get", {"source": "alpha", "response_format": "basic"})
            full, _ = await _call(client, "svc_sources_get", {"source": "alpha"})

        assert basic["body"] == {"name": "alpha", "size": None}
        assert full["body"] == {"name": "alpha", "size": 4}

    async def test_list_parameters_pass_through(self):
        app, _ = build_app(_store(alpha=1, beta=2))

        async with running(app), mcp_client(app) as client:
            page, _ = await _call(client, "svc_sources_list", {"page_size": 1})

        assert [item["name"] for item in page["body"]["items"]] == ["alpha"]
        assert page["body"]["next_page_token"]

    async def test_an_unknown_tool_is_a_protocol_error(self):
        app, _ = build_app(_store())

        async with running(app), mcp_client(app) as client:
            with pytest.raises(MCPError, match="Unknown tool"):
                await client.call_tool("svc_nothing_get", {})

    async def test_a_call_that_outlives_its_timeout_is_a_tool_error(self):
        app, _ = build_app(_store(), call_timeout=0.2)

        async with running(app), mcp_client(app) as client:
            answer, failed = await _call(client, "svc_delays_get", {"delay": 2})

        assert failed
        assert "did not answer svc_delays_get within 0.2 seconds" in answer["error"]


class TestStartup:
    """The tools are generated when the app starts, so a spec they cannot keep stops it."""

    async def test_a_write_that_cannot_preview_stops_startup(self):
        app, _ = build_app(_store())
        spec = copy.deepcopy(app.openapi())
        put = spec["paths"]["/api/v1/sources/{source}"]["put"]
        put["parameters"] = [p for p in put["parameters"] if p["name"] != "dry_run"]
        app.openapi_schema = spec

        with pytest.raises(McpSpecError, match="takes no dry_run"):
            async with running(app):
                pass

    async def test_the_endpoint_answers_503_until_the_app_starts(self):
        app, _ = build_app(_store())

        async with http_client(app) as http:
            response = await _list(http)

        assert response.status_code == 503

    async def test_the_app_can_start_twice(self):
        app, _ = build_app(_store())

        for _ in range(2):
            async with running(app), mcp_client(app) as client:
                assert len((await client.list_tools()).tools) == len(TOOLS)

    def test_the_mount_options_are_checked(self):
        with pytest.raises(ValueError, match="path"):
            mount(FastAPI(), path="mcp")
        with pytest.raises(ValueError, match="issuer"):
            mount(FastAPI(), issuer="idp.example.test")
        with pytest.raises(ValueError, match="call_timeout"):
            mount(FastAPI(), call_timeout=0)
