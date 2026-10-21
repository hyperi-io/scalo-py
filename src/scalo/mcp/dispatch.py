#  Project:   scalo
#  File:      src/scalo/mcp/dispatch.py
#  Purpose:   Run one tool call in-process through the app, as the MCP request's caller
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Run one tool call through the app it was generated from.

The call never leaves the process: it is an ASGI request into the same app,
carrying the MCP request's own ``Authorization`` header, so the app's
authentication, RBAC, preconditions, validation and audit run exactly as they
would for the caller's direct request. A write runs in two calls:

1. The preview (``dry_run`` true, the default) reads the resource's current
   ETag with a GET on the same path, then sends the write with ``dry_run=true``
   and that ETag as ``If-Match``. It returns the API's answer and a preview
   token naming the ETag and the exact request, keyed with the caller's
   ``Authorization`` header.
2. The commit (``dry_run`` false) sends the token back. It is refused with 412
   unless its own request, under the same ``Authorization``, is the one the
   token names, and it carries the token's ETag as ``If-Match``, so it lands
   only on the state the preview saw and the API answers 412 when someone else
   wrote first. A commit with no ``Authorization`` is refused outright.

Both halves are stateless: everything the commit needs travels in its arguments.
"""

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx2
from jsonschema.exceptions import best_match
from jsonschema.protocols import Validator
from mcp.types import CallToolResult, TextContent
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from scalo._openapi import is_json_media_type, wire_value
from scalo.api import Problem
from scalo.logger import logger

from .tools import BODY, CREATE_ETAG, DRY_RUN, PREVIEW_TOKEN, ToolSpec

_ACCEPT = "application/json, application/problem+json"

# Path values that would move the request onto another route once the path is decoded.
_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})

# The scope key under which the MCP endpoint hands each tool call the Exchange it reports back through.
EXCHANGE = "scalo.mcp.exchange"


@dataclass(slots=True)
class Exchange:
    """What the tool calls of one MCP request report back to the endpoint serving it.

    Attributes:
        unauthorised: The app answered one of the in-process requests 401.
    """

    unauthorised: bool = False


@dataclass(frozen=True, slots=True)
class Reply:
    """What the app answered one in-process request.

    Attributes:
        status: The HTTP status.
        etag: The ``ETag`` header, if any.
        body: The decoded JSON body, the text of any other body, ``None`` for none.
    """

    status: int
    etag: str | None
    body: Any


class ArgumentError(ValueError):
    """A tool's arguments cannot form the request it stands for."""


def _logs_unhandled(app: ASGIApp) -> bool:
    """Whether the app answers an unhandled exception itself, through a 500 or ``Exception`` handler that logs it."""
    handlers = getattr(app, "exception_handlers", None)
    return isinstance(handlers, Mapping) and (Exception in handlers or 500 in handlers)


def _in_process(
    app: ASGIApp, state: Mapping[str, Any] | None, client: tuple[str, int] | None, *, logs_unhandled: bool
) -> ASGIApp:
    """``app`` as the MCP request's caller reaches it: that request's peer address and a copy of its lifespan state.

    An exception that escapes the app is logged here unless the app logs it
    itself, then re-raised for the transport, which answers with the 500 the
    app already sent.
    """

    async def call(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope = {**scope, "client": client}
            if state is not None:
                scope["state"] = dict(state)
        try:
            await app(scope, receive, send)
        except Exception as exc:
            if not logs_unhandled:
                logger.opt(exception=exc).error(
                    "Unhandled exception in an MCP tool call", method=scope.get("method"), path=scope.get("path")
                )
            raise

    return call


def _decode(response: httpx2.Response) -> Any:
    if not response.content:
        return None
    if is_json_media_type(response.headers.get("content-type", "")):
        try:
            return response.json()
        except ValueError:
            return response.text
    return response.text


class AppClient:
    """Sends requests into an ASGI app in-process, as the MCP request's caller.

    Args:
        app: The application the tools were generated from.
        request: The MCP HTTP request, whose ``Authorization`` header, peer
            address, scheme, host and lifespan state each request reuses.
            ``None`` sends requests with no credentials and no peer address.

    Attributes:
        preview_key: The ``Authorization`` header's bytes, which key the
            caller's preview tokens. Empty when the request carries none.
    """

    def __init__(self, app: ASGIApp, request: Request | None) -> None:
        state = request.scope.get("state") if request is not None else None
        peer = request.client if request is not None else None
        exchange = request.scope.get(EXCHANGE) if request is not None else None
        self._exchange = exchange if isinstance(exchange, Exchange) else None
        self._headers = {"accept": _ACCEPT}
        self.preview_key = b""
        base_url = "http://mcp.invalid"
        if request is not None:
            authorization = request.headers.get("authorization")
            if authorization:
                self._headers["authorization"] = authorization
                self.preview_key = authorization.encode("latin-1")
            base_url = f"{request.url.scheme}://{request.url.netloc}"
        target = _in_process(
            app,
            state if isinstance(state, Mapping) else None,
            (peer.host, peer.port) if peer is not None else None,
            logs_unhandled=_logs_unhandled(app),
        )
        # The app's own 500 is the answer to an unhandled exception, so the transport must not raise it again.
        transport = httpx2.ASGITransport(app=target, raise_app_exceptions=False)
        self._client = httpx2.AsyncClient(transport=transport, base_url=base_url)

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self._client.__aexit__(exc_type, exc, traceback)

    async def send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        body: Any = None,
    ) -> Reply:
        """Send one request and decode the answer.

        A 401 is also reported to the MCP request's :class:`Exchange`, so the
        endpoint can answer that request with its own 401 challenge.

        Args:
            method: The HTTP method.
            path: The path, parameters already substituted.
            params: Query parameters. A list repeats its parameter.
            headers: Extra headers, such as ``If-Match``.
            body: The JSON body, ``None`` to send none.

        Returns:
            The app's answer.
        """
        response = await self._client.request(
            method,
            path,
            params=dict(params or {}),
            headers={**self._headers, **(headers or {})},
            json=body,
        )
        if response.status_code == 401 and self._exchange is not None:
            self._exchange.unauthorised = True
        return Reply(status=response.status_code, etag=response.headers.get("etag"), body=_decode(response))


def _not_unicode(value: Any, where: str = "") -> str | None:
    """The dotted path of the first string, key or value, that UTF-8 cannot encode, ``None`` when there is none.

    JSON can escape a lone surrogate into a string, and nothing downstream can send one.
    """
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return where or "arguments"
        return None
    items: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            label = f"{where}.{key}" if where else str(key)
            if _not_unicode(str(key)) is not None:
                return where or "arguments"
            items.append((label, item))
    elif isinstance(value, list):
        items = [(f"{where}[{index}]", item) for index, item in enumerate(value)]
    for label, item in items:
        if (found := _not_unicode(item, label)) is not None:
            return found
    return None


def _text(value: Any) -> str:
    """A scalar argument as a path segment or header value."""
    return str(wire_value(value))


def _path(tool: ToolSpec, arguments: Mapping[str, Any]) -> str:
    path = tool.path
    for argument in tool.path_arguments:
        value = _text(arguments[argument.name])
        if value in _UNSAFE_SEGMENTS or "/" in value:
            raise ArgumentError(f"{argument.name} must be one path segment: not empty, '.', '..', or holding '/'")
        path = path.replace("{" + argument.wire + "}", quote(value, safe=""))
    return path


def _header(name: str, value: Any) -> str:
    """``value`` as a header value, refusing the control characters that would end the header early."""
    text = _text(value)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ArgumentError(f"{name} may not hold control characters")
    return text


def _request_parts(tool: ToolSpec, arguments: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """The query parameters and headers the arguments carry."""
    params: dict[str, Any] = {}
    headers: dict[str, str] = {}
    for argument in tool.arguments:
        value = arguments.get(argument.name)
        if value is None:
            continue
        if argument.location == "query":
            params[argument.wire] = wire_value(value)
        elif argument.location == "header":
            headers[argument.wire] = _header(argument.name, value)
    return params, headers


@dataclass(frozen=True, slots=True)
class _Write:
    """The request a write's preview and commit both send, ``dry_run`` and the precondition aside."""

    method: str
    path: str
    params: dict[str, Any]
    headers: dict[str, str]
    body: Any


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _seal(etag: str | None, write: _Write, key: bytes) -> str:
    """The preview token: the ETag the preview read, then an HMAC-SHA256 over that ETag and the whole request."""
    canonical = json.dumps(
        [etag, write.method, write.path, write.params, write.headers, write.body],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    mac = hmac.new(key, canonical.encode(), hashlib.sha256).digest()
    return f"{_b64((etag or '').encode())}.{_b64(mac)}"


def _token_etag(token: str) -> str | None:
    """The ETag a preview token carries, ``None`` for a write that takes no precondition."""
    encoded, separator, _ = token.partition(".")
    if not separator:
        raise ArgumentError(f"{PREVIEW_TOKEN} is not one a dry run returned")
    try:
        etag = _unb64(encoded).decode()
    except ValueError as exc:
        raise ArgumentError(f"{PREVIEW_TOKEN} is not one a dry run returned") from exc
    return _header(PREVIEW_TOKEN, etag) or None


def _precondition(etag: str) -> dict[str, str]:
    """The header that binds a write to ``etag``: ``If-None-Match: *`` for a create, ``If-Match`` otherwise."""
    if etag == CREATE_ETAG:
        return {"If-None-Match": "*"}
    return {"If-Match": etag}


def _result(payload: dict[str, Any], *, error: bool) -> CallToolResult:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return CallToolResult(content=[TextContent(text=text)], structured_content=payload, is_error=error)


def failure(message: str) -> CallToolResult:
    """A tool error that never reached the API, such as an invalid argument."""
    return _result({"error": message}, error=True)


def _answer(reply: Reply, **extra: Any) -> CallToolResult:
    payload: dict[str, Any] = {"status": reply.status, **extra, "body": reply.body}
    if reply.etag is not None and "etag" not in payload:
        payload["etag"] = reply.etag
    return _result(payload, error=reply.status >= 400)


async def _preview(tool: ToolSpec, client: AppClient, write: _Write) -> CallToolResult:
    etag: str | None = None
    headers = write.headers
    if tool.if_match:
        current = await client.send("GET", write.path)
        if current.status == 404 and tool.if_none_match:
            etag = CREATE_ETAG
        elif current.status >= 400:
            return _answer(current, dry_run=True)
        elif current.etag is None:
            return failure(f"GET {write.path} answered without an ETag, so {tool.name} has nothing to bind a commit to")
        else:
            etag = current.etag
        headers = {**headers, **_precondition(etag)}
    reply = await client.send(
        write.method, write.path, params={**write.params, DRY_RUN: True}, headers=headers, body=write.body
    )
    extra: dict[str, Any] = {"dry_run": True}
    if etag is not None:
        extra["etag"] = etag
    if reply.status < 400:
        token = _seal(etag, write, client.preview_key)
        extra[PREVIEW_TOKEN] = token
        extra["next"] = (
            f"Nothing was changed. To commit this change, call {tool.name} again with the same arguments, "
            f"dry_run=false and preview_token={token!r}."
        )
    return _answer(reply, **extra)


def _mismatch() -> CallToolResult:
    problem = Problem(
        title="Precondition Failed",
        status=412,
        detail="The commit's arguments or credential differ from the preview's: preview this change, then commit",
        code="preview_mismatch",
    )
    reply = Reply(status=412, etag=None, body=problem.model_dump(mode="json", exclude_none=True))
    return _answer(reply, dry_run=False)


async def _commit(tool: ToolSpec, client: AppClient, write: _Write, token: str | None) -> CallToolResult:
    if not client.preview_key:
        return failure(
            f"dry_run=false commits the change, which needs the caller's Authorization header: the preview_token of "
            f"{tool.name} is keyed with it, and one keyed with nothing could be forged"
        )
    if not token:
        return failure(
            f"dry_run=false commits the change, which needs the preview_token a dry run of {tool.name} returned: "
            "call it with dry_run=true first"
        )
    etag = _token_etag(token)
    expected = _seal(etag, write, client.preview_key)
    if not hmac.compare_digest(token.encode("utf-8", "replace"), expected.encode()):
        return _mismatch()
    headers = write.headers if etag is None else {**write.headers, **_precondition(etag)}
    reply = await client.send(
        write.method, write.path, params={**write.params, DRY_RUN: False}, headers=headers, body=write.body
    )
    return _answer(reply, dry_run=False)


async def call_tool(
    tool: ToolSpec,
    validator: Validator,
    arguments: Mapping[str, Any] | None,
    client_factory: Callable[[], AppClient],
) -> CallToolResult:
    """Run one tool call: validate its arguments, then send its request into the app.

    Args:
        tool: The tool.
        validator: Checks the arguments against the tool's input schema.
        arguments: The call's arguments.
        client_factory: Opens the in-process client for this call.

    Returns:
        The API's answer as the tool result, ``is_error`` set for a status of 400
        or above, for a commit whose arguments differ from its preview's, and for
        arguments that never reached the API.
    """
    arguments = dict(arguments or {})
    invalid = best_match(validator.iter_errors(arguments))
    if invalid is not None:
        where = ".".join(str(part) for part in invalid.absolute_path)
        return failure(
            f"invalid argument {where}: {invalid.message}" if where else f"invalid arguments: {invalid.message}"
        )
    if (where := _not_unicode(arguments)) is not None:
        return failure(f"invalid argument {where}: it holds a lone surrogate, which is not Unicode text")
    try:
        path = _path(tool, arguments)
        params, headers = _request_parts(tool, arguments)
    except ArgumentError as exc:
        return failure(str(exc))
    write = _Write(method=tool.method, path=path, params=params, headers=headers, body=arguments.get(BODY))

    async with client_factory() as client:
        if tool.read_only:
            return _answer(await client.send(tool.method, path, params=params, headers=headers, body=write.body))
        if arguments.get(DRY_RUN, True):
            return await _preview(tool, client, write)
        try:
            return await _commit(tool, client, write, arguments.get(PREVIEW_TOKEN))
        except ArgumentError as exc:
            return failure(str(exc))
