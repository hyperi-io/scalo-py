#  Project:   scalo
#  File:      src/scalo/mcp/server.py
#  Purpose:   Serve the generated tools on the app over stateless MCP, with RFC 9728 metadata
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Serve an app's generated tools on the app itself.

:func:`mount` adds the MCP endpoint and, when an issuer is named, the RFC 9728
protected-resource metadata, and joins the app's lifespan: the tools are
generated from ``app.openapi()`` when the app starts, so a spec that cannot be
served fails startup rather than the first call.

The endpoint speaks the MCP revision of 2026-07-28: no session, no
``initialize``, one JSON-RPC request per POST. Older clients get the stateless
form of the handshake-era transport. Nothing is kept between requests, so a
deployment can run any number of replicas without sticky sessions.

Every request first passes the ``Origin`` check. With an issuer, a request with
no bearer token or a token the configured verifier refuses gets HTTP 401 and the
``WWW-Authenticate`` challenge that points an MCP client at the issuer. A tool
call the app answers 401 always gets HTTP 401: that challenge with an issuer, a
bare ``Bearer`` one without. Without a verifier the app's own check on every
call is the only token check.
"""

import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.protocols import Validator
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.caching import CacheHint
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from mcp.shared.auth import ProtectedResourceMetadata
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from scalo.api import Problem, problem_response
from scalo.logger import logger

from .dispatch import EXCHANGE, AppClient, Exchange, call_tool, failure
from .tools import McpSpecError, ToolSpec, tools_from_spec

PROTOCOL_VERSION = "2026-07-28"

# How long a client may reuse a tools/list answer. The list changes only when the app is redeployed.
DEFAULT_TOOLS_TTL_MS = 300_000

DEFAULT_CALL_TIMEOUT = 60.0

_WELL_KNOWN = "/.well-known/oauth-protected-resource"

# How long a client may reuse the protected-resource metadata.
_METADATA_MAX_AGE = 3600

_PORT = re.compile(r"[0-9]{1,5}")


def _issuer(issuer: str) -> str:
    """``issuer`` when it is an absolute http(s) URL with no query or fragment, as OAuth issuers are."""
    parts = urlsplit(issuer)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ValueError(f"issuer must be an absolute http(s) URL with no query or fragment, not {issuer!r}")
    return issuer


def _origin(origin: str) -> str:
    """An allowed origin, ``scheme://host[:port]`` in lower case, or with ``:*`` for any port."""
    candidate = origin.strip().lower().rstrip("/")
    parts = urlsplit(candidate.removesuffix(":*"))
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise ValueError(f"allowed origin must be scheme://host[:port], with :* for any port, not {origin!r}")
    return candidate


def _origin_allowed(origin: str, allowed: frozenset[str]) -> bool:
    """Whether ``origin`` is allowed: an exact entry, or a ``:*`` entry's scheme and host with no port or a number."""
    value = origin.strip().lower()
    if value in allowed:
        return True
    for entry in allowed:
        if not entry.endswith(":*"):
            continue
        host = entry[:-2]
        if value == host or (value.startswith(host + ":") and _PORT.fullmatch(value[len(host) + 1 :])):
            return True
    return False


def _bearer(scope: Scope) -> str | None:
    """The request's ``Authorization: Bearer`` credential, ``None`` when it carries none."""
    for key, value in scope.get("headers") or ():
        if key.lower() == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            token = token.strip()
            return token if scheme.lower() == "bearer" and token else None
    return None


class McpServer:
    """The MCP endpoint on one app: the generated tools and the requests that reach them.

    Built and wired by :func:`mount`. An ASGI app itself, served at :attr:`path`.

    Args:
        app: The application the tools are generated from and call into.
        path: Where the endpoint is served.
        name: The server name MCP clients see. Defaults to the app's title.
        version: The server version. Defaults to the app's version.
        instructions: Guidance for the model using the tools, sent with ``server/discover``.
        issuer: The OAuth issuer whose tokens the app accepts. Naming one publishes
            RFC 9728 metadata, refuses a request without a bearer token, and puts
            the metadata URL in every 401 challenge.
        scopes: Scopes the metadata lists as supported.
        resource_url: The endpoint's public URL. Defaults to the URL each request
            arrived on, so a deployment behind a gateway that rewrites the host or
            the path names it here.
        token_verifier: Checks the bearer token of every request before any MCP
            handling, ``tools/list`` included: the MCP SDK's ``TokenVerifier``.
            Confirming the token was issued for this resource is its job. Needs
            ``issuer``.
        allowed_origins: Browser origins allowed to call the endpoint. A request
            carrying any other ``Origin`` is refused with 403. A request with no
            ``Origin``, which no browser sends, passes.
        security_settings: The MCP SDK's transport security settings, for its
            ``Host`` allow-list. Its ``allowed_origins`` join ``allowed_origins``.
        tools_ttl_ms: How long a client may reuse a ``tools/list`` answer.
        call_timeout: Seconds one tool call may take, its preview read included.

    Raises:
        ValueError: On a path that does not start with ``/``, an issuer that is
            not an absolute http(s) URL, a verifier without an issuer, an allowed
            origin that is not ``scheme://host[:port]``, a negative TTL or a
            timeout that is not positive.
    """

    def __init__(
        self,
        app: FastAPI,
        *,
        path: str = "/mcp",
        name: str | None = None,
        version: str | None = None,
        instructions: str | None = None,
        issuer: str | None = None,
        scopes: Sequence[str] = (),
        resource_url: str | None = None,
        token_verifier: TokenVerifier | None = None,
        allowed_origins: Sequence[str] = (),
        security_settings: TransportSecuritySettings | None = None,
        tools_ttl_ms: int = DEFAULT_TOOLS_TTL_MS,
        call_timeout: float = DEFAULT_CALL_TIMEOUT,
    ) -> None:
        if not path.startswith("/") or path == "/":
            raise ValueError(f"path must start with '/' and name an endpoint, not {path!r}")
        if call_timeout <= 0:
            raise ValueError(f"call_timeout must be positive, not {call_timeout}")
        if token_verifier is not None and issuer is None:
            raise ValueError("token_verifier needs an issuer: the 401 it answers points the client at it")
        self.path = path.rstrip("/")
        self.issuer = None if issuer is None else _issuer(issuer)
        self.scopes = tuple(scopes)
        self.resource_url = resource_url.rstrip("/") if resource_url else None
        extra_origins = security_settings.allowed_origins if security_settings is not None else ()
        self.allowed_origins = frozenset(_origin(origin) for origin in (*allowed_origins, *extra_origins))
        self._security = (
            None
            if security_settings is None
            else security_settings.model_copy(update={"allowed_origins": sorted(self.allowed_origins)})
        )
        self._verifier = token_verifier
        self._app = app
        self._call_timeout = call_timeout
        self._tools: dict[str, ToolSpec] = {}
        self._validators: dict[str, Validator] = {}
        self._manager: StreamableHTTPSessionManager | None = None
        self.server: Server[Any] = Server(
            name or app.title,
            version=version or app.version,
            instructions=instructions,
            cache_hints={"tools/list": CacheHint(ttl_ms=tools_ttl_ms, scope="public")},
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

    @property
    def tools(self) -> tuple[ToolSpec, ...]:
        """The tools generated at the last startup, in the order ``tools/list`` gives them."""
        return tuple(self._tools.values())

    def load(self) -> tuple[ToolSpec, ...]:
        """Generate the tools from ``app.openapi()``.

        Returns:
            The tools, sorted by name.

        Raises:
            McpSpecError: When the spec's opt-ins cannot be served as tools, or a
                generated input schema is not valid JSON Schema.
        """
        tools = tools_from_spec(self._app.openapi())
        validators: dict[str, Validator] = {}
        for tool in tools:
            try:
                Draft202012Validator.check_schema(tool.input_schema)
            except SchemaError as exc:
                raise McpSpecError(
                    f"tool {tool.name}: the input schema is not valid JSON Schema: {exc.message}"
                ) from exc
            validators[tool.name] = Draft202012Validator(tool.input_schema)
        self._tools = {tool.name: tool for tool in tools}
        self._validators = validators
        logger.info("MCP tools generated from the OpenAPI spec", tools=len(tools), path=self.path)
        return tools

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """Generate the tools and serve requests until the context exits.

        :func:`mount` runs this inside the app's lifespan. Each entry starts a
        fresh transport, so the app can be started more than once.
        """
        self.load()
        manager = StreamableHTTPSessionManager(
            app=self.server, json_response=True, stateless=True, security_settings=self._security
        )
        async with manager.run():
            self._manager = manager
            try:
                yield
            finally:
                self._manager = None

    async def _list_tools(
        self, _ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        if params is not None and params.cursor is not None:
            raise MCPError(code=INVALID_PARAMS, message="tools/list answers every tool at once: send no cursor")
        return ListToolsResult(tools=[tool.tool() for tool in self._tools.values()])

    async def _call_tool(self, ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams) -> CallToolResult:
        tool = self._tools.get(params.name)
        if tool is None:
            raise MCPError(code=INVALID_PARAMS, message=f"Unknown tool: {params.name}")
        request = ctx.request if isinstance(ctx.request, Request) else None
        result: CallToolResult | None = None
        # A deadline, not a TimeoutError catch: a TimeoutError the call raises is its own failure, not this one.
        with anyio.move_on_after(self._call_timeout):
            result = await call_tool(
                tool, self._validators[tool.name], params.arguments, lambda: AppClient(self._app, request)
            )
        if result is None:
            return failure(f"the API did not answer {tool.name} within {self._call_timeout:g} seconds")
        logger.debug("MCP tool call", tool=tool.name, operation=tool.operation_id, error=result.is_error)
        return result

    def resource(self, request: Request) -> str:
        """The endpoint's URL, which the protected-resource metadata names as the resource."""
        if self.resource_url is not None:
            return self.resource_url
        return str(request.base_url).rstrip("/") + self.path

    def metadata_endpoint(self, issuer: str) -> Callable[[Request], Awaitable[Response]]:
        """The endpoint answering the RFC 9728 protected-resource metadata request, naming ``issuer``."""

        async def metadata(request: Request) -> Response:
            refused = await self._refusal(request)
            if refused is not None:
                return refused
            document = ProtectedResourceMetadata(
                resource=AnyHttpUrl(self.resource(request)),
                authorization_servers=[AnyHttpUrl(issuer)],
                scopes_supported=list(self.scopes) or None,
                resource_name=self.server.name,
            )
            if self.resource_url is not None:
                headers = {"Cache-Control": f"public, max-age={_METADATA_MAX_AGE}"}
            else:
                # The resource comes from this request's Host, so no shared cache may serve it to another host.
                headers = {"Cache-Control": f"private, max-age={_METADATA_MAX_AGE}", "Vary": "Host"}
            return JSONResponse(document.model_dump(mode="json", exclude_none=True), headers=headers)

        return metadata

    def _challenge(self, request: Request, *, error: str | None = None) -> Response:
        """401 with the RFC 9728 ``WWW-Authenticate`` challenge, or a bare ``Bearer`` one with no issuer to name."""
        if self.issuer is None:
            challenge = "Bearer"
        else:
            metadata_url = build_resource_metadata_url(AnyHttpUrl(self.resource(request)))
            challenge = "Bearer "
            if error is not None:
                challenge += f'error="{error}", '
            challenge += f'resource_metadata="{metadata_url}"'
            if self.scopes:
                challenge += f', scope="{" ".join(self.scopes)}"'
        detail = (
            "The bearer token is missing, invalid or expired"
            if error is not None
            else "Send the caller's token as Authorization: Bearer"
        )
        problem = Problem(title="Unauthorized", status=401, detail=detail, code="unauthenticated")
        return problem_response(problem, headers={"WWW-Authenticate": challenge})

    async def _refusal(self, request: Request) -> Response | None:
        """403 for an ``Origin`` that is not allowed, or the SDK's refusal of a ``Host`` its settings do not allow."""
        origin = request.headers.get("origin")
        if origin is not None and not _origin_allowed(origin, self.allowed_origins):
            problem = Problem(
                title="Forbidden", status=403, detail="The request's Origin is not allowed", code="origin_not_allowed"
            )
            return problem_response(problem)
        if self._security is None:
            return None
        return await TransportSecurityMiddleware(self._security).validate_request(request, is_post=False)

    async def _token_accepted(self, token: str) -> bool:
        """Whether the verifier accepts ``token`` and it has not expired."""
        if self._verifier is None:
            return True
        access = await self._verifier.verify_token(token)
        if access is None:
            return False
        return access.expires_at is None or access.expires_at > time.time()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request to the MCP endpoint."""
        if scope["type"] != "http":
            return
        request = Request(scope)
        refused = await self._refusal(request)
        if refused is not None:
            await refused(scope, receive, send)
            return
        if self.issuer is not None:
            token = _bearer(scope)
            if token is None:
                await self._challenge(request)(scope, receive, send)
                return
            if not await self._token_accepted(token):
                await self._challenge(request, error="invalid_token")(scope, receive, send)
                return
        manager = self._manager
        if manager is None:
            problem = Problem(title="Service Unavailable", status=503, detail="The MCP endpoint has not started")
            await problem_response(problem)(scope, receive, send)
            return
        await self._serve_challenging(manager, request, scope, receive, send)

    async def _serve_challenging(
        self, manager: StreamableHTTPSessionManager, request: Request, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Serve the request, answering with the 401 challenge instead when a tool call met the app's 401."""
        exchange = Exchange()
        challenged = False

        async def respond(message: Message) -> None:
            nonlocal challenged
            if message["type"] == "http.response.start" and exchange.unauthorised:
                challenged = True
                await self._challenge(request, error="invalid_token")(scope, receive, send)
                return
            if not challenged:
                await send(message)

        await manager.handle_request({**scope, EXCHANGE: exchange}, receive, respond)


def mount(
    app: FastAPI,
    *,
    path: str = "/mcp",
    name: str | None = None,
    version: str | None = None,
    instructions: str | None = None,
    issuer: str | None = None,
    scopes: Sequence[str] = (),
    resource_url: str | None = None,
    token_verifier: TokenVerifier | None = None,
    allowed_origins: Sequence[str] = (),
    security_settings: TransportSecuritySettings | None = None,
    tools_ttl_ms: int = DEFAULT_TOOLS_TTL_MS,
    call_timeout: float = DEFAULT_CALL_TIMEOUT,
) -> McpServer:
    """Serve MCP tools generated from the app's spec on the app itself.

    Adds the endpoint at ``path`` and, with an ``issuer``, the RFC 9728 metadata
    at ``/.well-known/oauth-protected-resource`` followed by ``path``. The routes
    go ahead of the app's own, so a catch-all mount cannot hide them, and stay out
    of the OpenAPI spec. The tools are generated when the app starts: wire the app
    with :func:`scalo.api.install` first, so its spec carries ``x-scalo``.

    Args:
        app: The application.
        path: Where the endpoint is served.
        name: The server name MCP clients see. Defaults to the app's title.
        version: The server version. Defaults to the app's version.
        instructions: Guidance for the model using the tools.
        issuer: The OAuth issuer whose tokens the app accepts.
        scopes: Scopes the metadata lists as supported.
        resource_url: The endpoint's public URL, when the request URL is not it.
        token_verifier: Checks every request's bearer token before any MCP handling.
        allowed_origins: Browser origins allowed to call the endpoint.
        security_settings: The MCP SDK's transport security settings.
        tools_ttl_ms: How long a client may reuse a ``tools/list`` answer.
        call_timeout: Seconds one tool call may take.

    Returns:
        The mounted server.

    Raises:
        ValueError: On an invalid argument, as :class:`McpServer` lists.
    """
    server = McpServer(
        app,
        path=path,
        name=name,
        version=version,
        instructions=instructions,
        issuer=issuer,
        scopes=scopes,
        resource_url=resource_url,
        token_verifier=token_verifier,
        allowed_origins=allowed_origins,
        security_settings=security_settings,
        tools_ttl_ms=tools_ttl_ms,
        call_timeout=call_timeout,
    )
    routes = [Route(server.path, endpoint=server, include_in_schema=False)]
    if server.issuer is not None:
        metadata = server.metadata_endpoint(server.issuer)
        routes.append(Route(_WELL_KNOWN + server.path, endpoint=metadata, methods=["GET"], include_in_schema=False))
    app.router.routes[0:0] = routes

    serve_app = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(target: Any) -> AsyncIterator[Any]:
        async with serve_app(target) as state, server.run():
            yield state

    app.router.lifespan_context = lifespan
    return server
