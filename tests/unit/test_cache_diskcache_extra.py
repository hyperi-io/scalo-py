#  Project:   hyperi-pylib
#  File:      tests/unit/test_cache_diskcache_extra.py
#  Purpose:   [cache] extra must pull diskcache so disk backend is available
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""T7: docs promise [cache] extra brings diskcache. Verify the import."""

from __future__ import annotations


def test_diskcache_importable_in_dev_env():
    """If running in the dev env (which has [cache] installed via [dev]
    or via uv sync --all-extras), diskcache must import."""
    import diskcache

    assert hasattr(diskcache, "Cache")
