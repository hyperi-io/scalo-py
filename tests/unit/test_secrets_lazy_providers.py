#  Project:   scalo
#  File:      tests/unit/test_secrets_lazy_providers.py
#  Purpose:   Importing scalo.secrets loads no provider SDK, and a provider's SDK loads when that provider is used
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``import scalo.secrets`` imports no provider SDK, and each provider loads on its own.

Each case runs in a fresh interpreter, because anything an earlier test imported would already sit in
``sys.modules`` and hide the cost.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import scalo

# The subprocess must import the same scalo tree as this test process, not whichever copy is installed.
_SRC = Path(scalo.__file__).resolve().parents[1]

_HEAD = """
import json
import sys

SDKS = [
    "boto3", "botocore", "aiobotocore", "google.cloud.secretmanager", "azure.keyvault.secrets",
    "azure.identity", "ansible_vault", "httpx", "stamina",
]


def report(**extra):
    print(json.dumps({
        "sdks": sorted(name for name in SDKS if name in sys.modules),
        "providers": sorted(m.rsplit(".", 1)[1] for m in sys.modules if m.startswith("scalo.secrets.providers.")),
        **extra,
    }))
"""

# Provider modules every import of the package needs.
_ALWAYS = {"base", "file"}

# Every name the package re-exports from a provider module, with the module that defines it.
_PROVIDER_NAMES = {
    "AIOBOTOCORE_AVAILABLE": "aws",
    "BOTO3_AVAILABLE": "aws",
    "AWSProvider": "aws",
    "AZURE_ASYNC_AVAILABLE": "azure",
    "AZURE_AVAILABLE": "azure",
    "AzureProvider": "azure",
    "GCP_AVAILABLE": "gcp",
    "GCPProvider": "gcp",
    "HTTPX_AVAILABLE": "openbao",
    "OpenBaoProvider": "openbao",
    "KubernetesProvider": "kubernetes",
}

# config key, provider config, provider module, the SDK modules that provider alone brings in
_CONFIGURED = [
    ("aws", {"region": "ap-southeast-2"}, "aws", {"boto3", "botocore", "aiobotocore"}),
    ("gcp", {"project_id": "demo"}, "gcp", {"google.cloud.secretmanager"}),
    ("azure", {"vault_url": "https://demo.vault.azure.net/"}, "azure", {"azure.keyvault.secrets", "azure.identity"}),
    ("openbao", {"address": "https://vault:8200"}, "openbao", {"httpx"}),
    ("kubernetes", {"secret_name": "demo"}, "kubernetes", {"httpx", "stamina"}),
    ("ansible_vault", {"password": "pw"}, "ansible_vault", {"ansible_vault"}),
]


def _run(body: str, tmp_path: Path) -> dict:
    """Run ``body`` after the report helpers in a fresh interpreter and return the JSON it printed last."""
    result = subprocess.run(
        [sys.executable, "-c", _HEAD + body],
        capture_output=True,
        check=False,
        cwd=tmp_path,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        errors="replace",
        timeout=180,
    )
    assert result.returncode == 0, f"the probe failed:\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestImportLoadsNoProviderSdk:
    def test_import_scalo_secrets_leaves_every_sdk_and_provider_module_unloaded(self, tmp_path):
        reported = _run("import scalo.secrets\nreport()", tmp_path)

        assert reported["sdks"] == [], f"importing scalo.secrets loaded {reported['sdks']}"
        assert set(reported["providers"]) == _ALWAYS, f"provider modules loaded: {reported['providers']}"


class TestPublicNamesStillResolve:
    def test_each_name_imports_from_both_packages_and_is_the_same_object(self, tmp_path):
        names = sorted(_PROVIDER_NAMES)
        body = f"""
import scalo.secrets
import scalo.secrets.providers
from scalo.secrets import ({", ".join(names)})
from scalo.secrets.providers import ({", ".join(names)})

found = {{}}
for name in {names!r}:
    top, sub = getattr(scalo.secrets, name), getattr(scalo.secrets.providers, name)
    found[name] = top is sub and top is not None
report(found=found)
"""
        reported = _run(body, tmp_path)

        assert reported["found"] == dict.fromkeys(_PROVIDER_NAMES, True)

    def test_a_provider_module_is_reachable_as_an_attribute_of_the_package(self, tmp_path):
        body = """
import scalo.secrets.providers

reached = {
    name: getattr(scalo.secrets.providers, name).__name__
    for name in ("aws", "azure", "gcp", "openbao", "kubernetes", "ansible_vault")
}
report(reached=reached)
"""
        reported = _run(body, tmp_path)

        assert reported["reached"] == {
            name: f"scalo.secrets.providers.{name}"
            for name in ("aws", "azure", "gcp", "openbao", "kubernetes", "ansible_vault")
        }

    def test_a_name_the_package_does_not_have_is_an_attribute_error(self, tmp_path):
        body = """
import scalo.secrets
import scalo.secrets.providers

missing = []
for package in (scalo.secrets, scalo.secrets.providers):
    try:
        package.NoSuchProvider
    except AttributeError as exc:
        missing.append(str(exc))
report(missing=missing)
"""
        reported = _run(body, tmp_path)

        assert len(reported["missing"]) == 2
        assert all("NoSuchProvider" in message for message in reported["missing"])

    def test_a_provider_whose_sdk_is_absent_still_resolves_with_its_flag_false(self, tmp_path):
        body = """
sys.modules["boto3"] = None
import scalo.secrets

report(flag=scalo.secrets.BOTO3_AVAILABLE, is_class=isinstance(scalo.secrets.AWSProvider, type))
"""
        reported = _run(body, tmp_path)

        assert reported["flag"] is False
        assert reported["is_class"] is True


class TestProviderLoadsOnUse:
    @pytest.mark.parametrize(
        ("name", "module", "sdks"),
        [
            ("AWSProvider", "aws", {"boto3", "botocore", "aiobotocore"}),
            ("GCP_AVAILABLE", "gcp", {"google.cloud.secretmanager"}),
            ("AzureProvider", "azure", {"azure.keyvault.secrets", "azure.identity"}),
            ("OpenBaoProvider", "openbao", {"httpx"}),
            ("KubernetesProvider", "kubernetes", {"httpx", "stamina"}),
        ],
        ids=["AWSProvider", "GCP_AVAILABLE", "AzureProvider", "OpenBaoProvider", "KubernetesProvider"],
    )
    def test_reading_a_provider_name_loads_that_provider_alone(self, tmp_path, name, module, sdks):
        reported = _run(f"import scalo.secrets\nscalo.secrets.{name}\nreport()", tmp_path)

        assert set(reported["providers"]) == _ALWAYS | {module}
        assert set(reported["sdks"]) == sdks

    @pytest.mark.parametrize(("key", "section", "module", "sdks"), _CONFIGURED, ids=[c[0] for c in _CONFIGURED])
    def test_from_config_loads_the_configured_provider_alone(self, tmp_path, key, section, module, sdks):
        config = {key: section, "cache": {"enabled": False}}
        # The registry is read directly: a health check would call the real backend.
        body = f"""
from scalo.secrets import SecretsManager

manager = SecretsManager.from_config({config!r})
report(registered=sorted(manager._providers))
"""
        reported = _run(body, tmp_path)

        assert key in reported["registered"], f"{key} was left out: {reported['registered']}"
        assert set(reported["providers"]) == _ALWAYS | {module}
        assert set(reported["sdks"]) == sdks
