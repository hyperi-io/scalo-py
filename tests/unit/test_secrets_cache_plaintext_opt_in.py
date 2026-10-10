#  Project:   scalo
#  File:      tests/unit/test_secrets_cache_plaintext_opt_in.py
#  Purpose:   The secrets disk tier writes only sealed entries or under the plaintext opt-in
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The secrets disk tier writes only sealed entries, or plaintext under an explicit opt-in."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from scalo.secrets.cache import DiskCache
from scalo.secrets.exceptions import CacheError
from scalo.secrets.manager import SecretsManager
from scalo.secrets.providers.file import FileProvider
from scalo.secrets.types import CacheConfig, SecretValue

VALUE = b"plaintext-secret-7f3a9c"


def _entry() -> SecretValue:
    return SecretValue(data=VALUE, fetched_at=datetime.now(UTC))


def _cache_files(directory: Path) -> list[Path]:
    return list(directory.glob("*.cache"))


def test_no_key_and_no_opt_in_writes_nothing(tmp_path):
    cache = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path)))

    cache.set("k", _entry())

    assert _cache_files(tmp_path) == []
    assert cache.get("k") is None


def test_no_key_and_no_opt_in_does_not_read_a_plaintext_file(tmp_path):
    DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), allow_plaintext_disk_cache=True)).set("k", _entry())
    assert len(_cache_files(tmp_path)) == 1

    reader = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path)))

    assert reader.get("k") is None


def test_plaintext_opt_in_writes_and_reads_back(tmp_path):
    cache = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), allow_plaintext_disk_cache=True))

    cache.set("k", _entry())

    [cache_file] = _cache_files(tmp_path)
    assert VALUE.hex().encode() in cache_file.read_bytes()
    result = cache.get("k")
    assert result is not None
    assert result.data == VALUE


def test_encryption_key_writes_a_sealed_entry_and_reads_back(tmp_path):
    cache = DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), encryption_key=b"k" * 32))

    cache.set("k", _entry())

    [cache_file] = _cache_files(tmp_path)
    assert VALUE.hex().encode() not in cache_file.read_bytes()
    result = cache.get("k")
    assert result is not None
    assert result.data == VALUE


def test_encryption_key_wins_over_the_plaintext_opt_in(tmp_path):
    cfg = CacheConfig(enabled=True, directory=str(tmp_path), encryption_key=b"k" * 32, allow_plaintext_disk_cache=True)
    cache = DiskCache(cfg)

    cache.set("k", _entry())

    [cache_file] = _cache_files(tmp_path)
    assert VALUE.hex().encode() not in cache_file.read_bytes()


@pytest.mark.parametrize("app_env", ["production", "prod", "PRODUCTION"])
def test_plaintext_opt_in_is_refused_in_production(tmp_path, monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)

    with pytest.raises(CacheError):
        DiskCache(CacheConfig(enabled=True, directory=str(tmp_path), allow_plaintext_disk_cache=True))


def test_default_manager_caches_in_memory_only(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(VALUE)
    cache_dir = tmp_path / "cache"
    manager = SecretsManager(providers={"file": FileProvider()}, cache_config=CacheConfig(directory=str(cache_dir)))

    assert manager.get_sync(str(secret_file)).data == VALUE
    secret_file.write_bytes(b"rotated")
    assert manager.get_sync(str(secret_file)).data == VALUE

    assert not cache_dir.exists() or _cache_files(cache_dir) == []


def test_from_config_reads_the_plaintext_opt_in(tmp_path):
    manager = SecretsManager.from_config(
        {"cache": {"directory": str(tmp_path), "allow_plaintext_disk_cache": True}},
    )

    assert manager._cache.config.allow_plaintext_disk_cache is True
