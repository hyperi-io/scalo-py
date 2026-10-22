#  Project:   scalo
#  File:      tests/unit/test_secrets_provider_health.py
#  Purpose:   The openbao, aws, gcp and azure providers say why their own health check failed
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Each provider catches its own errors and returns ``False``, so the manager never sees a reason.

So each logs one: a warning naming the provider, with the reason masked, when its check first fails, nothing
while it keeps failing, and one INFO line when it passes again. The providers here are real objects. OpenBao
and AWS talk to an HTTP server on localhost (tests/common/fake_secret_backends.py), or to a port nothing
listens on. GCP and Azure have no setting that points them at a local server, so they fail the way a
misconfigured deployment does, on a service account key file that is not there and on a tenant id the Azure SDK
refuses, both before any network call.
"""

import logging
import socket

import pytest
from common.fake_secret_backends import running_fake_aws, running_fake_vault
from common.fake_secrets import aws_access_key, opaque_secret

from scalo.secrets.providers.aws import BOTO3_AVAILABLE, AWSProvider
from scalo.secrets.providers.azure import AZURE_AVAILABLE, AzureProvider
from scalo.secrets.providers.gcp import GCP_AVAILABLE, GCPProvider
from scalo.secrets.providers.openbao import HTTPX_AVAILABLE, OpenBaoProvider
from scalo.secrets.types import AWSConfig, AzureConfig, GCPConfig, OpenBaoConfig

# Built at run time so no source-scanning tool sees a credential in the file.
_PASSWORD = "pw" + "-sentinel-" + "7f3a91"
_TOKEN = "tok" + "-sentinel-" + "c20b64"

_BOTH = pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])


@pytest.fixture(autouse=True)
def _capture_provider_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="scalo.secrets.providers")


async def _check(provider, use_async: bool) -> bool:
    return await provider.health_check_async() if use_async else provider.health_check_sync()


def _logged(caplog: pytest.LogCaptureFixture, provider: str, level: int) -> list[str]:
    name = f"scalo.secrets.providers.{provider}"
    return [r.getMessage() for r in caplog.records if r.name == name and r.levelno == level]


def _closed_port() -> int:
    """Return a local port with nothing listening on it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestOpenBao:
    @staticmethod
    def _provider(address: str) -> OpenBaoProvider:
        return OpenBaoProvider(OpenBaoConfig(address=address, token=opaque_secret("vault-token"), timeout_secs=2))

    @_BOTH
    async def test_a_store_nothing_listens_on_logs_one_warning(self, caplog, use_async):
        provider = self._provider(f"http://127.0.0.1:{_closed_port()}")

        results = [await _check(provider, use_async) for _ in range(3)]
        await provider.close()

        assert results == [False, False, False]
        warnings = _logged(caplog, "openbao", logging.WARNING)
        assert len(warnings) == 1, f"expected one warning, got {warnings}"
        assert "openbao" in warnings[0]
        assert "ConnectError" in warnings[0]

    @_BOTH
    async def test_a_sealed_store_is_named_and_each_recovery_is_logged_once(self, caplog, use_async):
        with running_fake_vault() as vault:
            provider = self._provider(vault.url)

            vault.status = 503
            assert [await _check(provider, use_async) for _ in range(2)] == [False, False]
            vault.status = 200
            assert [await _check(provider, use_async) for _ in range(2)] == [True, True]
            vault.status = 503
            assert await _check(provider, use_async) is False
            await provider.close()

        warnings = _logged(caplog, "openbao", logging.WARNING)
        assert len(warnings) == 2, f"one warning per outage, got {warnings}"
        assert "503" in warnings[0]
        assert "sealed" in warnings[0]
        recoveries = _logged(caplog, "openbao", logging.INFO)
        assert len(recoveries) == 1
        assert "openbao" in recoveries[0]

    @_BOTH
    async def test_a_standby_store_is_healthy_and_logs_nothing(self, caplog, use_async):
        with running_fake_vault() as vault:
            vault.status = 429
            provider = self._provider(vault.url)

            assert await _check(provider, use_async) is True
            await provider.close()

        assert [r for r in caplog.records if r.name.startswith("scalo.secrets.providers")] == []


@pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed")
class TestAws:
    @staticmethod
    def _provider(endpoint_url: str) -> AWSProvider:
        return AWSProvider(
            AWSConfig(
                region="ap-southeast-2",
                endpoint_url=endpoint_url,
                access_key_id=aws_access_key(),
                secret_access_key=opaque_secret("aws-secret"),
                timeout_secs=5,
            )
        )

    @_BOTH
    async def test_a_refusal_is_logged_once_with_the_reason_and_each_recovery_once(self, caplog, use_async):
        with running_fake_aws() as aws:
            provider = self._provider(aws.url)

            aws.status = 400
            assert [await _check(provider, use_async) for _ in range(3)] == [False, False, False]
            aws.status = 200
            assert [await _check(provider, use_async) for _ in range(2)] == [True, True]
            aws.status = 400
            assert await _check(provider, use_async) is False
            await provider.close()

        warnings = _logged(caplog, "aws", logging.WARNING)
        assert len(warnings) == 2, f"one warning per outage, got {warnings}"
        assert "aws" in warnings[0]
        assert "AccessDeniedException" in warnings[0]
        assert "the caller may not list secrets" in warnings[0]
        recoveries = _logged(caplog, "aws", logging.INFO)
        assert len(recoveries) == 1
        assert "aws" in recoveries[0]

    @_BOTH
    async def test_the_reason_is_masked(self, caplog, use_async):
        with running_fake_aws() as aws:
            provider = self._provider(aws.url)
            aws.status = 400
            aws.error_message = f"GET https://svc:{_PASSWORD}@vault.internal:8200/ failed, token={_TOKEN}"

            assert await _check(provider, use_async) is False
            await provider.close()

        warnings = _logged(caplog, "aws", logging.WARNING)
        assert len(warnings) == 1
        everything = " ".join([warnings[0], caplog.text])
        assert _PASSWORD not in everything, "a URL password reached the log"
        assert _TOKEN not in everything, "a token reached the log"
        assert "REDACTED" in warnings[0]
        assert "vault.internal:8200" in warnings[0], "masking removed the host that says where it failed"


@pytest.mark.skipif(not GCP_AVAILABLE, reason="google-cloud-secret-manager not installed")
class TestGcp:
    @_BOTH
    async def test_an_unreadable_key_file_is_logged_once(self, caplog, tmp_path, use_async):
        provider = GCPProvider(GCPConfig(project_id="demo", credentials_file=str(tmp_path / "absent-key.json")))

        results = [await _check(provider, use_async) for _ in range(3)]
        await provider.close()

        assert results == [False, False, False]
        warnings = _logged(caplog, "gcp", logging.WARNING)
        assert len(warnings) == 1, f"expected one warning, got {warnings}"
        assert "gcp" in warnings[0]
        assert "FileNotFoundError" in warnings[0]
        assert "absent-key.json" in warnings[0]


@pytest.mark.skipif(not AZURE_AVAILABLE, reason="azure-keyvault-secrets not installed")
class TestAzure:
    @_BOTH
    async def test_a_tenant_id_the_sdk_refuses_is_logged_once(self, caplog, use_async):
        provider = AzureProvider(
            AzureConfig(
                vault_url="https://demo.vault.azure.net/",
                tenant_id="not a tenant id!",
                client_id="demo-client",
                client_secret=opaque_secret("azure-secret"),
            )
        )

        results = [await _check(provider, use_async) for _ in range(3)]
        await provider.close()

        assert results == [False, False, False]
        warnings = _logged(caplog, "azure", logging.WARNING)
        assert len(warnings) == 1, f"expected one warning, got {warnings}"
        assert "azure" in warnings[0]
        assert "Invalid tenant ID" in warnings[0]
        assert opaque_secret("azure-secret") not in caplog.text
