#  Project:   hyperi-pylib
#  File:      tests/unit/test_cache_diskcache_extra.py
#  Purpose:   Cache falls back to memory when diskcache absent
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""[cache] does NOT pull diskcache (CVE-2025-69872, no fix). The cache
module must degrade to in-memory cashews when diskcache is missing."""

from __future__ import annotations

import sys

import pytest

from hyperi_pylib.cache.cache import cached, configure_cache


@pytest.mark.asyncio
async def test_memory_fallback_round_trips_without_diskcache(monkeypatch, tmp_path):
    """diskcache import blocked (it's not in [cache] -- CVE-2025-69872).
    configure_cache must fall back to in-memory cashews and still round-trip."""
    monkeypatch.setitem(sys.modules, "diskcache", None)

    configure_cache(directory=str(tmp_path))

    @cached("dcfallback", ttl=60)
    async def double(x: int) -> int:
        return x * 2

    assert await double(21) == 42
    assert await double(21) == 42  # cache hit, same result
