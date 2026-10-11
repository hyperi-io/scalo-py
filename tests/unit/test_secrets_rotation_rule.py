#  Project:   scalo
#  File:      tests/unit/test_secrets_rotation_rule.py
#  Purpose:   A rotation event fires only when both versions are known and differ
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A rotation event fires only when both versions are known and they differ."""

from datetime import UTC, datetime

import pytest

from scalo.secrets.manager import SecretsManager
from scalo.secrets.types import CacheConfig, RotationEvent, SecretValue


def _value(version: str | None) -> SecretValue:
    return SecretValue(data=b"value", fetched_at=datetime.now(UTC), version=version)


@pytest.mark.parametrize(
    ("old_version", "new_version", "expected"),
    [
        pytest.param("v1", "v2", [("v1", "v2")], id="changed"),
        pytest.param("v1", "v1", [], id="unchanged"),
        pytest.param(None, "v2", [], id="old-unversioned"),
        pytest.param("v1", None, [], id="new-unversioned"),
    ],
)
def test_rotation_fires_only_for_a_known_change(old_version, new_version, expected):
    events: list[RotationEvent] = []
    manager = SecretsManager(cache_config=CacheConfig(enabled=False))
    manager.on_rotation(events.append)

    manager._check_rotation("k", _value(old_version), _value(new_version))

    assert [(e.old_version, e.new_version) for e in events] == expected


def test_rotation_needs_a_previous_value():
    events: list[RotationEvent] = []
    manager = SecretsManager(cache_config=CacheConfig(enabled=False))
    manager.on_rotation(events.append)

    manager._check_rotation("k", None, _value("v2"))

    assert events == []
