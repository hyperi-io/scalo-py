# Project:   hyperi-pylib
# File:      tests/integration/test_secrets_openbao_tier1.py
# Purpose:   Integration tests for OpenBao Tier 1 + Tier 2 against real KV v2 wire protocol
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Integration tests for OpenBao Tier 1 + Tier 2 methods.

Uses the ``openbao_endpoint`` fixture from conftest.py -- cascade of:
1. Existing local Vault on :8200 → use it
2. ``docker compose -f docker-compose.openbao.yml up -d`` → spawn one
3. Skip the test class if neither available

Validates the actual KV v2 wire protocol against a real Vault binary, which
unit tests (httpx-stubbed) cannot. One round-trip per Tier 1 method covers
the contract.
"""

from __future__ import annotations

import uuid

import pytest

from hyperi_pylib.secrets.exceptions import (
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretVersionNotFoundError,
)
from hyperi_pylib.secrets.providers.openbao import HTTPX_AVAILABLE, OpenBaoProvider
from hyperi_pylib.secrets.types import OpenBaoConfig, SecretFilter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed"),
]


@pytest.fixture
def provider(openbao_endpoint) -> OpenBaoProvider:
    addr, token = openbao_endpoint
    return OpenBaoProvider(OpenBaoConfig(address=addr, auth_method="token", token=token))


def _unique_path(suffix: str) -> str:
    """Per-test unique path so tests can run in parallel without collision."""
    return f"secret/hyperi-pylib-test/{uuid.uuid4().hex[:8]}/{suffix}"


class TestOpenBaoTier1Roundtrip:
    """Single round-trip per Tier 1 method against a real Vault binary."""

    def test_create_get_metadata_update_delete_roundtrip(self, provider):
        path = _unique_path("roundtrip")

        # create
        meta = provider.create_sync(path, b"value-v1", tags={"env": "test"})
        assert meta.name == path
        assert meta.version == "1"
        assert meta.tags == {"env": "test"}

        # get_metadata reflects custom_metadata + version
        md = provider.get_metadata_sync(path)
        assert md.version == "1"
        assert md.tags == {"env": "test"}
        assert md.created_at is not None

        # update creates a new version
        meta2 = provider.update_sync(path, b"value-v2")
        assert meta2.version == "2"

        # get returns latest
        value = provider.get_sync(path, key="value")
        assert value.decode() == "value-v2"

        # delete (full destroy)
        provider.delete_sync(path)
        with pytest.raises(SecretNotFoundError):
            provider.get_metadata_sync(path)

    def test_create_already_exists(self, provider):
        path = _unique_path("dup")
        provider.create_sync(path, b"x")
        try:
            with pytest.raises(SecretAlreadyExistsError):
                provider.create_sync(path, b"y")
        finally:
            provider.delete_sync(path)

    def test_update_not_found(self, provider):
        path = _unique_path("missing-update")
        with pytest.raises(SecretNotFoundError):
            provider.update_sync(path, b"x")

    def test_delete_not_found(self, provider):
        path = _unique_path("missing-delete")
        with pytest.raises(SecretNotFoundError):
            provider.delete_sync(path)


class TestOpenBaoTier2Versioning:
    """Tier 2 (versioned) methods against real Vault."""

    def test_get_version_and_list_versions(self, provider):
        path = _unique_path("versions")
        try:
            provider.create_sync(path, b"v1")
            provider.update_sync(path, b"v2")
            provider.update_sync(path, b"v3")

            versions = provider.list_versions_sync(path)
            assert [v.version for v in versions] == ["3", "2", "1"]

            # Specific version round-trip
            v1 = provider.get_version_sync(path, "1", key="value")
            assert v1.decode() == "v1"

            v2 = provider.get_version_sync(path, "2", key="value")
            assert v2.decode() == "v2"
        finally:
            provider.delete_sync(path)

    def test_get_version_not_found(self, provider):
        path = _unique_path("v-404")
        try:
            provider.create_sync(path, b"v1")
            with pytest.raises(SecretVersionNotFoundError):
                provider.get_version_sync(path, "99")
        finally:
            provider.delete_sync(path)

    def test_list_versions_secret_not_found(self, provider):
        path = _unique_path("missing-versions")
        with pytest.raises(SecretNotFoundError):
            provider.list_versions_sync(path)


class TestOpenBaoListing:
    """Listing under a prefix works against real Vault LIST verb."""

    def test_list_under_prefix(self, provider):
        prefix_path = f"secret/hyperi-pylib-test/list-{uuid.uuid4().hex[:8]}"
        names = ["alpha", "beta", "gamma"]
        try:
            for n in names:
                provider.create_sync(f"{prefix_path}/{n}", b"x")

            result = provider.list_sync(SecretFilter(prefix=prefix_path))
            assert sorted(result) == sorted(names)
        finally:
            for n in names:
                try:
                    provider.delete_sync(f"{prefix_path}/{n}")
                except SecretNotFoundError:
                    pass

    def test_list_pattern_post_filter(self, provider):
        prefix_path = f"secret/hyperi-pylib-test/pattern-{uuid.uuid4().hex[:8]}"
        names = ["api_key", "api_secret", "password"]
        try:
            for n in names:
                provider.create_sync(f"{prefix_path}/{n}", b"x")

            result = provider.list_sync(SecretFilter(prefix=prefix_path, pattern="api*"))
            assert sorted(result) == ["api_key", "api_secret"]
        finally:
            for n in names:
                try:
                    provider.delete_sync(f"{prefix_path}/{n}")
                except SecretNotFoundError:
                    pass


class TestOpenBaoAsyncRoundtrip:
    """Async path against real Vault -- proves the httpx async client wiring."""

    async def test_async_create_get_delete(self, provider):
        path = _unique_path("async-rt")
        meta = await provider.create_async(path, b"async-value", tags={"async": "true"})
        assert meta.version == "1"

        value = await provider.get_async(path, key="value")
        assert value.decode() == "async-value"

        await provider.delete_async(path)
        with pytest.raises(SecretNotFoundError):
            await provider.get_metadata_async(path)
