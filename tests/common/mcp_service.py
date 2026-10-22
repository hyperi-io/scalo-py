#  Project:   scalo
#  File:      tests/common/mcp_service.py
#  Purpose:   A small scalo.api service with scalo.mcp mounted, and the MCP SDK client wired to it
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A scalo.api service that follows every convention, with its tools served by ``scalo.mcp``.

The service checks bearer tokens and RBAC itself, so a test can tell the app's own
401 and 403 from anything the MCP layer answers. Each replica built over one
:class:`Store` shares its data, the way replicas share a datastore.
"""

import json
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx2
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.provider import AccessToken
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scalo.api import (
    DryRun,
    GetView,
    Hierarchy,
    ListParams,
    McpHints,
    Page,
    PreconditionHeaders,
    ProblemError,
    View,
    etag_of,
    install,
    paginate,
    permission,
    scalo_extra,
)
from scalo.mcp import McpServer, mount

BASE_URL = "http://svc.test"
ISSUER = "https://idp.example.test/realms/svc"
HIERARCHY = Hierarchy(base_path="/api/v1", singletons={"deployment"}, tool_prefix="svc_")

READER = "reader-token"
WRITER = "writer-token"
OTHER_WRITER = "other-writer-token"
_GRANTS = {
    READER: {"source:read"},
    WRITER: {"source:read", "source:write"},
    OTHER_WRITER: {"source:read", "source:write"},
}

# What the crash fault's exception message holds, which no tool answer may echo.
CRASH_SECRET = "crash-secret-7f3a"

# The tools the service opts in, in the order tools/list gives them.
TOOLS = [
    "svc_delays_get",
    "svc_faults_get",
    "svc_sources_apply",
    "svc_sources_delete",
    "svc_sources_deploy",
    "svc_sources_get",
    "svc_sources_list",
]


class SourceSpec(BaseModel):
    """What a caller sends to create or replace a source."""

    size: int = Field(ge=1)


class Source(BaseModel):
    """A stored source. A basic view leaves the size out."""

    name: str
    size: int | None = None


class Change(BaseModel):
    """The change a write made, or would make on a dry run."""

    dry_run: bool
    before: Source | None
    after: Source | None


class Deployment(BaseModel):
    """The operation a deploy started, or would start."""

    operation: str
    dry_run: bool


class Delay(BaseModel):
    """How long a delay took."""

    seconds: float


@dataclass
class Store:
    """The data every replica of the service shares, and the requests the API itself served.

    Attributes:
        sources: Stored sources by name.
        seen: ``(method, path, Authorization header)`` for each request a permission check ran on.
        peers: The peer address, ``(host, port)`` or ``None``, of each request a permission check ran on.
    """

    sources: dict[str, Source] = field(default_factory=dict)
    seen: list[tuple[str, str, str]] = field(default_factory=list)
    peers: list[tuple[str, int] | None] = field(default_factory=list)


class Verifier:
    """The service's token verifier for the MCP endpoint: the tokens it issued, expired when told to be.

    Attributes:
        checked: Each token it was asked about, in order.
    """

    def __init__(self, *, expired: bool = False) -> None:
        self.checked: list[str] = []
        self._expires_at = int(time.time()) + (-60 if expired else 3600)

    async def verify_token(self, token: str) -> AccessToken | None:
        """The access the token grants, ``None`` for one the service did not issue."""
        self.checked.append(token)
        if token not in _GRANTS:
            return None
        return AccessToken(
            token=token, client_id="svc-agent", scopes=["svc"], expires_at=self._expires_at, resource=f"{BASE_URL}/mcp"
        )


def _store(request: Request) -> Store:
    return request.app.state.store


def require(action: str):
    """The service's RBAC dependency: a bearer token holding ``action``."""

    @permission(action)
    def check(request: Request) -> None:
        authorization = request.headers.get("authorization", "")
        _store(request).seen.append((request.method, request.url.path, authorization))
        _store(request).peers.append(None if request.client is None else (request.client.host, request.client.port))
        grants = _GRANTS.get(authorization.removeprefix("Bearer "))
        if grants is None:
            raise ProblemError(401, "The token is not one this service issued", code="unauthenticated")
        if action not in grants:
            raise ProblemError(403, f"The token does not grant {action}", code="forbidden")

    return check


def _found(store: Store, source: str) -> Source:
    current = store.sources.get(source)
    if current is None:
        raise ProblemError(404, f"No source named {source}", code="not_found")
    return current


def build_app(
    store: Store, *, issuer: str | None = ISSUER, catch_unhandled: bool = True, **options: Any
) -> tuple[FastAPI, McpServer]:
    """One replica of the service, its tools mounted at ``/mcp``."""
    sources = APIRouter(prefix="/sources")
    read = [Depends(require("source:read"))]
    write = [Depends(require("source:write"))]

    @sources.get("", dependencies=read, openapi_extra=scalo_extra(mcp=McpHints()))
    def list_sources(request: Request, query: ListParams) -> Page[Source]:
        """List sources."""
        return paginate(sorted(_store(request).sources.values(), key=lambda item: item.name), query)

    @sources.get("/{source}", dependencies=read, openapi_extra=scalo_extra(mcp=McpHints()))
    def get_source(source: str, request: Request, response: Response, view: GetView) -> Source:
        """Get a source."""
        current = _found(_store(request), source)
        response.headers["ETag"] = etag_of(current)
        return current if view is View.FULL else Source(name=current.name)

    @sources.put("/{source}", dependencies=write, openapi_extra=scalo_extra(mcp=McpHints()))
    def apply_source(
        source: str, body: SourceSpec, request: Request, response: Response, pre: PreconditionHeaders, dry_run: DryRun
    ) -> Change:
        """Create or replace a source."""
        store = _store(request)
        current = store.sources.get(source)
        pre.check(None if current is None else etag_of(current))
        after = Source(name=source, size=body.size)
        if not dry_run:
            store.sources[source] = after
            response.headers["ETag"] = etag_of(after)
        return Change(dry_run=dry_run, before=current, after=after)

    @sources.delete("/{source}", dependencies=write, openapi_extra=scalo_extra(mcp=McpHints()))
    def delete_source(source: str, request: Request, pre: PreconditionHeaders, dry_run: DryRun) -> Change:
        """Delete a source."""
        store = _store(request)
        current = _found(store, source)
        pre.check(etag_of(current))
        if not dry_run:
            del store.sources[source]
        return Change(dry_run=dry_run, before=current, after=None)

    @sources.post("/{source}/deploy", dependencies=write, openapi_extra=scalo_extra(mcp=McpHints(task=True)))
    def deploy_source(source: str, request: Request, dry_run: DryRun) -> Deployment:
        """Deploy a source."""
        _found(_store(request), source)
        return Deployment(operation=f"operations/deploy-{source}", dry_run=dry_run)

    @sources.get("/{source}/preview", dependencies=read, openapi_extra=scalo_extra(verb="preview"))
    def preview_source(source: str, request: Request) -> Source:
        """Preview a source, which no tool exposes."""
        return _found(_store(request), source)

    delays = APIRouter(prefix="/delays")

    @delays.get("/{delay}", dependencies=read, openapi_extra=scalo_extra(mcp=McpHints()))
    async def get_delay(delay: float) -> Delay:
        """Wait, then say how long."""
        await anyio.sleep(delay)
        return Delay(seconds=delay)

    faults = APIRouter(prefix="/faults")

    @faults.get("/{fault}", dependencies=read, openapi_extra=scalo_extra(mcp=McpHints()))
    async def get_fault(fault: str) -> Delay:
        """Fail the way the fault names: ``crash`` or ``timeout``."""
        if fault == "timeout":
            raise TimeoutError("the upstream did not answer")
        raise RuntimeError(f"the handler crashed holding {CRASH_SECRET}")

    deployment = APIRouter(prefix="/deployment")

    @deployment.get("", openapi_extra=scalo_extra(public=True))
    def get_deployment() -> Deployment:
        """Get the deployment, which no tool exposes."""
        return Deployment(operation="none", dry_run=False)

    app = FastAPI(title="svc", version="1.2.3", generate_unique_id_function=HIERARCHY.unique_id)
    app.state.store = store
    for router in (sources, delays, faults, deployment):
        app.include_router(router, prefix="/api/v1")
    install(app, HIERARCHY, catch_unhandled=catch_unhandled)
    server = mount(app, issuer=issuer, scopes=("svc",), **options)
    return app, server


@asynccontextmanager
async def running(*apps: FastAPI) -> AsyncIterator[None]:
    """Run each app's lifespan, as its server would at startup."""
    async with AsyncExitStack() as stack:
        for app in apps:
            await stack.enter_async_context(app.router.lifespan_context(app))
        yield


def http_client(
    asgi: ASGIApp, token: str | None = WRITER, *, headers: dict[str, str] | None = None
) -> httpx2.AsyncClient:
    """An HTTP client that reaches ``asgi`` without a network, sending ``token`` as the bearer."""
    sent = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=asgi), base_url=BASE_URL, headers={**sent, **(headers or {})}
    )


@asynccontextmanager
async def mcp_client(
    asgi: ASGIApp, token: str | None = WRITER, *, mode: str = "auto", headers: dict[str, str] | None = None
) -> AsyncIterator[Client]:
    """The MCP SDK's own client, over streamable HTTP to the service's ``/mcp``."""
    async with (
        http_client(asgi, token, headers=headers) as http,
        Client(streamable_http_client(f"{BASE_URL}/mcp", http_client=http), mode=mode, cache=None) as client,
    ):
        yield client


class Peer:
    """An ASGI wrapper that delivers every request from ``client``: ``(host, port)``, or ``None`` for no peer."""

    def __init__(self, app: ASGIApp, client: tuple[str, int] | None) -> None:
        self.app = app
        self.client = client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app({**scope, "client": self.client}, receive, send)


@dataclass
class Exchange:
    """One HTTP request a client sent, and what came back.

    Attributes:
        path: The request path.
        rpc: The JSON-RPC method in the body, ``None`` for a body that carries none.
        status: The response status.
        headers: The response headers, names lower case.
    """

    path: str
    rpc: str | None = None
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)


class Recorder:
    """An ASGI wrapper that records every request reaching ``app`` from outside the process."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.exchanges: list[Exchange] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received: list[Message] = []
        body = b""
        while True:
            message = await receive()
            received.append(message)
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        exchange = Exchange(path=scope["path"])
        if body:
            decoded = json.loads(body)
            exchange.rpc = decoded.get("method") if isinstance(decoded, dict) else None
        self.exchanges.append(exchange)

        async def replay() -> Message:
            return received.pop(0) if received else await receive()

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                exchange.status = message["status"]
                exchange.headers = {key.decode().lower(): value.decode() for key, value in message["headers"]}
            await send(message)

        await self.app(scope, replay, capture)


class RoundRobin:
    """A load balancer with no session affinity: each request goes to the next replica in turn."""

    def __init__(self, *replicas: ASGIApp) -> None:
        self.replicas = replicas
        self.served: list[int] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        index = len(self.served) % len(self.replicas)
        self.served.append(index)
        await self.replicas[index](scope, receive, send)
