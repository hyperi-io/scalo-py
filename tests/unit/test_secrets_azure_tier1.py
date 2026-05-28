# Project:   hyperi-pylib
# File:      tests/unit/test_secrets_azure_tier1.py
# Purpose:   Unit tests for Azure Key Vault Tier 1 + Tier 2 helpers
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for Azure Key Vault Tier 1 + Tier 2 helpers.

Azure Key Vault has no official emulator. Per-method tests against a fake
HTTP layer are deferred to the integration suite. Coverage strategy:

- **Pure-logic helpers** are tested here (value encoding, tag matching,
  metadata mapping, post-filter, error classification).
- **Live behaviour** is exercised by ``tests/integration/test_secrets_cloud_providers.py``
  with the existing ``@requires_azure`` skip marker -- runs against real Key Vault
  when CLI auth is configured. Note: tenant is being recreated, so live tests
  will need a refresh once the new vault URL is available.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from hyperi_pylib.secrets.exceptions import ProviderError, SecretNotFoundError
from hyperi_pylib.secrets.providers.azure import AZURE_AVAILABLE, AzureProvider
from hyperi_pylib.secrets.types import AzureConfig, SecretFilter

pytestmark = pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")


VAULT_URL = "https://hyperi-test.vault.azure.net/"


@pytest.fixture
def provider() -> AzureProvider:
    return AzureProvider(AzureConfig(vault_url=VAULT_URL))


# -------------------------------------------------------------------------
# Value encoding
# -------------------------------------------------------------------------


class TestDecodeValueForStorage:
    def test_utf8_returns_string(self):
        assert AzureProvider._decode_value_for_storage(b"hello") == "hello"

    def test_unicode_utf8_returns_string(self):
        assert AzureProvider._decode_value_for_storage("café".encode()) == "café"

    def test_non_utf8_raises_provider_error(self):
        with pytest.raises(ProviderError) as exc:
            AzureProvider._decode_value_for_storage(b"\xff\xfe\x00\x01")
        assert "valid utf-8" in str(exc.value)


# -------------------------------------------------------------------------
# Tag matching
# -------------------------------------------------------------------------


class TestTagsMatch:
    def test_all_present_returns_true(self):
        assert AzureProvider._tags_match({"env": "prod", "team": "platform"}, {"env": "prod"}) is True

    def test_missing_key_returns_false(self):
        assert AzureProvider._tags_match({"env": "prod"}, {"team": "platform"}) is False

    def test_value_mismatch_returns_false(self):
        assert AzureProvider._tags_match({"env": "dev"}, {"env": "prod"}) is False

    def test_empty_want_returns_true(self):
        assert AzureProvider._tags_match({"any": "thing"}, {}) is True


# -------------------------------------------------------------------------
# Permission hint
# -------------------------------------------------------------------------


class TestPermissionHint:
    def test_format(self, provider):
        assert "Key Vault" in provider._azure_hint()
        assert "RBAC" in provider._azure_hint() or "policy" in provider._azure_hint()


# -------------------------------------------------------------------------
# Metadata mapping
# -------------------------------------------------------------------------


def _fake_props(
    name: str = "hyperi-test",
    *,
    version: str = "abc123",
    tags: dict | None = None,
    created_on: datetime | None = None,
    updated_on: datetime | None = None,
    expires_on: datetime | None = None,
):
    """Build an object that quacks like azure.keyvault.secrets.SecretProperties."""
    return SimpleNamespace(
        name=name,
        version=version,
        tags=tags,
        created_on=created_on or datetime(2025, 1, 15, tzinfo=UTC),
        updated_on=updated_on or datetime(2025, 2, 1, tzinfo=UTC),
        expires_on=expires_on,
    )


class TestPropsToMetadata:
    def test_basic_mapping(self, provider):
        props = _fake_props(name="foo", version="abc", tags={"env": "prod"})
        meta = provider._props_to_metadata(props)
        assert meta.name == "foo"
        assert meta.version == "abc"
        assert meta.tags == {"env": "prod"}
        assert meta.source == "azure"
        assert meta.created_at is not None
        assert meta.updated_at is not None

    def test_no_tags_means_none(self, provider):
        props = _fake_props(tags=None)
        meta = provider._props_to_metadata(props)
        assert meta.tags is None

    def test_empty_tags_means_none(self, provider):
        props = _fake_props(tags={})
        meta = provider._props_to_metadata(props)
        assert meta.tags is None

    def test_expires_on_propagates(self, provider):
        expires = datetime(2026, 1, 1, tzinfo=UTC)
        props = _fake_props(expires_on=expires)
        meta = provider._props_to_metadata(props)
        assert meta.expires_at == expires

    def test_fallback_name_when_props_name_empty(self, provider):
        props = _fake_props(name="")
        meta = provider._props_to_metadata(props, fallback_name="fb")
        assert meta.name == "fb"


# -------------------------------------------------------------------------
# Post-filter (client-side)
# -------------------------------------------------------------------------


class TestPostFilter:
    def test_no_filter_sorts(self, provider):
        assert provider._post_filter(["zeta", "alpha", "mu"], None) == ["alpha", "mu", "zeta"]

    def test_prefix_filter(self, provider):
        names = ["hyperi-a", "hyperi-b", "other"]
        assert provider._post_filter(names, SecretFilter(prefix="hyperi")) == ["hyperi-a", "hyperi-b"]

    def test_pattern_filter(self, provider):
        names = ["api_key", "api_secret", "password"]
        assert provider._post_filter(names, SecretFilter(pattern="api*")) == ["api_key", "api_secret"]

    def test_prefix_and_pattern_compound(self, provider):
        names = ["hyperi-api", "hyperi-other", "external-api"]
        result = provider._post_filter(names, SecretFilter(prefix="hyperi", pattern="*-api"))
        assert result == ["hyperi-api"]


# -------------------------------------------------------------------------
# Error classification
# -------------------------------------------------------------------------


class TestErrorClassification:
    def test_404_via_status_code_attr(self, provider):
        err = SimpleNamespace(status_code=404)
        assert provider._is_404(err) is True

    def test_404_via_response(self, provider):
        err = SimpleNamespace(response=SimpleNamespace(status_code=404))
        assert provider._is_404(err) is True

    def test_403_detection(self, provider):
        err = SimpleNamespace(status_code=403)
        assert provider._is_403(err) is True

    def test_500_is_neither(self, provider):
        err = SimpleNamespace(status_code=500)
        assert provider._is_404(err) is False
        assert provider._is_403(err) is False


# -------------------------------------------------------------------------
# JSON value parsing (existing helper)
# -------------------------------------------------------------------------


class TestParseValue:
    def test_no_key_returns_full(self, provider):
        assert provider._parse_value("the secret", "foo", None) == b"the secret"

    def test_extract_key_from_json(self, provider):
        result = provider._parse_value('{"api_key": "xyz", "other": "abc"}', "foo", "api_key")
        assert result == b"xyz"

    def test_missing_key_raises(self, provider):
        with pytest.raises(SecretNotFoundError):
            provider._parse_value('{"a": 1}', "foo", "b")

    def test_invalid_json_raises(self, provider):
        with pytest.raises(ProviderError):
            provider._parse_value("not json", "foo", "key")
