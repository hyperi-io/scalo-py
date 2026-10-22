#  Project:   scalo
#  File:      src/scalo/cli/openapi/transport.py
#  Purpose:   The HTTP seam the generated CLI sends through: stdlib by default, scalo.http on request
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The one place the generated CLI touches the network.

:class:`UrllibTransport` is the default and needs nothing beyond the standard
library, so ``scalo[cli]`` stays Typer and JMESPath. :class:`ScaloHttpTransport`
sends through :mod:`scalo.http` instead, retrying GET and HEAD, for a consumer that
has the ``http`` extra. A test hands in its own :class:`Transport`, such as one
backed by an in-process ASGI app.
"""

import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

# Methods a retry cannot turn into a second write.
_IDEMPOTENT = frozenset({"GET", "HEAD"})


@dataclass(frozen=True, slots=True)
class Response:
    """One HTTP response, whatever sent it.

    Attributes:
        status: The status code.
        headers: Response headers, names lower-cased.
        content: The body as sent.
        reason: The reason phrase, when the transport reports one.
    """

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    content: bytes = b""
    reason: str = ""

    @property
    def ok(self) -> bool:
        """Whether the status is 2xx."""
        return 200 <= self.status < 300

    def json(self) -> Any:
        """The body parsed as JSON, ``None`` when it is empty.

        Raises:
            ValueError: When the body is not JSON.
        """
        if not self.content:
            return None
        return json.loads(self.content)


class TransportError(Exception):
    """The request got no HTTP answer: refused, unresolved, timed out or failed TLS."""


class Transport(Protocol):
    """Sends one request and returns the response, whatever its status."""

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        credentials: Mapping[str, str],
        content: bytes | None,
        timeout: float,
    ) -> Response:
        """Send one request.

        Args:
            method: The HTTP method.
            url: The absolute URL, query string included.
            headers: Request headers.
            credentials: Authentication headers, never sent on to a redirect target.
            content: The request body, if any.
            timeout: Seconds to wait for the answer.

        Returns:
            The response, 4xx and 5xx included.

        Raises:
            TransportError: When no HTTP answer arrived.
        """
        ...


def _lower(headers: Any) -> dict[str, str]:
    return {str(name).lower(): str(value) for name, value in headers.items()}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class UrllibTransport:
    """Standard-library transport with scalo's TLS posture and no retries.

    Credentials go on as unredirected headers, so a redirect never carries them
    to another host.

    Args:
        context: TLS context. ``None`` uses :func:`scalo.crypto.ssl_context`.
    """

    def __init__(self, *, context: ssl.SSLContext | None = None) -> None:
        self._context = context

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        credentials: Mapping[str, str],
        content: bytes | None,
        timeout: float,
    ) -> Response:
        """See :meth:`Transport.send`."""
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError(f"only http and https URLs are sent, not {url!r}")
        request = urllib.request.Request(url, data=content, method=method.upper())  # noqa: S310
        for name, value in headers.items():
            request.add_header(name, value)
        for name, value in credentials.items():
            request.add_unredirected_header(name, value)
        if self._context is None:
            from scalo.crypto import ssl_context

            self._context = ssl_context()
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self._context))
        try:
            with opener.open(request, timeout=timeout) as reply:
                return Response(reply.status, _lower(reply.headers), reply.read(), str(reply.reason or ""))
        except urllib.error.HTTPError as error:
            with error:
                return Response(error.code, _lower(error.headers), error.read(), str(error.reason or ""))
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", None) or error
            raise TransportError(f"could not reach {_origin(url)}: {reason}") from error


class ScaloHttpTransport:
    """Transport over :class:`scalo.http.HttpClient`, retrying only GET and HEAD.

    A retried POST, PUT, PATCH or DELETE could write twice, so those get one attempt.

    Args:
        retries: Attempts for a GET or HEAD.
        **client_kwargs: Passed to ``HttpClient``, such as ``crypto_profile`` or ``cafile``.

    Raises:
        ImportError: Without the ``http`` extra.
    """

    def __init__(self, *, retries: int = 3, **client_kwargs: Any) -> None:
        try:
            import httpx

            from scalo.http import HttpClient
        except ImportError as exc:
            raise ImportError("ScaloHttpTransport needs the 'http' extra: pip install 'scalo[http]'") from exc
        self._httpx = httpx
        self._client_class = HttpClient
        self._retries = retries
        self._client_kwargs = client_kwargs

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        credentials: Mapping[str, str],
        content: bytes | None,
        timeout: float,
    ) -> Response:
        """See :meth:`Transport.send`."""
        verb = method.upper()
        attempts = self._retries if verb in _IDEMPOTENT else 1
        httpx = self._httpx
        with self._client_class(timeout=timeout, retries=attempts, **self._client_kwargs) as client:
            send = getattr(client, verb.lower())
            try:
                reply = send(url, headers={**headers, **credentials}, content=content)
            except httpx.HTTPStatusError as error:
                reply = error.response
            except httpx.TransportError as error:
                raise TransportError(f"could not reach {_origin(url)}: {type(error).__name__}") from error
        return Response(reply.status_code, _lower(reply.headers), reply.content, reply.reason_phrase)
