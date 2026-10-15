#  Project:   scalo
#  File:      tests/unit/test_secrets_manager_missing_sdk.py
#  Purpose:   from_config leaves out a configured provider whose SDK is not installed
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``SecretsManager.from_config`` leaves out a configured provider whose SDK is not installed.

Each case runs in a fresh interpreter that puts ``None`` in ``sys.modules`` for the SDK before scalo
imports, so the provider module's own import probe sees a package that is not there.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scalo
from scalo.secrets import ProviderError, SecretsManager

# The subprocess must import the same scalo tree as this test process, not whichever copy is installed.
_SRC = Path(scalo.__file__).resolve().parents[1]

# provider key, SDK module to hide, provider config, extra named in the warning
_PROVIDERS = [
    ("aws", "boto3", {"region": "ap-southeast-2"}, "secrets-aws"),
    ("gcp", "google.cloud.secretmanager", {"project_id": "demo"}, "secrets-gcp"),
    ("azure", "azure.keyvault.secrets", {"vault_url": "https://demo.vault.azure.net/"}, "secrets-azure"),
    ("openbao", "httpx", {"address": "https://vault:8200"}, "secrets-vault"),
    ("ansible_vault", "ansible_vault", {"password": "pw"}, "secrets-ansible-vault"),
]

_SCRIPT = """
import json
import logging
import sys

hidden, provider, config = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
sys.modules[hidden] = None

warnings = []


class Capture(logging.Handler):
    def emit(self, record):
        warnings.append(record.getMessage())


log = logging.getLogger("scalo.secrets.manager")
log.addHandler(Capture(level=logging.WARNING))
log.setLevel(logging.WARNING)

from scalo.secrets import SecretsManager

manager = SecretsManager.from_config(config)
at_config = list(warnings)

try:
    manager.get_sync("anything", provider=provider)
    direct = "returned"
except Exception as exc:
    direct = type(exc).__name__

print(json.dumps({
    "warnings": at_config,
    "direct": direct,
    "fallback": manager.get_string_sync("fallback_demo"),
}))
"""


@pytest.fixture(scope="module", params=_PROVIDERS, ids=[case[0] for case in _PROVIDERS])
def outcome(request):
    """Run ``from_config`` with one provider's SDK hidden and report what the manager did."""
    provider, hidden, section, extra = request.param
    config = {
        provider: section,
        "cache": {"enabled": False},
        "sources": {"fallback_demo": {"provider": provider, "path": "demo"}},
    }
    env = {**os.environ, "PYTHONPATH": str(_SRC), "FALLBACK_DEMO": "from-env"}

    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, hidden, provider, json.dumps(config)],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=env,
        errors="replace",
        timeout=120,
    )

    assert result.returncode == 0, f"from_config raised with {hidden} hidden:\n{result.stderr}"
    reported = json.loads(result.stdout.strip().splitlines()[-1])
    return provider, extra, reported


class TestConfiguredProviderWithoutItsSdk:
    """A provider named in the config whose SDK is missing is logged and left out."""

    def test_from_config_returns_and_warns_with_the_install_hint(self, outcome):
        provider, extra, reported = outcome

        assert len(reported["warnings"]) == 1, f"expected one warning, got {reported['warnings']}"
        assert f"'{provider}'" in reported["warnings"][0]
        assert extra in reported["warnings"][0]

    def test_using_the_provider_raises_not_configured(self, outcome):
        _, _, reported = outcome

        assert reported["direct"] == "ProviderNotConfiguredError"

    def test_a_named_source_on_the_provider_falls_back_to_env(self, outcome):
        _, _, reported = outcome

        assert reported["fallback"] == "from-env"


class TestOtherProviderFailuresStillRaise:
    """Only a missing SDK is skipped. A provider whose SDK is present and whose config is bad fails fast."""

    @pytest.fixture(autouse=True)
    def _no_vault_password(self, monkeypatch):
        pytest.importorskip("ansible_vault")
        for name in ("ANSIBLE_VAULT_PASSWORD", "ANSIBLE_VAULT_PASS", "ANSIBLE_VAULT_PASSWORD_FILE"):
            monkeypatch.delenv(name, raising=False)

    def test_missing_password_raises_provider_error(self):
        with pytest.raises(ProviderError, match="no vault password"):
            SecretsManager.from_config({"ansible_vault": {}, "cache": {"enabled": False}})

    def test_provider_with_its_sdk_is_registered(self):
        manager = SecretsManager.from_config({"ansible_vault": {"password": "pw"}, "cache": {"enabled": False}})

        assert "ansible_vault" in manager.health_check_sync()
