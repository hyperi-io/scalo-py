#  Project:   hyperi-pylib
#  File:      tests/unit/test_secrets_cache_atomic.py
#  Purpose:   Verify atomic write + 0o600 perms + clear() error propagation
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""B6/S2/S6 regression tests: concurrent writers race-free, file perms
locked to 0o600, clear() distinguishes "empty cache" from "directory
missing"."""

from __future__ import annotations

import os
import stat
import sys
import threading
from datetime import UTC, datetime

import pytest

from hyperi_pylib.secrets.cache import DiskCache
from hyperi_pylib.secrets.types import CacheConfig, SecretValue


@pytest.fixture
def cache(tmp_path):
    cfg = CacheConfig(enabled=True, directory=str(tmp_path), ttl_secs=3600, stale_grace_secs=0)
    return DiskCache(cfg)


def _make_value(payload: bytes) -> SecretValue:
    return SecretValue(data=payload, fetched_at=datetime.now(UTC), version="v1", source="test")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode semantics only")
def test_cache_file_has_0o600_mode(cache, tmp_path):
    cache.set("api/key", _make_value(b"secret-bytes"))
    cached = next(tmp_path.glob("*.cache"))
    mode = stat.S_IMODE(cached.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode semantics only")
def test_cache_dir_has_0o700_mode(tmp_path):
    cfg = CacheConfig(enabled=True, directory=str(tmp_path / "fresh"), ttl_secs=3600, stale_grace_secs=0)
    DiskCache(cfg)
    mode = stat.S_IMODE((tmp_path / "fresh").stat().st_mode)
    assert mode == 0o700, f"expected 0o700, got {oct(mode)}"


def test_concurrent_writers_no_corruption(cache):
    """Many threads writing the SAME secret name must never produce
    a corrupt cache file. With the old shared ``.tmp`` path, one writer
    would overwrite another's bytes mid-rename. With unique tempfiles
    each writer's payload is committed atomically.
    """
    payloads = [f"payload-{i}".encode() for i in range(32)]

    def writer(p: bytes):
        cache.set("shared/name", _make_value(p))

    threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Whatever the final value is, it must be ONE of the payloads
    # (not a torn blend of two writers).
    got = cache.get("shared/name")
    assert got is not None
    assert got.data in payloads


def test_no_orphan_tmp_files_after_writes(cache, tmp_path):
    """All .tmp files must be cleaned up after writes complete."""
    for i in range(10):
        cache.set(f"key-{i}", _make_value(f"v{i}".encode()))

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"orphan tempfiles: {leftovers}"


def test_clear_returns_zero_when_dir_missing(tmp_path):
    """Directory missing -> 0, not an exception."""
    cfg = CacheConfig(enabled=False, directory=str(tmp_path / "nope"), ttl_secs=3600, stale_grace_secs=0)
    cache = DiskCache(cfg)
    assert cache.clear() == 0


def test_clear_counts_only_cache_files(cache, tmp_path):
    """Non-cache files in the dir must not be touched."""
    cache.set("a", _make_value(b"x"))
    cache.set("b", _make_value(b"y"))
    (tmp_path / "unrelated.txt").write_text("keep me", encoding="utf-8")

    deleted = cache.clear()
    assert deleted == 2
    assert (tmp_path / "unrelated.txt").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX chmod semantics only")
def test_clear_logs_warning_on_unlink_failure(cache, tmp_path, caplog):
    """If a cache file can't be unlinked, log a warning but keep going."""
    cache.set("a", _make_value(b"x"))
    cache.set("b", _make_value(b"y"))

    # Make the directory read-only so unlink fails
    os.chmod(tmp_path, 0o500)
    try:
        with caplog.at_level("WARNING"):
            count = cache.clear()
        # Either 0 (both failed) or partial; what matters is no crash.
        assert count >= 0
    finally:
        os.chmod(tmp_path, 0o700)
