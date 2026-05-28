# Project:   hyperi-pylib
# File:      tests/unit/test_secrets_gcp_tier1.py
# Purpose:   Unit tests for GCP Secret Manager Tier 1 + Tier 2 helpers
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for GCP Secret Manager Tier 1 + Tier 2 helpers.

GCP Secret Manager has no official emulator and uses gRPC, so per-method
unit tests against fake responses are out of scope (would require a fake
gRPC server). Coverage strategy:

- **Pure-logic helpers** are tested here (resource-name builders, filter
  translation, metadata mapping, datetime conversion).
- **Live behaviour** is exercised by ``tests/integration/test_secrets_cloud_providers.py``
  with the existing ``@requires_gcp`` skip marker -- runs against real GCP
  when ADC creds are present.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from hyperi_pylib.secrets.providers.gcp import GCP_AVAILABLE, GCPProvider
from hyperi_pylib.secrets.types import GCPConfig, SecretFilter

pytestmark = pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")


PROJECT = "hyperi-test-project"


@pytest.fixture
def provider() -> GCPProvider:
    return GCPProvider(GCPConfig(project_id=PROJECT))


# -------------------------------------------------------------------------
# Resource name builders
# -------------------------------------------------------------------------


class TestResourceNames:
    def test_parent(self, provider):
        assert provider._parent() == f"projects/{PROJECT}"

    def test_secret_name_from_short_path(self, provider):
        assert provider._secret_name("hyperi-test") == f"projects/{PROJECT}/secrets/hyperi-test"

    def test_secret_name_from_full_resource(self, provider):
        assert provider._secret_name(f"projects/other/secrets/foo") == "projects/other/secrets/foo"

    def test_secret_name_strips_versions_suffix(self, provider):
        assert provider._secret_name("projects/other/secrets/foo/versions/3") == "projects/other/secrets/foo"

    def test_version_resource_name_short(self, provider):
        assert (
            provider._version_resource_name("hyperi-test", "5") == f"projects/{PROJECT}/secrets/hyperi-test/versions/5"
        )

    def test_version_resource_name_latest(self, provider):
        assert (
            provider._version_resource_name("hyperi-test", "latest")
            == f"projects/{PROJECT}/secrets/hyperi-test/versions/latest"
        )

    def test_version_name_legacy_helper_short(self, provider):
        # _version_name (used by get_sync) appends /versions/latest if absent
        assert provider._version_name("hyperi-test") == f"projects/{PROJECT}/secrets/hyperi-test/versions/latest"


class TestShortName:
    def test_strips_full_resource(self):
        assert GCPProvider._short_name("projects/p/secrets/foo") == "foo"

    def test_strips_full_resource_with_version(self):
        assert GCPProvider._short_name("projects/p/secrets/foo/versions/3") == "foo"

    def test_returns_bare_name_unchanged(self):
        assert GCPProvider._short_name("foo") == "foo"


# -------------------------------------------------------------------------
# Filter translation
# -------------------------------------------------------------------------


class TestBuildFilter:
    def test_no_filter(self):
        assert GCPProvider._build_filter(None) == ""

    def test_empty_filter(self):
        assert GCPProvider._build_filter(SecretFilter()) == ""

    def test_prefix_only(self):
        assert GCPProvider._build_filter(SecretFilter(prefix="hyperi")) == "name:hyperi"

    def test_tags_only(self):
        result = GCPProvider._build_filter(SecretFilter(tags={"env": "prod"}))
        assert result == "labels.env=prod"

    def test_prefix_and_tags_joined(self):
        result = GCPProvider._build_filter(SecretFilter(prefix="hyperi", tags={"env": "prod"}))
        assert "name:hyperi" in result
        assert "labels.env=prod" in result
        assert " AND " in result


class TestPostFilter:
    def test_no_filter_sorts(self, provider):
        assert provider._post_filter(["zeta", "alpha", "mu"], None) == ["alpha", "mu", "zeta"]

    def test_pattern_filters_and_sorts(self, provider):
        names = ["api_key", "api_secret", "password"]
        assert provider._post_filter(names, SecretFilter(pattern="api*")) == ["api_key", "api_secret"]

    def test_no_pattern_sorts(self, provider):
        assert provider._post_filter(["b", "a"], SecretFilter()) == ["a", "b"]


# -------------------------------------------------------------------------
# Metadata mapping
# -------------------------------------------------------------------------


def _fake_secret(name: str, *, labels: dict | None = None, create_time: datetime | None = None):
    """Build a SimpleNamespace that mimics google.cloud.secretmanager_v1.types.Secret enough for our mapper."""
    return SimpleNamespace(
        name=name,
        labels=labels or {},
        create_time=create_time or datetime(2025, 1, 15, tzinfo=UTC),
        expire_time=None,
    )


def _fake_version(
    name: str, *, create_time: datetime | None = None, destroy_time: datetime | None = None, state: str = "ENABLED"
):
    return SimpleNamespace(
        name=name,
        create_time=create_time or datetime(2025, 2, 1, tzinfo=UTC),
        destroy_time=destroy_time,
        state=state,
    )


class TestSecretToMetadata:
    def test_basic_mapping(self, provider):
        secret = _fake_secret(f"projects/{PROJECT}/secrets/foo", labels={"env": "prod", "team": "platform"})
        meta = provider._secret_to_metadata(secret)
        assert meta.name == "foo"
        assert meta.tags == {"env": "prod", "team": "platform"}
        assert meta.source == "gcp"
        assert meta.created_at is not None

    def test_no_labels_means_no_tags(self, provider):
        secret = _fake_secret(f"projects/{PROJECT}/secrets/foo", labels={})
        meta = provider._secret_to_metadata(secret)
        assert meta.tags is None

    def test_version_count_passed_through(self, provider):
        secret = _fake_secret(f"projects/{PROJECT}/secrets/foo")
        meta = provider._secret_to_metadata(secret, version_count=5)
        assert meta.version_count == 5


class TestVersionToMetadata:
    def test_extracts_version_id(self, provider):
        v = _fake_version(f"projects/{PROJECT}/secrets/foo/versions/3")
        meta = provider._version_to_metadata(v, f"projects/{PROJECT}/secrets/foo")
        assert meta.version == "3"
        assert meta.name == "foo"
        assert meta.source == "gcp"

    def test_destroy_time_overrides_updated_at(self, provider):
        destroy = datetime(2025, 3, 1, tzinfo=UTC)
        v = _fake_version(f"projects/{PROJECT}/secrets/foo/versions/2", destroy_time=destroy)
        meta = provider._version_to_metadata(v, f"projects/{PROJECT}/secrets/foo")
        assert meta.updated_at == destroy


# -------------------------------------------------------------------------
# Datetime conversion
# -------------------------------------------------------------------------


class TestDatetimeFromProtobuf:
    def test_none_returns_none(self):
        assert GCPProvider._dt_from_protobuf(None) is None

    def test_naive_datetime_gets_utc(self):
        naive = datetime(2025, 1, 15, 12, 0, 0)
        result = GCPProvider._dt_from_protobuf(naive)
        assert result is not None
        assert result.tzinfo is not None

    def test_aware_datetime_preserved(self):
        aware = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert GCPProvider._dt_from_protobuf(aware) == aware

    def test_seconds_nanos_object(self):
        ts = SimpleNamespace(seconds=1737000000, nanos=500_000_000)
        result = GCPProvider._dt_from_protobuf(ts)
        assert result is not None
        assert result.tzinfo is UTC


# -------------------------------------------------------------------------
# Permission hint
# -------------------------------------------------------------------------


class TestPermissionHint:
    def test_format(self, provider):
        assert provider._gcp_hint("create") == "check IAM role for secretmanager.secrets.create"

    def test_includes_operation(self, provider):
        assert "delete" in provider._gcp_hint("delete")


# -------------------------------------------------------------------------
# Payload extraction (existing helper exercised via Tier 2 path)
# -------------------------------------------------------------------------


class TestParsePayload:
    def test_no_key_returns_raw(self, provider):
        assert provider._parse_payload(b"raw bytes", "secret/foo", None) == b"raw bytes"

    def test_extract_key_from_json(self, provider):
        result = provider._parse_payload(b'{"api_key": "xyz", "other": "abc"}', "secret/foo", "api_key")
        assert result == b"xyz"

    def test_missing_key_raises(self, provider):
        from hyperi_pylib.secrets.exceptions import SecretNotFoundError

        with pytest.raises(SecretNotFoundError):
            provider._parse_payload(b'{"a": 1}', "secret/foo", "b")

    def test_invalid_json_raises(self, provider):
        from hyperi_pylib.secrets.exceptions import ProviderError

        with pytest.raises(ProviderError):
            provider._parse_payload(b"not json", "secret/foo", "key")
