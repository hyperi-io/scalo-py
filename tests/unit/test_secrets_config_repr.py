#  Project:   hyperi-pylib
#  File:      tests/unit/test_secrets_config_repr.py
#  Purpose:   Provider config dataclasses must NOT print credentials in repr
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Provider config repr must not embed credential fields."""

from __future__ import annotations

from common.fake_secrets import opaque_secret

from hyperi_pylib.secrets.types import (
    AnsibleVaultConfig,
    AWSConfig,
    AzureConfig,
    GCPConfig,
    OpenBaoConfig,
)

SECRET = opaque_secret("cred")


def test_openbao_config_token_redacted():
    cfg = OpenBaoConfig(address="https://vault:8200", token=SECRET)
    assert SECRET not in repr(cfg)
    # Address (non-secret) still appears so callers can identify the config
    assert "vault:8200" in repr(cfg)


def test_openbao_config_role_id_redacted():
    cfg = OpenBaoConfig(address="https://vault:8200", role_id=SECRET, secret_id=SECRET)
    assert SECRET not in repr(cfg)


def test_aws_config_secret_access_key_redacted():
    cfg = AWSConfig(secret_access_key=SECRET, access_key_id=SECRET)
    assert SECRET not in repr(cfg)


def test_azure_config_client_secret_redacted():
    cfg = AzureConfig(vault_url="https://kv.azure.net/", client_secret=SECRET)
    assert SECRET not in repr(cfg)
    assert "kv.azure.net" in repr(cfg)


def test_ansible_vault_config_password_redacted():
    cfg = AnsibleVaultConfig(password=SECRET, password_file="/tmp/pw")
    assert SECRET not in repr(cfg)
    # password_file path is non-sensitive metadata, still shown
    assert "/tmp/pw" in repr(cfg)


def test_gcp_config_unchanged():
    """GCP uses ADC or a credentials_file path -- no secret strings on
    the config itself. Sanity check: repr surfaces project + path."""
    cfg = GCPConfig(project_id="my-project", credentials_file="/keys/sa.json")
    r = repr(cfg)
    assert "my-project" in r
    assert "/keys/sa.json" in r


def test_provider_configs_in_exception_chain_do_not_leak():
    """If a provider config is interpolated into an exception message
    (a common debug pattern), credentials still must not leak."""
    cfg = OpenBaoConfig(address="https://vault:8200", token=SECRET)
    try:
        raise RuntimeError(f"openbao init failed for {cfg!r}")
    except RuntimeError as e:
        assert SECRET not in str(e)
        assert SECRET not in repr(e)
