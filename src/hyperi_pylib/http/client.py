# Project:   hyperi-pylib
# File:      http/client.py
# Purpose:   HTTP client implementations with retries and observability
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""HTTP client implementations with automatic retries, timeouts, and metrics.

Uses Stamina for retries -- exponential backoff with jitter, structlog/Prometheus
auto-detection, and ``stamina.set_testing(...)`` for deterministic test runs.

**Composition with CircuitBreaker** -- when stacking, put the breaker
OUTSIDE the retry context:

    with breaker:
        for attempt in stamina.retry_context(...):
            with attempt:
                response = client.get(url)

That way the retry budget is consumed inside one breaker call, and a
fully-failed retry budget counts as ONE failure to the breaker -- not
N. Reversing the order (retry around breaker) means each rejection
from an OPEN breaker eats a retry slot, which is wasteful and slow.

**Distributed tracing** -- callers can pass ``traceparent=<header>``
to inject a W3C trace-context header on a single request, or wire it
globally via httpx event hooks at construction time (see
``HttpClient.__init__`` extras).

**Idempotent retries** -- POST/PATCH retries are unsafe by default
because a retried request may have already landed. To opt in, pass
``idempotency_key="<uuid>"`` per request; the value is sent as the
``Idempotency-Key`` header and downstream services that support the
pattern (Stripe, AWS, etc.) deduplicate on it.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import stamina

from hyperi_pylib.logger import logger

# Default configuration
DEFAULT_TIMEOUT = 30.0  # Solves B113 bandit warnings
DEFAULT_RETRIES = 3


def _is_retryable(exc: BaseException) -> bool:
    """Retry on transport errors and 5xx server errors. Never retry on 4xx client errors."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return False


def _apply_request_headers(
    kwargs: dict[str, Any],
    traceparent: str | None,
    idempotency_key: str | None,
) -> None:
    """Inject W3C traceparent + Idempotency-Key headers if provided."""
    if traceparent is None and idempotency_key is None:
        return
    headers = dict(kwargs.get("headers") or {})
    if traceparent is not None:
        headers["traceparent"] = traceparent
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    kwargs["headers"] = headers


def new_idempotency_key() -> str:
    """Generate a random Idempotency-Key (UUIDv4) suitable for POST/PATCH retry safety."""
    return str(uuid.uuid4())


class HttpClient:
    """Synchronous HTTP client with retries, timeouts, and observability.

    Features:
        - Default 30s timeout (configurable)
        - Automatic retries with exponential backoff via Stamina
        - Prometheus metrics auto-detected by Stamina
        - structlog integration auto-detected by Stamina

    Usage:
        >>> client = HttpClient(base_url="https://api.example.com")
        >>> response = client.get("/users/123")
        >>> data = response.json()

        >>> # With custom settings
        >>> client = HttpClient(timeout=60.0, retries=5)
        >>> response = client.post("/data", json={"key": "value"})

    Testing:
        >>> import stamina
        >>> stamina.set_testing(True)  # Disables retries in tests
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        **client_kwargs: Any,
    ) -> None:
        """Initialise HTTP client.

        Args:
            base_url: Base URL for all requests (optional)
            timeout: Request timeout in seconds (default: 30.0)
            retries: Number of retry attempts (default: 3)
            **client_kwargs: Additional arguments passed to httpx.Client
        """
        self._timeout = timeout
        self._retries = retries
        self._client = httpx.Client(
            base_url=base_url or "",
            timeout=httpx.Timeout(timeout),
            **client_kwargs,
        )
        logger.debug(
            "HTTP client initialised",
            base_url=base_url,
            timeout=timeout,
            retries=retries,
        )

    def __enter__(self) -> HttpClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit - close client."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        self._client.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        traceparent: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request with stamina-driven retries.

        Retries on transport errors and 5xx responses with exponential backoff
        and jitter. 4xx responses surface immediately.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL (absolute or relative to base_url)
            traceparent: Optional W3C trace-context header (e.g. propagated
                from an OTel current span via TraceContextTextMapPropagator).
                When set, the SAME traceparent goes on every retry.
            idempotency_key: Optional Idempotency-Key header value for
                retry-safe POST/PATCH. Use :func:`new_idempotency_key` to
                generate one. The same key is sent on every retry, so
                downstream services that honour the pattern deduplicate.
            **kwargs: Additional arguments passed to httpx request

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: On non-retryable errors or after retries exhausted
        """
        _apply_request_headers(kwargs, traceparent, idempotency_key)
        for attempt in stamina.retry_context(
            on=_is_retryable,
            attempts=self._retries,
            wait_initial=0.5,
            wait_max=10.0,
            wait_jitter=1.0,
        ):
            with attempt:
                response = self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
        # Unreachable: stamina.retry_context always raises on exhaustion
        raise RuntimeError("retry context exhausted without raising")  # pragma: no cover

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send GET request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (params, headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send POST request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (json, data, headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send PUT request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (json, data, headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send PATCH request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (json, data, headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send DELETE request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send HEAD request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send OPTIONS request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (headers, etc.)

        Returns:
            httpx.Response object
        """
        return self._request("OPTIONS", url, **kwargs)


class AsyncHttpClient:
    """Asynchronous HTTP client with retries, timeouts, and observability.

    Features:
        - Default 30s timeout (configurable)
        - Automatic retries with exponential backoff via Stamina
        - Prometheus metrics auto-detected by Stamina
        - structlog integration auto-detected by Stamina

    Usage:
        >>> async with AsyncHttpClient(base_url="https://api.example.com") as client:
        ...     response = await client.get("/users/123")
        ...     data = response.json()

        >>> # Or manage lifecycle manually
        >>> client = AsyncHttpClient()
        >>> try:
        ...     response = await client.get("https://api.example.com/users")
        ... finally:
        ...     await client.aclose()

    Testing:
        >>> import stamina
        >>> stamina.set_testing(True)  # Disables retries in tests
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        **client_kwargs: Any,
    ) -> None:
        """Initialise async HTTP client.

        Args:
            base_url: Base URL for all requests (optional)
            timeout: Request timeout in seconds (default: 30.0)
            retries: Number of retry attempts (default: 3)
            **client_kwargs: Additional arguments passed to httpx.AsyncClient
        """
        self._timeout = timeout
        self._retries = retries
        self._client = httpx.AsyncClient(
            base_url=base_url or "",
            timeout=httpx.Timeout(timeout),
            **client_kwargs,
        )
        logger.debug(
            "Async HTTP client initialised",
            base_url=base_url,
            timeout=timeout,
            retries=retries,
        )

    async def __aenter__(self) -> AsyncHttpClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit - close client."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the async HTTP client and release resources."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        traceparent: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute async HTTP request with stamina-driven retries.

        See ``HttpClient._request`` for retry policy + traceparent /
        idempotency_key semantics.
        """
        _apply_request_headers(kwargs, traceparent, idempotency_key)
        async for attempt in stamina.retry_context(
            on=_is_retryable,
            attempts=self._retries,
            wait_initial=0.5,
            wait_max=10.0,
            wait_jitter=1.0,
        ):
            with attempt:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
        raise RuntimeError("retry context exhausted without raising")  # pragma: no cover

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async GET request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (params, headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async POST request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (json, data, headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async PUT request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (json, data, headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async PATCH request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (json, data, headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async DELETE request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("DELETE", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async HEAD request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("HEAD", url, **kwargs)

    async def options(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send async OPTIONS request.

        Args:
            url: Request URL
            **kwargs: Additional arguments (headers, etc.)

        Returns:
            httpx.Response object
        """
        return await self._request("OPTIONS", url, **kwargs)
