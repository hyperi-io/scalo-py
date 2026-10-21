#  Project:   scalo
#  File:      src/scalo/cli/openapi/client.py
#  Purpose:   Turn an Operation and its input document into one HTTP call
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Bind a base URL and a credential to a transport, and call operations through it.

An API key goes in the configured header (``X-API-Key`` by default), a token as
``Authorization: Bearer``. Both travel as credentials, which a transport never
forwards to a redirect target.
"""

import datetime
import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote, urlencode

from scalo._openapi import wire_value

from .config import Credential
from .errors import ApiError, CliUsageError
from .spec import Operation
from .transport import Response, Transport


def _json_value(value: Any) -> str:
    """A body value JSON has no type for: a YAML date or timestamp as ISO 8601.

    Raises:
        CliUsageError: For any other type, such as a YAML ``!!binary``.
    """
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    raise CliUsageError(f"the body holds a {type(value).__name__}, which a JSON body cannot carry")


class Client:
    """Calls operations against one API.

    Args:
        base_url: The API's base URL, such as ``https://api.example``.
        credential: The credential, ``None`` to call anonymously.
        transport: Sends the requests.
        api_key_header: The header an API key goes in.
        timeout: Seconds to wait for each answer.
        trace: Takes a line per request sent and per answer, for ``--verbose``.
            Credentials never reach it.
    """

    def __init__(
        self,
        base_url: str,
        credential: Credential | None,
        transport: Transport,
        *,
        api_key_header: str = "X-API-Key",
        timeout: float = 30.0,
        trace: Callable[[str], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.credential = credential
        self._transport = transport
        self._api_key_header = api_key_header
        self._timeout = timeout
        self._trace = trace

    def credentials(self) -> dict[str, str]:
        """The authentication headers for this client's credential."""
        credential = self.credential
        if credential is None or credential.value is None:
            return {}
        if credential.is_api_key:
            return {self._api_key_header: credential.value}
        return {"Authorization": f"Bearer {credential.value}"}

    def url(self, operation: Operation, path: Mapping[str, Any], query: Mapping[str, Any]) -> str:
        """The operation's URL with its path parameters filled in and its query string.

        Raises:
            CliUsageError: When a path parameter has no value.
        """
        template = operation.path
        for field in operation.parameters:
            if field.location != "path":
                continue
            value = path.get(field.name)
            if value is None or value == "":
                raise CliUsageError(f"{operation.operation_id} needs a value for path parameter {field.name!r}")
            template = template.replace("{" + field.name + "}", quote(str(value), safe=""))
        pairs = {name: wire_value(value) for name, value in query.items() if value is not None}
        suffix = f"?{urlencode(pairs, doseq=True)}" if pairs else ""
        return f"{self.base_url}{template}{suffix}"

    def _send(self, method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        request_headers = {"Accept": "application/json", **headers}
        content = None
        if body is not None:
            content = json.dumps(body, ensure_ascii=False, default=_json_value).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if self._trace is not None:
            self._trace(f"> {method.upper()} {url}")
        reply = self._transport.send(
            method.upper(),
            url,
            headers=request_headers,
            credentials=self.credentials(),
            content=content,
            timeout=self._timeout,
        )
        if self._trace is not None:
            self._trace(f"< {reply.status} {reply.reason}".rstrip())
        return reply

    def send(self, method: str, path: str, *, headers: Mapping[str, str] | None = None, body: Any = None) -> Response:
        """Send one request to a path below the base URL, for a hand-written command.

        Args:
            method: The HTTP method.
            path: The path, such as ``/api/v1/auth/login``.
            headers: Extra request headers.
            body: A JSON body, if any.

        Returns:
            The answer, whatever its status.

        Raises:
            TransportError: When the API cannot be reached.
        """
        return self._send(method, f"{self.base_url}/{path.lstrip('/')}", headers or {}, body)

    def call(self, operation: Operation, request: Mapping[str, Any]) -> Any:
        """Call one operation with an input document.

        Args:
            operation: The operation.
            request: The input document: ``path``, ``query``, ``header`` and ``body``.

        Returns:
            The parsed JSON answer, its text when it is not JSON, ``None`` when empty.

        Raises:
            ApiError: On a status outside 2xx.
            CliUsageError: When a path parameter has no value.
            TransportError: When the API cannot be reached.
        """
        url = self.url(operation, request.get("path") or {}, request.get("query") or {})
        headers = {
            name: str(wire_value(value)) for name, value in (request.get("header") or {}).items() if value is not None
        }
        reply = self._send(operation.method, url, headers, request.get("body"))
        if not reply.ok:
            raise ApiError(reply)
        if reply.status == 204 or not reply.content:
            return None
        try:
            return reply.json()
        except ValueError:
            return reply.content.decode("utf-8", errors="replace")
