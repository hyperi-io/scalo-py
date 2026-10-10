#  Project:   scalo
#  File:      tests/unit/test_secrets_refresh.py
#  Purpose:   Background refresh re-fetches cached secrets, fresh entries included
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Background refresh re-fetches cached secrets from their provider, fresh entries included."""

from pathlib import Path

from scalo.secrets.manager import SecretsManager
from scalo.secrets.providers.file import FileProvider
from scalo.secrets.types import CacheConfig, RotationEvent


def _manager(tmp_path: Path) -> SecretsManager:
    return SecretsManager(
        providers={"file": FileProvider()},
        cache_config=CacheConfig(directory=str(tmp_path / "cache"), ttl_secs=3600),
    )


async def test_refresh_replaces_a_fresh_cached_value(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    manager = _manager(tmp_path)
    assert manager.get_sync(str(secret_file)).data == b"v1"
    secret_file.write_bytes(b"v2-rotated")

    await manager._refresh_all()

    assert manager.get_sync(str(secret_file)).data == b"v2-rotated"


async def test_refresh_reports_a_rotation_it_finds(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    events: list[RotationEvent] = []
    manager = _manager(tmp_path)
    manager.on_rotation(events.append)
    first = manager.get_sync(str(secret_file))
    secret_file.write_bytes(b"v2-rotated")

    await manager._refresh_all()

    assert [(e.old_version, e.new_version is not None) for e in events] == [(first.version, True)]
    assert events[0].new_version != first.version


async def test_refresh_reports_nothing_when_nothing_changed(tmp_path):
    secret_file = tmp_path / "secret.txt"
    secret_file.write_bytes(b"v1")
    events: list[RotationEvent] = []
    manager = _manager(tmp_path)
    manager.on_rotation(events.append)
    manager.get_sync(str(secret_file))

    await manager._refresh_all()

    assert events == []
