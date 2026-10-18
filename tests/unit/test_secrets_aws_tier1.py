# Project:   scalo
# File:      tests/unit/test_secrets_aws_tier1.py
# Purpose:   Unit tests for AWS Secrets Manager Tier 1 + Tier 2 methods
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for AWS Secrets Manager Tier 1 + Tier 2 methods.

Uses moto's in-process AWS emulator (no Docker, no real AWS, no creds).
A ``mocked_aws`` fixture wraps each test so both sync (boto3) and async
(aiobotocore) calls go through the same fake AWS backend.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest

from scalo.secrets.exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPendingDeletionError,
    SecretVersionNotFoundError,
)
from scalo.secrets.manager import SecretsManager
from scalo.secrets.providers.aws import AIOBOTOCORE_AVAILABLE, BOTO3_AVAILABLE, AWSProvider
from scalo.secrets.types import AWSConfig, SecretFilter

try:
    from moto import mock_aws

    MOTO_AVAILABLE = True
except ImportError:
    # pytestmark skips every test, so the fixture never reaches mock_aws.
    MOTO_AVAILABLE = False


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


def _sync_only_provider(monkeypatch, config: AWSConfig) -> AWSProvider:
    """AWSProvider with aiobotocore disabled so async paths use the run_in_executor fallback.

    moto + aiobotocore 3.x have a long-standing incompat where moto returns the
    response body as sync bytes while aiobotocore tries to ``await`` it
    (``'bytes' object can't be awaited``). Forcing the sync fallback covers our
    async API contract (return shape, exception mapping) deterministically.
    Live aiobotocore is exercised by tests/integration/test_secrets_cloud_providers.py
    against real AWS when SSO creds are available.
    """
    import scalo.secrets.providers.aws as aws_mod

    monkeypatch.setattr(aws_mod, "AIOBOTOCORE_AVAILABLE", False)
    return AWSProvider(config)


@pytest.fixture
def provider(mocked_aws, monkeypatch) -> AWSProvider:
    """AWSProvider on the default config, sync fallback only."""
    return _sync_only_provider(monkeypatch, AWSConfig(region=REGION))


def _record_params(provider: AWSProvider, operation: str) -> list[dict]:
    """Collect the parameters of every ``operation`` call the provider's sync client sends."""
    sent: list[dict] = []
    provider._get_sync_client().meta.events.register(
        f"provide-client-params.secretsmanager.{operation}",
        lambda params, **_: sent.append(dict(params)),
    )
    return sent


# -------------------------------------------------------------------------
# create
# -------------------------------------------------------------------------


class TestAWSCreateSync:
    def test_happy_path_string_value(self, provider):
        meta = provider.create_sync("hyperi-test", b"hunter2")
        assert meta.name == "hyperi-test"
        assert meta.source == "aws"
        # AWS create_secret returns only ARN/Name/VersionId -- created_at fills via describe
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
        assert meta.version_count is not None
        assert meta.version_count >= 1

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
        # Still describe-able for the recovery window, but no longer readable.
        assert provider.get_metadata_sync("hyperi-del").name == "hyperi-del"
        with pytest.raises(SecretPendingDeletionError):
            provider.get_sync("hyperi-del")

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
        # AWS validates VersionId length (>=32) before contacting the service --
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
        "list_secret_version_ids for a missing secret -- real AWS returns "
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

    async def test_missing_secret_is_logged_and_omitted(self, provider, caplog):
        await provider.create_async("batch-present", b"value-present")
        caplog.set_level("WARNING", logger="scalo.secrets.providers.aws")
        results = await provider.batch_get_async(["batch-present", "batch-missing"])
        assert set(results) == {"batch-present"}
        errors = [r for r in caplog.records if r.getMessage() == "AWS batch_get error"]
        assert len(errors) == 1
        assert errors[0].secret_id == "batch-missing"
        assert errors[0].code == "ResourceNotFoundException"
        assert errors[0].error_message
        assert "value-present" not in " ".join(str(v) for v in vars(errors[0]).values())

    async def test_partial_failure_logs_never_carry_a_secret_value(self, provider, caplog):
        fake_value = "fake-secret-value-3c9e1a"
        await provider.create_async("batch-held", fake_value.encode("utf-8"))
        caplog.set_level("DEBUG", logger="scalo")
        results = await provider.batch_get_async(["batch-held", "batch-absent"])
        assert results["batch-held"].data == fake_value.encode("utf-8")
        scalo_records = [r for r in caplog.records if r.name.startswith("scalo")]
        assert any(r.getMessage() == "AWS batch_get error" for r in scalo_records)
        for record in scalo_records:
            assert fake_value not in record.getMessage()
            assert fake_value not in " ".join(str(v) for v in vars(record).values())


# -------------------------------------------------------------------------
# Encoding helpers (no AWS calls -- don't need the fixture)
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


# -------------------------------------------------------------------------
# Customer KMS key
# -------------------------------------------------------------------------


class TestAWSKmsKey:
    def test_create_encrypts_with_the_configured_key(self, mocked_aws, monkeypatch):
        provider = _sync_only_provider(monkeypatch, AWSConfig(region=REGION, kms_key_id="alias/scalo-test"))
        provider.create_sync("hyperi-kms", b"x")
        described = provider._get_sync_client().describe_secret(SecretId="hyperi-kms")
        assert described["KmsKeyId"] == "alias/scalo-test"

    async def test_create_async_encrypts_with_the_configured_key(self, mocked_aws, monkeypatch):
        provider = _sync_only_provider(monkeypatch, AWSConfig(region=REGION, kms_key_id="alias/scalo-test"))
        await provider.create_async("hyperi-kms-a", b"x")
        described = provider._get_sync_client().describe_secret(SecretId="hyperi-kms-a")
        assert described["KmsKeyId"] == "alias/scalo-test"

    def test_no_key_leaves_the_aws_managed_key(self, provider):
        sent = _record_params(provider, "CreateSecret")
        provider.create_sync("hyperi-no-kms", b"x")
        described = provider._get_sync_client().describe_secret(SecretId="hyperi-no-kms")
        assert "KmsKeyId" not in described
        assert "KmsKeyId" not in sent[0]


# -------------------------------------------------------------------------
# Deletion recovery window
# -------------------------------------------------------------------------


class TestAWSRecoveryWindow:
    def test_unset_window_sends_neither_parameter(self, provider):
        sent = _record_params(provider, "DeleteSecret")
        provider.create_sync("hyperi-default-window", b"x")
        provider.delete_sync("hyperi-default-window")
        assert sent == [{"SecretId": "hyperi-default-window"}]

    def test_zero_forces_the_delete_and_frees_the_name(self, mocked_aws, monkeypatch):
        provider = _sync_only_provider(monkeypatch, AWSConfig(region=REGION, recovery_window_days=0))
        sent = _record_params(provider, "DeleteSecret")
        provider.create_sync("hyperi-force", b"v1")
        provider.delete_sync("hyperi-force")
        assert sent == [{"SecretId": "hyperi-force", "ForceDeleteWithoutRecovery": True}]
        provider.create_sync("hyperi-force", b"v2")
        assert provider.get_sync("hyperi-force").data == b"v2"

    async def test_zero_forces_the_delete_async(self, mocked_aws, monkeypatch):
        provider = _sync_only_provider(monkeypatch, AWSConfig(region=REGION, recovery_window_days=0))
        await provider.create_async("hyperi-force-a", b"v1")
        await provider.delete_async("hyperi-force-a")
        await provider.create_async("hyperi-force-a", b"v2")
        assert (await provider.get_async("hyperi-force-a")).data == b"v2"

    def test_seven_days_schedules_the_deletion(self, mocked_aws, monkeypatch):
        provider = _sync_only_provider(monkeypatch, AWSConfig(region=REGION, recovery_window_days=7))
        sent = _record_params(provider, "DeleteSecret")
        provider.create_sync("hyperi-window", b"x")
        requested_at = datetime.now(UTC)
        provider.delete_sync("hyperi-window")
        assert sent == [{"SecretId": "hyperi-window", "RecoveryWindowInDays": 7}]
        described = provider._get_sync_client().describe_secret(SecretId="hyperi-window")
        assert described["DeletedDate"] is not None
        # moto records the end of the window as DeletedDate.
        assert timedelta(days=6) < described["DeletedDate"] - requested_at < timedelta(days=8)


# -------------------------------------------------------------------------
# A name pending deletion
# -------------------------------------------------------------------------


def _stub_client_error(provider: AWSProvider, operation: str, message: str):
    """Make the provider's sync client answer ``operation`` with an InvalidRequestException."""
    from botocore.stub import Stubber

    stubber = Stubber(provider._get_sync_client())
    stubber.add_client_error(
        operation,
        service_error_code="InvalidRequestException",
        service_message=message,
        http_status_code=400,
    )
    return stubber


class TestAWSPendingDeletion:
    def test_read_inside_the_window_is_named(self, provider):
        provider.create_sync("hyperi-pending-read", b"x")
        provider.delete_sync("hyperi-pending-read")
        with pytest.raises(SecretPendingDeletionError) as exc:
            provider.get_sync("hyperi-pending-read")
        assert isinstance(exc.value, ProviderError)
        assert exc.value.operation == "GetSecretValue"
        assert exc.value.path == "hyperi-pending-read"
        assert "scheduled for deletion" in str(exc.value)

    async def test_read_async_inside_the_window_is_named(self, provider):
        await provider.create_async("hyperi-pending-read-a", b"x")
        await provider.delete_async("hyperi-pending-read-a")
        with pytest.raises(SecretPendingDeletionError):
            await provider.get_async("hyperi-pending-read-a")

    def test_versioned_read_inside_the_window_is_named(self, provider):
        meta = provider.create_sync("hyperi-pending-version", b"x")
        provider.delete_sync("hyperi-pending-version")
        with pytest.raises(SecretPendingDeletionError):
            provider.get_version_sync("hyperi-pending-version", meta.version)

    def test_update_inside_the_window_is_named(self, provider):
        provider.create_sync("hyperi-pending-update", b"x")
        provider.delete_sync("hyperi-pending-update")
        with pytest.raises(SecretPendingDeletionError) as exc:
            provider.update_sync("hyperi-pending-update", b"y")
        assert exc.value.operation == "UpdateSecret"

    def test_create_on_a_name_inside_the_window_is_named(self, provider):
        # moto answers this CreateSecret with ResourceExistsException, so AWS's own answer is stubbed.
        message = "You can't create this secret because a secret with this name is already scheduled for deletion."
        with _stub_client_error(provider, "create_secret", message), pytest.raises(SecretPendingDeletionError) as exc:
            provider.create_sync("hyperi-pending-create", b"x")
        assert exc.value.operation == "CreateSecret"
        assert exc.value.path == "hyperi-pending-create"

    def test_other_invalid_requests_stay_provider_errors(self, provider):
        message = "You can't perform this operation on the secret because it is managed by another service."
        with _stub_client_error(provider, "create_secret", message), pytest.raises(ProviderError) as exc:
            provider.create_sync("hyperi-managed", b"x")
        assert not isinstance(exc.value, SecretPendingDeletionError)


# -------------------------------------------------------------------------
# Region resolution
# -------------------------------------------------------------------------


@pytest.fixture
def no_region(mocked_aws, monkeypatch, tmp_path):
    """No region from config, environment or a profile, with moto active so nothing reaches AWS."""
    for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "absent-config"))


class TestAWSRegion:
    def test_config_region_wins(self, no_region, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        assert SecretsManager._parse_aws_config({"region": REGION}).region == REGION

    def test_aws_region_wins_over_default_region(self, no_region, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
        assert SecretsManager._parse_aws_config({}).region == "eu-west-1"

    def test_default_region_alone_selects_the_region(self, no_region, monkeypatch):
        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
        config = SecretsManager._parse_aws_config({})
        assert config.region == "eu-west-2"
        provider = _sync_only_provider(monkeypatch, config)
        assert provider._get_sync_client().meta.region_name == "eu-west-2"

    def test_no_region_anywhere_is_never_us_east_1(self, no_region, monkeypatch):
        from botocore.exceptions import NoRegionError

        config = SecretsManager._parse_aws_config({})
        assert config.region is None
        provider = _sync_only_provider(monkeypatch, config)
        assert "region_name" not in provider._get_client_kwargs()
        # The SDK chain finds nothing and refuses, rather than reaching a default region.
        with pytest.raises(NoRegionError):
            provider._get_sync_client()

    def test_from_config_passes_the_new_keys(self, no_region):
        manager = SecretsManager.from_config(
            {"aws": {"region": REGION, "kms_key_id": "alias/scalo-test", "recovery_window_days": 0}}
        )
        provider = manager._providers["aws"]
        assert isinstance(provider, AWSProvider)
        assert provider._config.kms_key_id == "alias/scalo-test"
        assert provider._config.recovery_window_days == 0

    def test_from_config_refuses_an_out_of_range_window(self, no_region):
        with pytest.raises(ValueError, match="recovery_window_days"):
            SecretsManager.from_config({"aws": {"region": REGION, "recovery_window_days": 3}})
