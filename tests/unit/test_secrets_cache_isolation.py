#  Project:   hyperi-pylib
#  File:      tests/unit/test_secrets_cache_isolation.py
#  Purpose:   Two SecretsManager instances must not share cached secrets
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Two SecretsManager instances must not share cached secrets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hyperi_pylib.secrets.manager import SecretsManager, _CacheKey
from hyperi_pylib.secrets.providers.file import FileProvider
from hyperi_pylib.secrets.types import CacheConfig, ProviderType, SecretValue, SourceConfig


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_two_managers_with_distinct_file_providers_do_not_share_cache(tmp_path):
    """Two managers, two tmpdirs, same logical secret name + path.
    Manager A and Manager B must each return their OWN backend's value.
    """
    tenant_a = tmp_path / "tenant_a"
    tenant_b = tmp_path / "tenant_b"

    secret_path_a = tenant_a / "api_key"
    secret_path_b = tenant_b / "api_key"
    _write(secret_path_a, b"TENANT_A_SECRET")
    _write(secret_path_b, b"TENANT_B_SECRET")

    # Disable disk cache so memory cache is the only path
    disabled_cache = CacheConfig(enabled=False)

    mgr_a = SecretsManager(
        providers={"file": FileProvider()},
        sources={"shared": SourceConfig(provider=ProviderType.FILE, path=str(secret_path_a))},
        cache_config=disabled_cache,
    )
    mgr_b = SecretsManager(
        providers={"file": FileProvider()},
        sources={"shared": SourceConfig(provider=ProviderType.FILE, path=str(secret_path_b))},
        cache_config=disabled_cache,
    )

    val_a = mgr_a.get_sync("shared")
    val_b = mgr_b.get_sync("shared")

    assert val_a.data == b"TENANT_A_SECRET"
    assert val_b.data == b"TENANT_B_SECRET"
    # And neither manager has the other's value lingering in memory cache
    a_cached_keys = list(mgr_a._memory_cache.keys())
    # Both should have populated their OWN cache, not shared one
    assert all(isinstance(k, _CacheKey) for k in a_cached_keys)
    a_values = {v.data for v in mgr_a._memory_cache.values()}
    b_values = {v.data for v in mgr_b._memory_cache.values()}
    assert b"TENANT_B_SECRET" not in a_values
    assert b"TENANT_A_SECRET" not in b_values


def test_same_provider_name_different_path_no_bleed(tmp_path):
    """Two managers, same logical provider key ("file"), DIFFERENT paths.
    Sanity check that the structured cache key keeps them apart."""
    p1 = tmp_path / "secret_1"
    p2 = tmp_path / "secret_2"
    _write(p1, b"VALUE_ONE")
    _write(p2, b"VALUE_TWO")

    mgr = SecretsManager(
        providers={"file": FileProvider()},
        sources={
            "one": SourceConfig(provider=ProviderType.FILE, path=str(p1)),
            "two": SourceConfig(provider=ProviderType.FILE, path=str(p2)),
        },
        cache_config=CacheConfig(enabled=False),
    )

    assert mgr.get_sync("one").data == b"VALUE_ONE"
    assert mgr.get_sync("two").data == b"VALUE_TWO"
    # Both must be cached under DIFFERENT keys
    assert len(mgr._memory_cache) == 2


def test_path_containing_colons_round_trips(tmp_path):
    """C14: previous string-based key used split(':', 2), which broke for
    paths containing colons. Structured cache key handles this cleanly."""
    weird_path = tmp_path / "ns:tenant-1:key" / "secret"
    _write(weird_path, b"COLON_HEAVY_VALUE")

    mgr = SecretsManager(
        providers={"file": FileProvider()},
        sources={"weird": SourceConfig(provider=ProviderType.FILE, path=str(weird_path))},
        cache_config=CacheConfig(enabled=False),
    )

    val = mgr.get_sync("weird")
    assert val.data == b"COLON_HEAVY_VALUE"
    # Cache key should preserve the original path verbatim, no parsing damage
    keys = list(mgr._memory_cache.keys())
    assert len(keys) == 1
    assert keys[0].path == str(weird_path)


def test_memory_cache_is_instance_not_class_attribute():
    """Defensive: confirms the cache is no longer class-level. A new manager
    instance starts with an empty cache regardless of what other instances
    did."""
    mgr1 = SecretsManager(cache_config=CacheConfig(enabled=False))
    mgr2 = SecretsManager(cache_config=CacheConfig(enabled=False))
    # Different dict objects (instance attribute, not shared class attribute)
    assert mgr1._memory_cache is not mgr2._memory_cache
    # And not present on the class itself
    assert "_memory_cache" not in vars(SecretsManager)
