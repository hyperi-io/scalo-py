# Project:   hs-pylib
# File:      tests/unit/test_http.py
# Purpose:   Unit tests for hs_pylib.http module
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""Unit tests for hs_pylib.http module."""

import httpx
import pytest
import stamina

# Disable retries for faster tests
stamina.set_testing(True)


class TestHttpClient:
    """Tests for synchronous HttpClient."""

    def test_import(self):
        """Test that HttpClient can be imported."""
        from hs_pylib.http import HttpClient

        assert HttpClient is not None

    def test_init_defaults(self):
        """Test HttpClient initialises with defaults."""
        from hs_pylib.http import HttpClient

        client = HttpClient()
        assert client._timeout == 30.0
        assert client._retries == 3
        client.close()

    def test_init_custom_timeout(self):
        """Test HttpClient with custom timeout."""
        from hs_pylib.http import HttpClient

        client = HttpClient(timeout=60.0)
        assert client._timeout == 60.0
        client.close()

    def test_init_custom_retries(self):
        """Test HttpClient with custom retries."""
        from hs_pylib.http import HttpClient

        client = HttpClient(retries=5)
        assert client._retries == 5
        client.close()

    def test_init_with_base_url(self):
        """Test HttpClient with base URL."""
        from hs_pylib.http import HttpClient

        client = HttpClient(base_url="https://api.example.com")
        assert client._client.base_url == httpx.URL("https://api.example.com")
        client.close()

    def test_context_manager(self):
        """Test HttpClient as context manager."""
        from hs_pylib.http import HttpClient

        with HttpClient() as client:
            assert client is not None
            assert client._client is not None

    def test_get_request(self, httpx_mock):
        """Test GET request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="GET",
            url="https://api.example.com/users",
            json={"users": []},
        )

        with HttpClient() as client:
            response = client.get("https://api.example.com/users")
            assert response.status_code == 200
            assert response.json() == {"users": []}

    def test_post_request(self, httpx_mock):
        """Test POST request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="POST",
            url="https://api.example.com/users",
            json={"id": 1},
            status_code=201,
        )

        with HttpClient() as client:
            response = client.post(
                "https://api.example.com/users",
                json={"name": "Test User"},
            )
            assert response.status_code == 201
            assert response.json() == {"id": 1}

    def test_put_request(self, httpx_mock):
        """Test PUT request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="PUT",
            url="https://api.example.com/users/1",
            json={"id": 1, "name": "Updated"},
        )

        with HttpClient() as client:
            response = client.put(
                "https://api.example.com/users/1",
                json={"name": "Updated"},
            )
            assert response.status_code == 200

    def test_patch_request(self, httpx_mock):
        """Test PATCH request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="PATCH",
            url="https://api.example.com/users/1",
            json={"id": 1, "name": "Patched"},
        )

        with HttpClient() as client:
            response = client.patch(
                "https://api.example.com/users/1",
                json={"name": "Patched"},
            )
            assert response.status_code == 200

    def test_delete_request(self, httpx_mock):
        """Test DELETE request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="DELETE",
            url="https://api.example.com/users/1",
            status_code=204,
        )

        with HttpClient() as client:
            response = client.delete("https://api.example.com/users/1")
            assert response.status_code == 204

    def test_head_request(self, httpx_mock):
        """Test HEAD request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="HEAD",
            url="https://api.example.com/users",
        )

        with HttpClient() as client:
            response = client.head("https://api.example.com/users")
            assert response.status_code == 200

    def test_options_request(self, httpx_mock):
        """Test OPTIONS request."""
        from hs_pylib.http import HttpClient

        httpx_mock.add_response(
            method="OPTIONS",
            url="https://api.example.com/users",
        )

        with HttpClient() as client:
            response = client.options("https://api.example.com/users")
            assert response.status_code == 200


class TestAsyncHttpClient:
    """Tests for asynchronous AsyncHttpClient."""

    def test_import(self):
        """Test that AsyncHttpClient can be imported."""
        from hs_pylib.http import AsyncHttpClient

        assert AsyncHttpClient is not None

    def test_init_defaults(self):
        """Test AsyncHttpClient initialises with defaults."""
        from hs_pylib.http import AsyncHttpClient

        client = AsyncHttpClient()
        assert client._timeout == 30.0
        assert client._retries == 3

    def test_init_custom_timeout(self):
        """Test AsyncHttpClient with custom timeout."""
        from hs_pylib.http import AsyncHttpClient

        client = AsyncHttpClient(timeout=60.0)
        assert client._timeout == 60.0

    def test_init_custom_retries(self):
        """Test AsyncHttpClient with custom retries."""
        from hs_pylib.http import AsyncHttpClient

        client = AsyncHttpClient(retries=5)
        assert client._retries == 5

    def test_init_with_base_url(self):
        """Test AsyncHttpClient with base URL."""
        from hs_pylib.http import AsyncHttpClient

        client = AsyncHttpClient(base_url="https://api.example.com")
        assert client._client.base_url == httpx.URL("https://api.example.com")

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test AsyncHttpClient as async context manager."""
        from hs_pylib.http import AsyncHttpClient

        async with AsyncHttpClient() as client:
            assert client is not None
            assert client._client is not None

    @pytest.mark.asyncio
    async def test_async_get_request(self, httpx_mock):
        """Test async GET request."""
        from hs_pylib.http import AsyncHttpClient

        httpx_mock.add_response(
            method="GET",
            url="https://api.example.com/users",
            json={"users": []},
        )

        async with AsyncHttpClient() as client:
            response = await client.get("https://api.example.com/users")
            assert response.status_code == 200
            assert response.json() == {"users": []}

    @pytest.mark.asyncio
    async def test_async_post_request(self, httpx_mock):
        """Test async POST request."""
        from hs_pylib.http import AsyncHttpClient

        httpx_mock.add_response(
            method="POST",
            url="https://api.example.com/users",
            json={"id": 1},
            status_code=201,
        )

        async with AsyncHttpClient() as client:
            response = await client.post(
                "https://api.example.com/users",
                json={"name": "Test User"},
            )
            assert response.status_code == 201
            assert response.json() == {"id": 1}

    @pytest.mark.asyncio
    async def test_async_put_request(self, httpx_mock):
        """Test async PUT request."""
        from hs_pylib.http import AsyncHttpClient

        httpx_mock.add_response(
            method="PUT",
            url="https://api.example.com/users/1",
            json={"id": 1, "name": "Updated"},
        )

        async with AsyncHttpClient() as client:
            response = await client.put(
                "https://api.example.com/users/1",
                json={"name": "Updated"},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_async_delete_request(self, httpx_mock):
        """Test async DELETE request."""
        from hs_pylib.http import AsyncHttpClient

        httpx_mock.add_response(
            method="DELETE",
            url="https://api.example.com/users/1",
            status_code=204,
        )

        async with AsyncHttpClient() as client:
            response = await client.delete("https://api.example.com/users/1")
            assert response.status_code == 204
