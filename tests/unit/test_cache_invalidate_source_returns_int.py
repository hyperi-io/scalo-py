#  Project:   hyperi-pylib
#  File:      tests/unit/test_cache_invalidate_source_returns_int.py
#  Purpose:   invalidate_source must return int (count), never None
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""T8: invalidate_source() annotated -> int but cashews delete_match
returns None for some backends. Coalesce to 0 so callers get a real int."""

from __future__ import annotations

import pytest

from hyperi_pylib.cache.cache import cache, cached, invalidate_source


@pytest.fixture(autouse=True)
def _cashews_memory_setup():
    """Cashews requires explicit setup. Memory backend has no I/O cost."""
    cache.setup("mem://")
    return


@pytest.mark.asyncio
async def test_invalidate_source_returns_int_empty():
    """Unknown source returns int (0), not None."""
    result = await invalidate_source("never-cached-prefix-xyz")
    assert isinstance(result, int)
    assert result >= 0


@pytest.mark.asyncio
async def test_invalidate_source_returns_int_after_caching():
    """After populating a source via @cached, invalidate returns int."""

    @cached("t8probe", ttl=60)
    async def fetcher(x: int) -> int:
        return x * 2

    await fetcher(1)
    await fetcher(2)

    result = await invalidate_source("t8probe")
    assert isinstance(result, int)
