#  Project:   scalo
#  File:      tests/unit/test_secrets_cache_isolation.py
#  Purpose:   Two SecretsManager instances must not share cached secrets
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Two SecretsManager instances must not share cached secrets."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scalo.secrets.manager import SecretsManager, _CacheKey
from scalo.secrets.providers.file import FileProvider
from scalo.secrets.types import CacheConfig, ProviderType, SecretValue, SourceConfig


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

    mgr_a = SecretsManager(
        providers={"file": FileProvider()},
        sources={"shared": SourceConfig(provider=ProviderType.FILE, path=str(secret_path_a))},
        cache_config=CacheConfig(enabled=True, directory=str(tmp_path / "cache_a")),
    )
    mgr_b = SecretsManager(
        providers={"file": FileProvider()},
        sources={"shared": SourceConfig(provider=ProviderType.FILE, path=str(secret_path_b))},
        cache_config=CacheConfig(enabled=True, directory=str(tmp_path / "cache_b")),
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
        cache_config=CacheConfig(enabled=True, directory=str(tmp_path / "cache")),
    )

    assert mgr.get_sync("one").data == b"VALUE_ONE"
    assert mgr.get_sync("two").data == b"VALUE_TWO"
    # Both must be cached under DIFFERENT keys
    assert len(mgr._memory_cache) == 2


def test_path_containing_colons_round_trips(tmp_path):
    """The previous string-based key used split(':', 2), which broke for
    paths containing colons. The structured cache key handles them cleanly."""
    weird_path = tmp_path / "ns:tenant-1:key" / "secret"
    _write(weird_path, b"COLON_HEAVY_VALUE")

    mgr = SecretsManager(
        providers={"file": FileProvider()},
        sources={"weird": SourceConfig(provider=ProviderType.FILE, path=str(weird_path))},
        cache_config=CacheConfig(enabled=True, directory=str(tmp_path / "cache")),
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


# Seals disk-cache entries, so the disk tier is on.
_CACHE_KEY = "k" * 32


def _disk_cached(cache_dir: Path) -> CacheConfig:
    return CacheConfig(enabled=True, directory=str(cache_dir), encryption_key=_CACHE_KEY)


def test_a_colon_in_path_or_key_never_shares_a_disk_entry(tmp_path):
    """``(path="x:y", key="c")`` and ``(path="x", key="y:c")`` once both became ``file:x:y:c`` on disk."""
    base = tmp_path / "secrets"
    _write(base / "x:y", b'{"c": "ONE"}')
    _write(base / "x", b'{"y:c": "TWO"}')
    cache = _disk_cached(tmp_path / "cache")

    first = SecretsManager(cache_config=cache).get_sync(str(base / "x:y"), key="c")
    # A second manager starts with an empty memory tier, so its read reaches the disk tier.
    second = SecretsManager(cache_config=cache).get_sync(str(base / "x"), key="y:c")

    assert first.data == b"ONE"
    assert second.data == b"TWO"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        pytest.param({"address": "https://bao-a:8200"}, {"address": "https://bao-b:8200"}, id="address"),
        pytest.param({"namespace": "tenant-a"}, {"namespace": "tenant-b"}, id="namespace"),
        pytest.param({"mount": "kv-a"}, {"mount": "kv-b"}, id="mount"),
        pytest.param({"token": "s.one"}, {"token": "s.two"}, id="credential"),
        pytest.param(
            {"auth_method": "approle", "role_id": "r1"}, {"auth_method": "approle", "role_id": "r2"}, id="role"
        ),
    ],
)
def test_two_openbao_backends_named_alike_never_share_a_disk_entry(tmp_path, a, b):
    from scalo.secrets.providers.openbao import OpenBaoProvider
    from scalo.secrets.types import OpenBaoConfig

    def manager(fields: dict[str, Any]) -> SecretsManager:
        settings: dict[str, Any] = {"address": "https://bao:8200", **fields}
        config = OpenBaoConfig(**settings)
        return SecretsManager(providers={"openbao": OpenBaoProvider(config)}, cache_config=_disk_cached(tmp_path))

    key = _CacheKey("openbao", "secret/data/app", "password")
    first, second = manager(a)._disk_key(key), manager(b)._disk_key(key)
    assert first != second
    # A credential reaches the cache file name only as a digest.
    assert "s.one" not in first
    assert "r1" not in first


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("change", ["update", "delete"])
def test_an_update_or_delete_is_never_answered_from_either_cache_tier(tmp_path, change, mode):
    """Both tiers hold the old value and a sub-key of it, and neither may answer once it changed."""
    import asyncio

    from scalo.secrets.exceptions import SecretNotFoundError

    secret = tmp_path / "secrets" / "db"
    _write(secret, b'{"password": "OLD"}')
    cache = _disk_cached(tmp_path / "cache")
    manager = SecretsManager(cache_config=cache)
    assert manager.get_sync(str(secret)).data == b'{"password": "OLD"}'
    assert manager.get_sync(str(secret), key="password").data == b"OLD"

    if change == "update" and mode == "sync":
        manager.update_sync(str(secret), b'{"password": "NEW"}')
    elif change == "update":
        asyncio.run(manager.update(str(secret), b'{"password": "NEW"}'))
    elif mode == "sync":
        manager.delete_sync(str(secret))
    else:
        asyncio.run(manager.delete(str(secret)))

    # A second manager on the same directory starts with an empty memory tier, so it reads the disk tier.
    for reader in (manager, SecretsManager(cache_config=cache)):
        if change == "update":
            assert reader.get_sync(str(secret), key="password").data == b"NEW"
            assert reader.get_sync(str(secret)).data == b'{"password": "NEW"}'
        else:
            with pytest.raises(SecretNotFoundError):
                reader.get_sync(str(secret), key="password")
            with pytest.raises(SecretNotFoundError):
                reader.get_sync(str(secret))
