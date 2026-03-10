# Project:   hyperi-pylib
# File:      tests/integration/test_secrets_cloud_providers.py
# Purpose:   Integration tests for cloud secrets providers (AWS, GCP, Azure, Vault)
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Integration tests for cloud secrets providers against real provider endpoints.

Tests gracefully skip when the required credentials or env vars are not configured.
Failed tests do NOT block the build — developers without access to specific cloud
accounts simply skip those tests.

Configuration via environment variables (or tests/.env.integration file):

    # AWS Secrets Manager
    HYPERI_TEST_AWS_REGION=ap-southeast-2
    HYPERI_TEST_AWS_SECRET_NAME=hyperi-pylib-test
    # Credentials: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY + AWS_SESSION_TOKEN
    # Via SSO: eval $(aws configure export-credentials --profile hypersec-internet-services --format env)

    # GCP Secret Manager
    HYPERI_TEST_GCP_PROJECT_ID=hyperi-dfe
    HYPERI_TEST_GCP_SECRET_NAME=hyperi-pylib-test
    # Credentials: gcloud auth application-default login

    # Azure Key Vault
    HYPERI_TEST_AZURE_VAULT_URL=https://hyperi-pylib-test.vault.azure.net/
    HYPERI_TEST_AZURE_SECRET_NAME=hyperi-pylib-test
    # Credentials: az login (ensure AZURE_CLIENT_SECRET is unset if stale)

    # OpenBao / Vault
    HYPERI_TEST_VAULT_ADDR=https://bao.devex.hyperi.io:8200
    HYPERI_TEST_VAULT_TOKEN=<token>
    HYPERI_TEST_VAULT_PATH=secret/data/hyperi-pylib-test
    HYPERI_TEST_VAULT_KEY=api_key

Copy tests/.env.integration.example to tests/.env.integration and fill in values.

Run with:
    pytest tests/integration/test_secrets_cloud_providers.py -v -m integration
"""

import os
from pathlib import Path

import pytest

# Load tests/.env.integration if present — per-developer config without env pollution
_env_file = Path(__file__).parent / ".env.integration"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Test config from env
# ---------------------------------------------------------------------------

AWS_REGION = os.environ.get("HYPERI_TEST_AWS_REGION", "ap-southeast-2")
AWS_SECRET_NAME = os.environ.get("HYPERI_TEST_AWS_SECRET_NAME", "hyperi-pylib-test")

GCP_PROJECT_ID = os.environ.get("HYPERI_TEST_GCP_PROJECT_ID", "hyperi-dfe")
GCP_SECRET_NAME = os.environ.get("HYPERI_TEST_GCP_SECRET_NAME", "hyperi-pylib-test")

AZURE_VAULT_URL = os.environ.get("HYPERI_TEST_AZURE_VAULT_URL", "https://hyperi-pylib-test.vault.azure.net/")
AZURE_SECRET_NAME = os.environ.get("HYPERI_TEST_AZURE_SECRET_NAME", "hyperi-pylib-test")

VAULT_ADDR = os.environ.get("HYPERI_TEST_VAULT_ADDR", "")
VAULT_TOKEN = os.environ.get("HYPERI_TEST_VAULT_TOKEN", "")
VAULT_PATH = os.environ.get("HYPERI_TEST_VAULT_PATH", "secret/data/hyperi-pylib-test")
VAULT_KEY = os.environ.get("HYPERI_TEST_VAULT_KEY", "api_key")

EXPECTED_API_KEY = "test-value-abc123"
EXPECTED_OTHER_KEY = "other-value"

# ---------------------------------------------------------------------------
# Credential availability checks
# ---------------------------------------------------------------------------


def _aws_creds_available() -> bool:
    """True when short-lived AWS credentials are present (SSO-exported or CI)."""
    return bool(
        os.environ.get("AWS_ACCESS_KEY_ID")
        and os.environ.get("AWS_SECRET_ACCESS_KEY")
        and os.environ.get("AWS_SESSION_TOKEN")
    )


def _gcp_creds_available() -> bool:
    """True when GCP ADC credentials are configured."""
    adc_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if adc_file:
        return Path(adc_file).exists()
    home_adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return home_adc.exists()


def _azure_creds_available() -> bool:
    """True when Azure CLI credentials are present and no stale client secret overrides them."""
    if os.environ.get("AZURE_CLIENT_SECRET"):
        # Stale service principal secret overrides CLI auth and will fail
        return False
    msal_cache = Path.home() / ".azure" / "msal_token_cache.json"
    access_tokens = Path.home() / ".azure" / "accessTokens.json"
    return msal_cache.exists() or access_tokens.exists()


def _vault_creds_available() -> bool:
    """True when Vault address and token are configured."""
    return bool(VAULT_ADDR and VAULT_TOKEN)


requires_aws = pytest.mark.skipif(
    not _aws_creds_available(),
    reason="AWS credentials not available (need AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY + AWS_SESSION_TOKEN)",
)

requires_gcp = pytest.mark.skipif(
    not _gcp_creds_available(),
    reason="GCP ADC not configured (run: gcloud auth application-default login)",
)

requires_azure = pytest.mark.skipif(
    not _azure_creds_available(),
    reason="Azure CLI credentials not available or AZURE_CLIENT_SECRET is set (run: az login)",
)

requires_vault = pytest.mark.skipif(
    not _vault_creds_available(),
    reason="Vault credentials not configured (set HYPERI_TEST_VAULT_ADDR and HYPERI_TEST_VAULT_TOKEN)",
)


# ---------------------------------------------------------------------------
# Provider imports — skip entire module if secrets extra not installed
# ---------------------------------------------------------------------------

try:
    from hyperi_pylib.secrets import (
        AWSConfig,
        AzureConfig,
        GCPConfig,
        OpenBaoConfig,
        SecretsManager,
    )
    from hyperi_pylib.secrets.exceptions import SecretNotFoundError
    from hyperi_pylib.secrets.providers import (
        AIOBOTOCORE_AVAILABLE,
        AZURE_AVAILABLE,
        BOTO3_AVAILABLE,
        GCP_AVAILABLE,
        AWSProvider,
        AzureProvider,
        GCPProvider,
        OpenBaoProvider,
    )
except ImportError as _e:
    pytest.skip(f"secrets module not importable: {_e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# AWS Provider
# ---------------------------------------------------------------------------


class TestAWSProviderIntegration:
    """Real AWS Secrets Manager tests — skipped when credentials not available."""

    def _provider(self) -> "AWSProvider":
        return AWSProvider(AWSConfig(region=AWS_REGION))

    @requires_aws
    @pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
    def test_get_sync_key_extraction(self):
        """Extract api_key from JSON secret."""
        value = self._provider().get_sync(AWS_SECRET_NAME, key="api_key")
        assert value.decode() == EXPECTED_API_KEY
        assert value.source == "aws"

    @requires_aws
    @pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
    def test_get_sync_other_key(self):
        """Extract second key from JSON secret."""
        value = self._provider().get_sync(AWS_SECRET_NAME, key="other_key")
        assert value.decode() == EXPECTED_OTHER_KEY

    @requires_aws
    @pytest.mark.skipif(not AIOBOTOCORE_AVAILABLE, reason="aiobotocore not installed")
    @pytest.mark.asyncio
    async def test_get_async_key_extraction(self):
        """Async key extraction from JSON secret."""
        value = await self._provider().get_async(AWS_SECRET_NAME, key="api_key")
        assert value.decode() == EXPECTED_API_KEY
        assert value.source == "aws"

    @requires_aws
    @pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
    def test_health_check_sync(self):
        assert self._provider().health_check_sync() is True

    @requires_aws
    @pytest.mark.skipif(not AIOBOTOCORE_AVAILABLE, reason="aiobotocore not installed")
    @pytest.mark.asyncio
    async def test_health_check_async(self):
        assert await self._provider().health_check_async() is True

    @requires_aws
    @pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
    def test_from_config_secrets_manager(self):
        """SecretsManager.from_config with AWS provider."""
        manager = SecretsManager.from_config(
            {
                "aws": {"region": AWS_REGION},
                "sources": {"api_key": {"provider": "aws", "secret_id": AWS_SECRET_NAME, "key": "api_key"}},
                "cache": {"enabled": False},
            }
        )
        assert manager.get_sync("api_key").decode() == EXPECTED_API_KEY

    @requires_aws
    @pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
    def test_env_fallback_when_aws_secret_missing(self, monkeypatch):
        """ENV fallback when AWS secret does not exist."""
        monkeypatch.setenv("FALLBACK_KEY", "aws-fallback-value")
        manager = SecretsManager.from_config(
            {
                "aws": {"region": AWS_REGION},
                "sources": {
                    "missing": {
                        "provider": "aws",
                        "secret_id": "this-secret-does-not-exist-hyperi-pylib",
                        "env_fallback": "FALLBACK_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("missing")
        assert value.decode() == "aws-fallback-value"
        assert value.source == "env"


# ---------------------------------------------------------------------------
# GCP Provider
# ---------------------------------------------------------------------------


class TestGCPProviderIntegration:
    """Real GCP Secret Manager tests — skipped when ADC not configured."""

    def _provider(self) -> "GCPProvider":
        return GCPProvider(GCPConfig(project_id=GCP_PROJECT_ID))

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    def test_get_sync_key_extraction(self):
        """Extract api_key from JSON secret."""
        value = self._provider().get_sync(GCP_SECRET_NAME, key="api_key")
        assert value.decode() == EXPECTED_API_KEY
        assert value.source == "gcp"

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    def test_get_sync_other_key(self):
        """Extract second key from JSON secret."""
        value = self._provider().get_sync(GCP_SECRET_NAME, key="other_key")
        assert value.decode() == EXPECTED_OTHER_KEY

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    @pytest.mark.asyncio
    async def test_get_async_key_extraction(self):
        """Async key extraction from JSON secret."""
        value = await self._provider().get_async(GCP_SECRET_NAME, key="api_key")
        assert value.decode() == EXPECTED_API_KEY
        assert value.source == "gcp"

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    def test_health_check_sync(self):
        assert self._provider().health_check_sync() is True

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    @pytest.mark.asyncio
    async def test_health_check_async(self):
        assert await self._provider().health_check_async() is True

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    def test_from_config_secrets_manager(self):
        """SecretsManager.from_config with GCP provider."""
        manager = SecretsManager.from_config(
            {
                "gcp": {"project_id": GCP_PROJECT_ID},
                "sources": {"api_key": {"provider": "gcp", "path": GCP_SECRET_NAME, "key": "api_key"}},
                "cache": {"enabled": False},
            }
        )
        assert manager.get_sync("api_key").decode() == EXPECTED_API_KEY

    @requires_gcp
    @pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
    def test_env_fallback_when_gcp_secret_missing(self, monkeypatch):
        """ENV fallback when GCP secret does not exist."""
        monkeypatch.setenv("FALLBACK_KEY", "gcp-fallback-value")
        manager = SecretsManager.from_config(
            {
                "gcp": {"project_id": GCP_PROJECT_ID},
                "sources": {
                    "missing": {
                        "provider": "gcp",
                        "path": "this-secret-does-not-exist-hyperi-pylib",
                        "env_fallback": "FALLBACK_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("missing")
        assert value.decode() == "gcp-fallback-value"
        assert value.source == "env"


# ---------------------------------------------------------------------------
# Azure Provider
# ---------------------------------------------------------------------------


class TestAzureProviderIntegration:
    """Real Azure Key Vault tests — skipped when CLI credentials not configured."""

    def _provider(self) -> "AzureProvider":
        return AzureProvider(AzureConfig(vault_url=AZURE_VAULT_URL))

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    def test_get_sync_key_extraction(self):
        """Extract api_key from JSON secret."""
        value = self._provider().get_sync(AZURE_SECRET_NAME, key="api_key")
        assert value.decode() == EXPECTED_API_KEY
        assert value.source == "azure"

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    def test_get_sync_other_key(self):
        """Extract second key from JSON secret."""
        value = self._provider().get_sync(AZURE_SECRET_NAME, key="other_key")
        assert value.decode() == EXPECTED_OTHER_KEY

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    @pytest.mark.asyncio
    async def test_get_async_key_extraction(self):
        """Async key extraction from JSON secret."""
        provider = self._provider()
        try:
            value = await provider.get_async(AZURE_SECRET_NAME, key="api_key")
            assert value.decode() == EXPECTED_API_KEY
            assert value.source == "azure"
        finally:
            await provider.close()

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    def test_health_check_sync(self):
        assert self._provider().health_check_sync() is True

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    @pytest.mark.asyncio
    async def test_health_check_async(self):
        provider = self._provider()
        try:
            assert await provider.health_check_async() is True
        finally:
            await provider.close()

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    def test_from_config_secrets_manager(self):
        """SecretsManager.from_config with Azure provider."""
        manager = SecretsManager.from_config(
            {
                "azure": {"vault_url": AZURE_VAULT_URL},
                "sources": {"api_key": {"provider": "azure", "path": AZURE_SECRET_NAME, "key": "api_key"}},
                "cache": {"enabled": False},
            }
        )
        assert manager.get_sync("api_key").decode() == EXPECTED_API_KEY

    @requires_azure
    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
    def test_env_fallback_when_azure_secret_missing(self, monkeypatch):
        """ENV fallback when Azure secret does not exist."""
        monkeypatch.setenv("FALLBACK_KEY", "azure-fallback-value")
        manager = SecretsManager.from_config(
            {
                "azure": {"vault_url": AZURE_VAULT_URL},
                "sources": {
                    "missing": {
                        "provider": "azure",
                        "path": "this-secret-does-not-exist-hyperi-pylib",
                        "env_fallback": "FALLBACK_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("missing")
        assert value.decode() == "azure-fallback-value"
        assert value.source == "env"


# ---------------------------------------------------------------------------
# OpenBao / Vault Provider
# ---------------------------------------------------------------------------


class TestVaultProviderIntegration:
    """Real OpenBao/Vault tests — skipped when VAULT_ADDR and VAULT_TOKEN not set."""

    def _provider(self) -> "OpenBaoProvider":
        return OpenBaoProvider(
            OpenBaoConfig(
                address=VAULT_ADDR,
                auth_method="token",
                token=VAULT_TOKEN,
            )
        )

    @requires_vault
    def test_get_sync_key_extraction(self):
        """Extract key from Vault KV secret."""
        value = self._provider().get_sync(VAULT_PATH, key=VAULT_KEY)
        assert value.source == "openbao"
        assert len(value.decode()) > 0

    @requires_vault
    @pytest.mark.asyncio
    async def test_get_async_key_extraction(self):
        """Async key extraction from Vault KV secret."""
        value = await self._provider().get_async(VAULT_PATH, key=VAULT_KEY)
        assert value.source == "openbao"
        assert len(value.decode()) > 0

    @requires_vault
    def test_health_check_sync(self):
        assert self._provider().health_check_sync() is True

    @requires_vault
    @pytest.mark.asyncio
    async def test_health_check_async(self):
        assert await self._provider().health_check_async() is True

    @requires_vault
    def test_from_config_secrets_manager(self):
        """SecretsManager.from_config with Vault provider."""
        manager = SecretsManager.from_config(
            {
                "openbao": {"address": VAULT_ADDR, "auth": {"method": "token", "token": VAULT_TOKEN}},
                "sources": {"vault_key": {"provider": "openbao", "path": VAULT_PATH, "key": VAULT_KEY}},
                "cache": {"enabled": False},
            }
        )
        assert len(manager.get_sync("vault_key").decode()) > 0

    @requires_vault
    def test_env_fallback_when_vault_path_missing(self, monkeypatch):
        """ENV fallback when Vault path does not exist."""
        monkeypatch.setenv("FALLBACK_KEY", "vault-fallback-value")
        manager = SecretsManager.from_config(
            {
                "openbao": {"address": VAULT_ADDR, "auth": {"method": "token", "token": VAULT_TOKEN}},
                "sources": {
                    "missing": {
                        "provider": "openbao",
                        "path": "secret/data/this-does-not-exist-hyperi-pylib-test",
                        "env_fallback": "FALLBACK_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("missing")
        assert value.decode() == "vault-fallback-value"
        assert value.source == "env"


# ---------------------------------------------------------------------------
# ENV fallback — no cloud credentials required, always runs
# ---------------------------------------------------------------------------


class TestEnvFallbackAlwaysRuns:
    """ENV fallback tests using the file provider — no cloud credentials required."""

    @pytest.mark.asyncio
    async def test_async_falls_back_to_env_when_file_missing(self, monkeypatch):
        """Async: falls back to ENV var when file secret does not exist."""
        monkeypatch.setenv("TEST_API_KEY", "env-fallback-value")
        manager = SecretsManager.from_config(
            {
                "sources": {
                    "api_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                        "env_fallback": "TEST_API_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = await manager.get("api_key")
        assert value.decode() == "env-fallback-value"
        assert value.source == "env"

    def test_sync_falls_back_to_env_when_file_missing(self, monkeypatch):
        """Sync: falls back to ENV var when file secret does not exist."""
        monkeypatch.setenv("TEST_API_KEY", "env-fallback-sync")
        manager = SecretsManager.from_config(
            {
                "sources": {
                    "api_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                        "env_fallback": "TEST_API_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("api_key")
        assert value.decode() == "env-fallback-sync"
        assert value.source == "env"

    def test_raises_when_fallback_env_var_absent(self, monkeypatch):
        """Raises original error when env_fallback var is not set."""
        monkeypatch.delenv("TEST_API_KEY", raising=False)
        manager = SecretsManager.from_config(
            {
                "sources": {
                    "api_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                        "env_fallback": "TEST_API_KEY",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        with pytest.raises(SecretNotFoundError):
            manager.get_sync("api_key")

    def test_raises_when_no_env_fallback_configured(self, monkeypatch):
        """Raises immediately when env_fallback is not configured."""
        monkeypatch.setenv("TEST_API_KEY", "should-not-be-used")
        manager = SecretsManager.from_config(
            {
                "sources": {
                    "api_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        with pytest.raises(SecretNotFoundError):
            manager.get_sync("api_key")

    def test_auto_fallback_uses_name_uppercased(self, monkeypatch):
        """Auto fallback: NAME.upper() is tried when no env_fallback is set."""
        monkeypatch.setenv("FRED_KEY", "auto-fallback-value")
        manager = SecretsManager.from_config(
            {
                "sources": {
                    "fred_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("fred_key")
        assert value.decode() == "auto-fallback-value"
        assert value.source == "env"

    def test_auto_fallback_with_env_prefix(self, monkeypatch):
        """Auto fallback: {PREFIX}_{NAME.upper()} is tried when env_prefix is set."""
        monkeypatch.setenv("DFE_FRED_KEY", "prefixed-fallback-value")
        manager = SecretsManager.from_config(
            {
                "env_prefix": "DFE",
                "sources": {
                    "fred_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("fred_key")
        assert value.decode() == "prefixed-fallback-value"
        assert value.source == "env"

    def test_explicit_env_fallback_overrides_prefix(self, monkeypatch):
        """Explicit env_fallback takes precedence over auto prefix lookup."""
        monkeypatch.setenv("MY_EXPLICIT_VAR", "explicit-value")
        monkeypatch.setenv("DFE_FRED_KEY", "should-not-be-used")
        manager = SecretsManager.from_config(
            {
                "env_prefix": "DFE",
                "sources": {
                    "fred_key": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                        "env_fallback": "MY_EXPLICIT_VAR",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("fred_key")
        assert value.decode() == "explicit-value"
        assert value.source == "env"

    def test_auto_fallback_prefix_via_env_var(self, monkeypatch):
        """env_prefix can also be set via HYPERI_SECRETS_ENV_PREFIX env var."""
        monkeypatch.setenv("HYPERI_SECRETS_ENV_PREFIX", "APP")
        monkeypatch.setenv("APP_MY_SECRET", "env-prefix-via-env-var")
        manager = SecretsManager.from_config(
            {
                "sources": {
                    "my_secret": {
                        "provider": "file",
                        "path": "/nonexistent/path/that/does/not/exist",
                    },
                },
                "cache": {"enabled": False},
            }
        )
        value = manager.get_sync("my_secret")
        assert value.decode() == "env-prefix-via-env-var"
        assert value.source == "env"
