#  Project:   scalo
#  File:      tests/unit/test_secrets_cache_disabled.py
#  Purpose:   CacheConfig.enabled=False turns off every secrets cache tier
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""CacheConfig.enabled=False turns off every secrets cache tier."""

from pathlib import Path

import pytest

from scalo.secrets.exceptions import ProviderError
from scalo.secrets.manager import SecretsManager
from scalo.secrets.providers.file import FileProvider
from scalo.secrets.types import CacheConfig, RotationEvent, SecretValue

both_paths = pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])


class _CountingFileProvider(FileProvider):
    """The real file provider, counting how often the manager reads it."""

    def __init__(self) -> None:
        self.reads = 0

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        self.reads += 1
        return super().get_sync(path, key)


def _manager(tmp_path: Path, provider: FileProvider, *, enabled: bool, ttl_secs: int = 3600) -> SecretsManager:
    return SecretsManager(
        providers={"file": provider},
        cache_config=CacheConfig(enabled=enabled, directory=str(tmp_path / "cache"), ttl_secs=ttl_secs),
    )


async def _get(manager: SecretsManager, path: Path, *, use_async: bool) -> bytes:
    if use_async:
        return (await manager.get(str(path))).data
    return manager.get_sync(str(path)).data


def _break(secret_file: Path) -> None:
    """Swap the secret file for a directory, so the file provider raises ProviderError."""
    secret_file.unlink()
    secret_file.mkdir()


@both_paths
async def test_disabled_cache_reads_the_provider_on_every_get(tmp_path, use_async):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    provider = _CountingFileProvider()
    manager = _manager(tmp_path, provider, enabled=False)

    assert await _get(manager, secret_file, use_async=use_async) == b"v1"
    secret_file.write_bytes(b"v2")
    assert await _get(manager, secret_file, use_async=use_async) == b"v2"
    assert await _get(manager, secret_file, use_async=use_async) == b"v2"

    assert provider.reads == 3
    assert manager._memory_cache == {}
    assert not (tmp_path / "cache").exists()


@both_paths
async def test_disabled_cache_raises_when_the_provider_fails(tmp_path, use_async):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    manager = _manager(tmp_path, FileProvider(), enabled=False)

    assert await _get(manager, secret_file, use_async=use_async) == b"v1"
    _break(secret_file)

    with pytest.raises(ProviderError):
        await _get(manager, secret_file, use_async=use_async)


@both_paths
async def test_disabled_cache_emits_no_rotation_event(tmp_path, use_async):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    events: list[RotationEvent] = []
    manager = _manager(tmp_path, FileProvider(), enabled=False)
    manager.on_rotation(events.append)

    assert await _get(manager, secret_file, use_async=use_async) == b"v1"
    secret_file.write_bytes(b"v2-rotated")
    assert await _get(manager, secret_file, use_async=use_async) == b"v2-rotated"

    assert events == []


@both_paths
async def test_enabled_cache_serves_repeat_reads_from_cache(tmp_path, use_async):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    provider = _CountingFileProvider()
    manager = _manager(tmp_path, provider, enabled=True)

    assert await _get(manager, secret_file, use_async=use_async) == b"v1"
    secret_file.write_bytes(b"v2")
    assert await _get(manager, secret_file, use_async=use_async) == b"v1"

    assert provider.reads == 1


@both_paths
async def test_enabled_cache_serves_the_stale_value_when_the_provider_fails(tmp_path, use_async):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    manager = _manager(tmp_path, FileProvider(), enabled=True, ttl_secs=0)

    assert await _get(manager, secret_file, use_async=use_async) == b"v1"
    _break(secret_file)

    assert await _get(manager, secret_file, use_async=use_async) == b"v1"
