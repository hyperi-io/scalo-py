# Project:   hyperi-pylib
# File:      tests/unit/test_secrets_openbao_tier1.py
# Purpose:   Unit tests for OpenBao Tier 1 + Tier 2 (versioned) methods
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for OpenBao Tier 1 + Tier 2 provider methods.

Uses pytest-httpx to fake KV v2 endpoints at the httpx transport level —
no mocks, no real Vault required.
"""

from __future__ import annotations

import base64

import pytest

from hyperi_pylib.secrets.exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
    SecretVersionNotFoundError,
)
from hyperi_pylib.secrets.providers.openbao import HTTPX_AVAILABLE, OpenBaoProvider
from hyperi_pylib.secrets.types import OpenBaoConfig, SecretFilter

pytestmark = pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")

VAULT_ADDR = "http://vault.test:8200"
VAULT_TOKEN = "test-token-42"  # noqa: S105
KV_DATA_URL = f"{VAULT_ADDR}/v1/secret/data/myapp"
KV_META_URL = f"{VAULT_ADDR}/v1/secret/metadata/myapp"
KV_LIST_URL = f"{VAULT_ADDR}/v1/secret/metadata/myapp/"


@pytest.fixture
def provider() -> OpenBaoProvider:
    return OpenBaoProvider(OpenBaoConfig(address=VAULT_ADDR, auth_method="token", token=VAULT_TOKEN))


def _meta_response(
    *,
    current_version: int = 3,
    versions: dict | None = None,
    custom_metadata: dict | None = None,
    created_time: str = "2025-01-01T00:00:00.000000Z",
    updated_time: str = "2025-02-01T00:00:00.000000Z",
) -> dict:
    """Canonical KV v2 GET /metadata/ response shape."""
    if versions is None:
        versions = {
            "1": {"created_time": "2025-01-01T00:00:00.000000Z", "deletion_time": "", "destroyed": False},
            "2": {"created_time": "2025-01-15T00:00:00.000000Z", "deletion_time": "", "destroyed": False},
            "3": {"created_time": "2025-02-01T00:00:00.000000Z", "deletion_time": "", "destroyed": False},
        }
    return {
        "data": {
            "created_time": created_time,
            "current_version": current_version,
            "max_versions": 0,
            "oldest_version": 0,
            "updated_time": updated_time,
            "custom_metadata": custom_metadata,
            "versions": versions,
        }
    }


def _post_response(version: int, created_time: str = "2025-02-15T00:00:00.000000Z") -> dict:
    """Canonical KV v2 POST /data/ response shape."""
    return {
        "data": {
            "created_time": created_time,
            "deletion_time": "",
            "destroyed": False,
            "version": version,
        }
    }


# -------------------------------------------------------------------------
# list
# -------------------------------------------------------------------------


class TestListSync:
    def test_returns_leaf_keys_sorted(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="LIST",
            url=KV_LIST_URL,
            json={"data": {"keys": ["zeta", "alpha", "subdir/", "mu"]}},
        )
        result = provider.list_sync(SecretFilter(prefix="secret/myapp"))
        assert result == ["alpha", "mu", "zeta"]

    def test_pattern_post_filter(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="LIST",
            url=KV_LIST_URL,
            json={"data": {"keys": ["api_key", "password", "config", "api_secret"]}},
        )
        result = provider.list_sync(SecretFilter(prefix="secret/myapp", pattern="api*"))
        assert result == ["api_key", "api_secret"]

    def test_no_prefix_returns_empty(self, provider):
        assert provider.list_sync(SecretFilter()) == []

    def test_no_filter_returns_empty(self, provider):
        assert provider.list_sync() == []

    def test_404_returns_empty(self, provider, httpx_mock):
        httpx_mock.add_response(method="LIST", url=KV_LIST_URL, status_code=404)
        assert provider.list_sync(SecretFilter(prefix="secret/myapp")) == []

    def test_403_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="LIST", url=KV_LIST_URL, status_code=403)
        with pytest.raises(SecretPermissionError) as exc:
            provider.list_sync(SecretFilter(prefix="secret/myapp"))
        assert exc.value.operation == "list"
        assert exc.value.path == "secret/myapp"
        assert "Vault policy" in (exc.value.hint or "")

    def test_500_raises_provider_error(self, provider, httpx_mock):
        httpx_mock.add_response(method="LIST", url=KV_LIST_URL, status_code=500)
        with pytest.raises(ProviderError):
            provider.list_sync(SecretFilter(prefix="secret/myapp"))


class TestListAsync:
    async def test_returns_leaf_keys_sorted(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="LIST",
            url=KV_LIST_URL,
            json={"data": {"keys": ["beta", "alpha"]}},
        )
        result = await provider.list_async(SecretFilter(prefix="secret/myapp"))
        assert result == ["alpha", "beta"]

    async def test_403_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="LIST", url=KV_LIST_URL, status_code=403)
        with pytest.raises(SecretPermissionError):
            await provider.list_async(SecretFilter(prefix="secret/myapp"))


# -------------------------------------------------------------------------
# get_metadata
# -------------------------------------------------------------------------


class TestGetMetadataSync:
    def test_happy_path_populates_all_fields(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=KV_META_URL,
            json=_meta_response(current_version=3, custom_metadata={"env": "prod"}),
        )
        meta = provider.get_metadata_sync("secret/myapp")
        assert meta.name == "secret/myapp"
        assert meta.version == "3"
        assert meta.version_count == 3
        assert meta.tags == {"env": "prod"}
        assert meta.source == "openbao"
        assert meta.created_at is not None
        assert meta.updated_at is not None

    def test_404_raises_not_found(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            provider.get_metadata_sync("secret/myapp")

    def test_403_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=403)
        with pytest.raises(SecretPermissionError) as exc:
            provider.get_metadata_sync("secret/myapp")
        assert exc.value.operation == "read"

    def test_no_custom_metadata_means_no_tags(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=KV_META_URL,
            json=_meta_response(custom_metadata=None),
        )
        meta = provider.get_metadata_sync("secret/myapp")
        assert meta.tags is None


class TestGetMetadataAsync:
    async def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        meta = await provider.get_metadata_async("secret/myapp")
        assert meta.version == "3"

    async def test_404(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            await provider.get_metadata_async("secret/myapp")


# -------------------------------------------------------------------------
# create
# -------------------------------------------------------------------------


class TestCreateSync:
    def test_happy_path_utf8_value(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=KV_DATA_URL,
            json=_post_response(version=1),
            match_json={"data": {"value": "secret-value"}, "options": {"cas": 0}},
        )
        meta = provider.create_sync("secret/myapp", b"secret-value")
        assert meta.name == "secret/myapp"
        assert meta.version == "1"
        assert meta.tags is None
        assert meta.source == "openbao"

    def test_with_tags_makes_two_calls(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=KV_DATA_URL,
            json=_post_response(version=1),
            match_json={"data": {"value": "x"}, "options": {"cas": 0}},
        )
        httpx_mock.add_response(
            method="POST",
            url=KV_META_URL,
            status_code=204,
            match_json={"custom_metadata": {"env": "prod", "team": "platform"}},
        )
        meta = provider.create_sync("secret/myapp", b"x", tags={"env": "prod", "team": "platform"})
        assert meta.tags == {"env": "prod", "team": "platform"}

    def test_non_utf8_uses_base64_envelope(self, provider, httpx_mock):
        binary = b"\xff\xfe\x00\x01"  # invalid utf-8
        expected_b64 = base64.b64encode(binary).decode("ascii")
        httpx_mock.add_response(
            method="POST",
            url=KV_DATA_URL,
            json=_post_response(version=1),
            match_json={"data": {"value_b64": expected_b64}, "options": {"cas": 0}},
        )
        meta = provider.create_sync("secret/myapp", binary)
        assert meta.version == "1"

    def test_cas_conflict_raises_already_exists(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=KV_DATA_URL,
            status_code=400,
            json={"errors": ["check-and-set parameter did not match the current version"]},
        )
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync("secret/myapp", b"x")

    def test_403_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="POST", url=KV_DATA_URL, status_code=403)
        with pytest.raises(SecretPermissionError) as exc:
            provider.create_sync("secret/myapp", b"x")
        assert exc.value.operation == "create"

    def test_500_raises_provider_error(self, provider, httpx_mock):
        httpx_mock.add_response(method="POST", url=KV_DATA_URL, status_code=500)
        with pytest.raises(ProviderError):
            provider.create_sync("secret/myapp", b"x")


class TestCreateAsync:
    async def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(method="POST", url=KV_DATA_URL, json=_post_response(version=1))
        meta = await provider.create_async("secret/myapp", b"x")
        assert meta.version == "1"

    async def test_cas_conflict(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="POST",
            url=KV_DATA_URL,
            status_code=400,
            json={"errors": ["check-and-set parameter did not match the current version"]},
        )
        with pytest.raises(SecretAlreadyExistsError):
            await provider.create_async("secret/myapp", b"x")


# -------------------------------------------------------------------------
# update
# -------------------------------------------------------------------------


class TestUpdateSync:
    def test_happy_path(self, provider, httpx_mock):
        # Pre-existence check
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response(current_version=3))
        # Actual update POST (no cas)
        httpx_mock.add_response(
            method="POST",
            url=KV_DATA_URL,
            json=_post_response(version=4),
            match_json={"data": {"value": "new-value"}},
        )
        meta = provider.update_sync("secret/myapp", b"new-value")
        assert meta.version == "4"

    def test_not_found_via_precheck(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            provider.update_sync("secret/myapp", b"x")

    def test_403_on_write_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        httpx_mock.add_response(method="POST", url=KV_DATA_URL, status_code=403)
        with pytest.raises(SecretPermissionError) as exc:
            provider.update_sync("secret/myapp", b"x")
        assert exc.value.operation == "update"


class TestUpdateAsync:
    async def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        httpx_mock.add_response(method="POST", url=KV_DATA_URL, json=_post_response(version=4))
        meta = await provider.update_async("secret/myapp", b"x")
        assert meta.version == "4"

    async def test_not_found(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            await provider.update_async("secret/myapp", b"x")


# -------------------------------------------------------------------------
# delete
# -------------------------------------------------------------------------


class TestDeleteSync:
    def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        httpx_mock.add_response(method="DELETE", url=KV_META_URL, status_code=204)
        provider.delete_sync("secret/myapp")  # no exception

    def test_not_found_via_precheck(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            provider.delete_sync("secret/myapp")

    def test_403_on_delete_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        httpx_mock.add_response(method="DELETE", url=KV_META_URL, status_code=403)
        with pytest.raises(SecretPermissionError) as exc:
            provider.delete_sync("secret/myapp")
        assert exc.value.operation == "delete"


class TestDeleteAsync:
    async def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        httpx_mock.add_response(method="DELETE", url=KV_META_URL, status_code=200)
        await provider.delete_async("secret/myapp")

    async def test_not_found(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            await provider.delete_async("secret/myapp")


# -------------------------------------------------------------------------
# get_version
# -------------------------------------------------------------------------


def _kv_data_response(value: str = "the-secret", version: int = 2) -> dict:
    return {
        "data": {
            "data": {"value": value},
            "metadata": {
                "created_time": "2025-01-15T00:00:00.000000Z",
                "deletion_time": "",
                "destroyed": False,
                "version": version,
            },
        }
    }


class TestGetVersionSync:
    def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=f"{KV_DATA_URL}?version=2",
            json=_kv_data_response(value="version-two", version=2),
        )
        result = provider.get_version_sync("secret/myapp", "2", key="value")
        assert result.decode() == "version-two"
        assert result.version == "2"

    def test_version_not_found_when_secret_exists(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=f"{KV_DATA_URL}?version=99", status_code=404)
        # disambiguator call: secret exists
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response())
        with pytest.raises(SecretVersionNotFoundError) as exc:
            provider.get_version_sync("secret/myapp", "99")
        assert exc.value.version == "99"

    def test_secret_not_found(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=f"{KV_DATA_URL}?version=2", status_code=404)
        # disambiguator: secret missing too
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError) as exc:
            provider.get_version_sync("secret/myapp", "2")
        assert not isinstance(exc.value, SecretVersionNotFoundError)


class TestGetVersionAsync:
    async def test_happy_path(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=f"{KV_DATA_URL}?version=2", json=_kv_data_response())
        result = await provider.get_version_async("secret/myapp", "2", key="value")
        assert result.decode() == "the-secret"


# -------------------------------------------------------------------------
# list_versions
# -------------------------------------------------------------------------


class TestListVersionsSync:
    def test_returns_newest_first(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response(current_version=3))
        versions = provider.list_versions_sync("secret/myapp")
        assert [v.version for v in versions] == ["3", "2", "1"]
        assert all(v.name == "secret/myapp" for v in versions)
        assert all(v.source == "openbao" for v in versions)

    def test_404_raises_not_found(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=404)
        with pytest.raises(SecretNotFoundError):
            provider.list_versions_sync("secret/myapp")

    def test_403_raises_permission(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, status_code=403)
        with pytest.raises(SecretPermissionError):
            provider.list_versions_sync("secret/myapp")

    def test_tags_propagate_to_each_version(self, provider, httpx_mock):
        httpx_mock.add_response(
            method="GET",
            url=KV_META_URL,
            json=_meta_response(custom_metadata={"team": "platform"}),
        )
        versions = provider.list_versions_sync("secret/myapp")
        assert all(v.tags == {"team": "platform"} for v in versions)


class TestListVersionsAsync:
    async def test_newest_first(self, provider, httpx_mock):
        httpx_mock.add_response(method="GET", url=KV_META_URL, json=_meta_response(current_version=3))
        versions = await provider.list_versions_async("secret/myapp")
        assert [v.version for v in versions] == ["3", "2", "1"]


# -------------------------------------------------------------------------
# Path normalisation
# -------------------------------------------------------------------------


class TestPathNormalisation:
    def test_metadata_path_for_bare_path(self, provider):
        assert provider._normalize_metadata_path("secret/myapp/config") == "/v1/secret/metadata/myapp/config"

    def test_metadata_path_swaps_data_for_metadata(self, provider):
        assert provider._normalize_metadata_path("secret/data/myapp") == "/v1/secret/metadata/myapp"

    def test_metadata_path_passes_through_qualified(self, provider):
        assert provider._normalize_metadata_path("v1/secret/metadata/x") == "/v1/secret/metadata/x"

    def test_list_path_appends_trailing_slash(self, provider):
        assert provider._normalize_list_path("secret/myapp").endswith("/")

    def test_encode_value_utf8(self):
        assert OpenBaoProvider._encode_value_for_storage(b"hello") == {"value": "hello"}

    def test_encode_value_non_utf8_uses_b64(self):
        result = OpenBaoProvider._encode_value_for_storage(b"\xff\xfe")
        assert "value_b64" in result
        assert "value" not in result
