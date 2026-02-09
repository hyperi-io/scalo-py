# Project:   hyperi-pylib
# File:      http/client.py
# Purpose:   HTTP client implementations with retries and observability
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""HTTP client implementations with automatic retries, timeouts, and metrics."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from hyperi_pylib.logger import logger

# Default configuration
DEFAULT_TIMEOUT = 30.0  # Solves B113 bandit warnings
DEFAULT_RETRIES = 3


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
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request with retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL (absolute or relative to base_url)
            **kwargs: Additional arguments passed to httpx request

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: On non-retryable errors or after retries exhausted
        """

        backoff = 0.5
        for attempt in range(1, self._retries + 1):
            try:
                response = self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if 500 <= status < 600 and attempt < self._retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise
            except httpx.TransportError:
                if attempt < self._retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise

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
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute async HTTP request with retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL (absolute or relative to base_url)
            **kwargs: Additional arguments passed to httpx request

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: On non-retryable errors or after retries exhausted
        """

        backoff = 0.5
        for attempt in range(1, self._retries + 1):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if 500 <= status < 600 and attempt < self._retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise
            except httpx.TransportError:
                if attempt < self._retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise

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
