# Project:   hyperi-pylib
# File:      tests/unit/test_secrets_aws_tier1.py
# Purpose:   Unit tests for AWS Secrets Manager Tier 1 + Tier 2 methods
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for AWS Secrets Manager Tier 1 + Tier 2 methods.

Uses moto's in-process AWS emulator (no Docker, no real AWS, no creds).
A ``mocked_aws`` fixture wraps each test so both sync (boto3) and async
(aiobotocore) calls go through the same fake AWS backend.
"""

from __future__ import annotations

import os

import pytest

from hyperi_pylib.secrets.exceptions import (
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretVersionNotFoundError,
)
from hyperi_pylib.secrets.providers.aws import AIOBOTOCORE_AVAILABLE, BOTO3_AVAILABLE, AWSProvider
from hyperi_pylib.secrets.types import AWSConfig, SecretFilter

try:
    from moto import mock_aws

    MOTO_AVAILABLE = True
except ImportError:
    MOTO_AVAILABLE = False
    mock_aws = None  # type: ignore[assignment]


pytestmark = [
    pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed"),
    pytest.mark.skipif(not MOTO_AVAILABLE, reason="moto not installed"),
]


REGION = "ap-southeast-2"


@pytest.fixture
def mocked_aws(monkeypatch):
    """Activate moto for the duration of one test; ensure dummy creds are present."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    with mock_aws():
        yield


@pytest.fixture
def provider(mocked_aws, monkeypatch) -> AWSProvider:
    """AWSProvider with aiobotocore disabled so async paths use the run_in_executor fallback.

    moto + aiobotocore 3.x have a long-standing incompat where moto returns the
    response body as sync bytes while aiobotocore tries to ``await`` it
    (``'bytes' object can't be awaited``). Forcing the sync fallback covers our
    async API contract (return shape, exception mapping) deterministically.
    Live aiobotocore is exercised by tests/integration/test_secrets_cloud_providers.py
    against real AWS when SSO creds are available.
    """
    import hyperi_pylib.secrets.providers.aws as aws_mod

    monkeypatch.setattr(aws_mod, "AIOBOTOCORE_AVAILABLE", False)
    return AWSProvider(AWSConfig(region=REGION))


# -------------------------------------------------------------------------
# create
# -------------------------------------------------------------------------


class TestAWSCreateSync:
    def test_happy_path_string_value(self, provider):
        meta = provider.create_sync("hyperi-test", b"hunter2")
        assert meta.name == "hyperi-test"
        assert meta.source == "aws"
        # AWS create_secret returns only ARN/Name/VersionId — created_at fills via describe
        assert meta.version is not None

    def test_with_tags(self, provider):
        meta = provider.create_sync("hyperi-tagged", b"x", tags={"env": "prod", "team": "platform"})
        assert meta.tags == {"env": "prod", "team": "platform"}
        described = provider.get_metadata_sync("hyperi-tagged")
        assert described.tags == {"env": "prod", "team": "platform"}
        assert described.created_at is not None

    def test_binary_value_round_trip(self, provider):
        binary = b"\xff\xfe\x00\x01"
        provider.create_sync("hyperi-binary", binary)
        value = provider.get_sync("hyperi-binary")
        assert value.data == binary

    def test_already_exists_raises(self, provider):
        provider.create_sync("hyperi-dup", b"first")
        with pytest.raises(SecretAlreadyExistsError):
            provider.create_sync("hyperi-dup", b"second")


class TestAWSCreateAsync:
    async def test_happy_path(self, provider):
        meta = await provider.create_async("hyperi-async", b"x")
        assert meta.name == "hyperi-async"

    async def test_already_exists(self, provider):
        await provider.create_async("hyperi-dup-a", b"first")
        with pytest.raises(SecretAlreadyExistsError):
            await provider.create_async("hyperi-dup-a", b"second")


# -------------------------------------------------------------------------
# get_metadata
# -------------------------------------------------------------------------


class TestAWSGetMetadataSync:
    def test_after_create(self, provider):
        provider.create_sync("hyperi-md", b"x", tags={"a": "b"})
        meta = provider.get_metadata_sync("hyperi-md")
        assert meta.name == "hyperi-md"
        assert meta.source == "aws"
        assert meta.created_at is not None
        assert meta.tags == {"a": "b"}
        assert meta.version is not None
        assert meta.version_count is not None and meta.version_count >= 1

    def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            provider.get_metadata_sync("does-not-exist")


class TestAWSGetMetadataAsync:
    async def test_happy_path(self, provider):
        await provider.create_async("hyperi-md-a", b"x")
        meta = await provider.get_metadata_async("hyperi-md-a")
        assert meta.name == "hyperi-md-a"
        assert meta.created_at is not None

    async def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            await provider.get_metadata_async("missing")


# -------------------------------------------------------------------------
# list
# -------------------------------------------------------------------------


class TestAWSListSync:
    def test_returns_all_when_no_filter(self, provider):
        provider.create_sync("alpha", b"x")
        provider.create_sync("beta", b"x")
        provider.create_sync("zeta", b"x")
        result = provider.list_sync()
        assert sorted(result) == ["alpha", "beta", "zeta"]

    def test_prefix_filter(self, provider):
        provider.create_sync("hyperi-alpha", b"x")
        provider.create_sync("hyperi-beta", b"x")
        provider.create_sync("other", b"x")
        result = provider.list_sync(SecretFilter(prefix="hyperi"))
        assert "hyperi-alpha" in result
        assert "hyperi-beta" in result
        assert "other" not in result

    def test_pattern_post_filter(self, provider):
        provider.create_sync("api_key", b"x")
        provider.create_sync("api_secret", b"x")
        provider.create_sync("password", b"x")
        result = provider.list_sync(SecretFilter(pattern="api*"))
        assert sorted(result) == ["api_key", "api_secret"]


class TestAWSListAsync:
    async def test_returns_all(self, provider):
        await provider.create_async("alpha", b"x")
        await provider.create_async("beta", b"x")
        result = await provider.list_async()
        assert sorted(result) == ["alpha", "beta"]


# -------------------------------------------------------------------------
# update
# -------------------------------------------------------------------------


class TestAWSUpdateSync:
    def test_happy_path(self, provider):
        provider.create_sync("hyperi-upd", b"v1")
        meta = provider.update_sync("hyperi-upd", b"v2")
        assert meta.name == "hyperi-upd"
        value = provider.get_sync("hyperi-upd")
        assert value.data == b"v2"

    def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            provider.update_sync("missing", b"x")


class TestAWSUpdateAsync:
    async def test_happy_path(self, provider):
        await provider.create_async("hyperi-upd-a", b"v1")
        meta = await provider.update_async("hyperi-upd-a", b"v2")
        assert meta.name == "hyperi-upd-a"

    async def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            await provider.update_async("missing", b"x")


# -------------------------------------------------------------------------
# delete
# -------------------------------------------------------------------------


class TestAWSDeleteSync:
    def test_happy_path_soft_delete(self, provider):
        provider.create_sync("hyperi-del", b"x")
        provider.delete_sync("hyperi-del")
        # Soft-deleted: get_secret_value should fail with InvalidRequestException → ProviderError
        # (the secret is still describe-able for the recovery window).
        # Explicitly verifying delete completed without raising is sufficient here.

    def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            provider.delete_sync("missing")


class TestAWSDeleteAsync:
    async def test_happy_path(self, provider):
        await provider.create_async("hyperi-del-a", b"x")
        await provider.delete_async("hyperi-del-a")

    async def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            await provider.delete_async("missing")


# -------------------------------------------------------------------------
# get_version
# -------------------------------------------------------------------------


class TestAWSGetVersionSync:
    def test_happy_path(self, provider):
        provider.create_sync("hyperi-vers", b"v1")
        meta = provider.get_metadata_sync("hyperi-vers")
        assert meta.version is not None
        result = provider.get_version_sync("hyperi-vers", meta.version)
        assert result.data == b"v1"

    def test_secret_not_found(self, provider):
        # AWS validates VersionId length (>=32) before contacting the service —
        # use a UUID-shaped string so the not-found path is exercised.
        with pytest.raises(SecretNotFoundError) as exc:
            provider.get_version_sync("missing", "00000000-0000-0000-0000-000000000000")
        assert not isinstance(exc.value, SecretVersionNotFoundError)


class TestAWSGetVersionAsync:
    async def test_happy_path(self, provider):
        await provider.create_async("hyperi-vers-a", b"v1")
        meta = await provider.get_metadata_async("hyperi-vers-a")
        result = await provider.get_version_async("hyperi-vers-a", meta.version)
        assert result.data == b"v1"


# -------------------------------------------------------------------------
# list_versions
# -------------------------------------------------------------------------


class TestAWSListVersionsSync:
    def test_returns_at_least_one(self, provider):
        provider.create_sync("hyperi-lv", b"v1")
        provider.update_sync("hyperi-lv", b"v2")
        versions = provider.list_versions_sync("hyperi-lv")
        assert len(versions) >= 1
        assert all(v.name == "hyperi-lv" for v in versions)
        assert all(v.source == "aws" for v in versions)

    @pytest.mark.skip(
        reason="moto raises KeyError instead of ResourceNotFoundException on "
        "list_secret_version_ids for a missing secret — real AWS returns "
        "ResourceNotFoundException; covered by live integration tests."
    )
    def test_not_found(self, provider):
        with pytest.raises(SecretNotFoundError):
            provider.list_versions_sync("missing")


class TestAWSListVersionsAsync:
    async def test_returns_versions(self, provider):
        await provider.create_async("hyperi-lv-a", b"v1")
        versions = await provider.list_versions_async("hyperi-lv-a")
        assert len(versions) >= 1


# -------------------------------------------------------------------------
# Native batch_get_async
# -------------------------------------------------------------------------


class TestAWSBatchGet:
    async def test_batch_returns_all_present(self, provider):
        await provider.create_async("batch-a", b"value-a")
        await provider.create_async("batch-b", b"value-b")
        await provider.create_async("batch-c", b"value-c")
        results = await provider.batch_get_async(["batch-a", "batch-b", "batch-c"])
        assert set(results.keys()) == {"batch-a", "batch-b", "batch-c"}
        assert results["batch-a"].data == b"value-a"
        assert results["batch-b"].data == b"value-b"
        assert results["batch-c"].data == b"value-c"

    async def test_empty_input_returns_empty(self, provider):
        assert await provider.batch_get_async([]) == {}


# -------------------------------------------------------------------------
# Encoding helpers (no AWS calls — don't need the fixture)
# -------------------------------------------------------------------------


class TestEncodeValue:
    def test_utf8_uses_secret_string(self):
        result = AWSProvider._encode_value(b"plain-utf8")
        assert result == {"SecretString": "plain-utf8"}

    def test_non_utf8_uses_secret_binary(self):
        binary = b"\xff\xfe\x00\x01"
        result = AWSProvider._encode_value(binary)
        assert result == {"SecretBinary": binary}


class TestBuildListFilters:
    def test_no_filter_returns_none(self):
        assert AWSProvider._build_list_filters(None) is None

    def test_empty_filter_returns_none(self):
        assert AWSProvider._build_list_filters(SecretFilter()) is None

    def test_prefix_only(self):
        result = AWSProvider._build_list_filters(SecretFilter(prefix="hyperi"))
        assert result == [{"Key": "name", "Values": ["hyperi"]}]

    def test_tags_expand_to_paired_filters(self):
        result = AWSProvider._build_list_filters(SecretFilter(tags={"env": "prod"}))
        assert {"Key": "tag-key", "Values": ["env"]} in (result or [])
        assert {"Key": "tag-value", "Values": ["prod"]} in (result or [])
