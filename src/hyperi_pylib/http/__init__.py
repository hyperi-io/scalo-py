# Project:   hyperi-pylib
# File:      http/__init__.py
# Purpose:   HTTP client module with retries, timeouts, and observability
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
hyperi-pylib HTTP Client Module - Production HTTP with Retries and Observability.

Provides HTTP clients with automatic retries (via Stamina), default timeouts,
structured logging, and Prometheus metrics integration.

Quick Start:
    >>> from hyperi_pylib.http import HttpClient, AsyncHttpClient
    >>>
    >>> # Sync client
    >>> client = HttpClient(base_url="https://api.example.com")
    >>> response = client.get("/users/123")
    >>>
    >>> # Async client
    >>> async with AsyncHttpClient() as client:
    ...     response = await client.get("https://api.example.com/users")

Features:
    - Default 30s timeout (solves B113 bandit warnings)
    - Automatic retries with exponential backoff (via Stamina)
    - Prometheus metrics auto-detected
    - structlog integration auto-detected
    - Testing mode: stamina.set_testing(attempts=1)

Configuration:
    - timeout: Request timeout in seconds (default: 30.0)
    - retries: Number of retry attempts (default: 3)
    - base_url: Optional base URL for all requests

Dependencies:
    - httpx>=0.27
    - stamina>=25.1
"""

from .client import AsyncHttpClient, HttpClient, new_idempotency_key

__all__ = [
    "AsyncHttpClient",
    "HttpClient",
    "new_idempotency_key",
]
