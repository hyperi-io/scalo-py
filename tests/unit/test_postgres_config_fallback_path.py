#  Project:   hyperi-pylib
#  File:      tests/unit/test_postgres_config_fallback_path.py
#  Purpose:   PG fallback file must default to ~/.cache, never /tmp
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""PG fallback file defaults to ~/.cache, never /tmp; 0o600 perms."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hyperi_pylib.config.postgres_loader import PostgresConfigLoader


def test_default_fallback_path_is_under_home_cache(monkeypatch):
    """When neither --fallback-file nor HYPERI_CONFIG_FALLBACK_FILE is
    set, the path lives under ~/.cache, NEVER /tmp."""
    monkeypatch.delenv("HYPERI_CONFIG_FALLBACK_FILE", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    loader = PostgresConfigLoader(
        dsn="postgresql://u:p@h:5432/d",
        fallback_enabled=True,
    )
    path = loader.fallback_file
    home = Path.home()
    assert str(path).startswith(str(home)), f"fallback escaped home: {path}"
    assert "/tmp" not in str(path)
    assert "hyperi-ai" in str(path)
    assert path.name.endswith(".yaml")


def test_default_fallback_path_respects_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("HYPERI_CONFIG_FALLBACK_FILE", raising=False)

    loader = PostgresConfigLoader(
        dsn="postgresql://u:p@h:5432/d",
        fallback_enabled=True,
    )
    assert str(loader.fallback_file).startswith(str(tmp_path))


def test_env_var_overrides_default(monkeypatch, tmp_path):
    explicit = tmp_path / "custom.yaml"
    monkeypatch.setenv("HYPERI_CONFIG_FALLBACK_FILE", str(explicit))

    loader = PostgresConfigLoader(
        dsn="postgresql://u:p@h:5432/d",
        fallback_enabled=True,
    )
    assert loader.fallback_file == explicit


def test_explicit_arg_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HYPERI_CONFIG_FALLBACK_FILE", str(tmp_path / "from_env.yaml"))
    explicit = tmp_path / "from_arg.yaml"

    loader = PostgresConfigLoader(
        dsn="postgresql://u:p@h:5432/d",
        fallback_enabled=True,
        fallback_file=str(explicit),
    )
    assert loader.fallback_file == explicit


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode semantics only")
def test_fallback_file_written_with_0o600_and_parent_0o700(tmp_path):
    """When the fallback file is actually written, parent dir is 0o700
    and the file itself is 0o600. Owner-only access."""
    target = tmp_path / "deep" / "nested" / "fallback.yaml"
    loader = PostgresConfigLoader(
        dsn="postgresql://u:p@h:5432/d",
        fallback_enabled=True,
        fallback_file=str(target),
    )

    ok = loader._write_fallback_file({"foo": "bar", "secret_field": "value"})
    assert ok is True
    assert target.exists()

    file_mode = stat.S_IMODE(target.stat().st_mode)
    parent_mode = stat.S_IMODE(target.parent.stat().st_mode)
    assert file_mode == 0o600, f"file mode {oct(file_mode)} (want 0o600)"
    assert parent_mode == 0o700, f"parent mode {oct(parent_mode)} (want 0o700)"
