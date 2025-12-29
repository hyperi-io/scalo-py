# Project:   hs-pylib
# File:      tests/unit/test_cache.py
# Purpose:   Unit tests for hs_pylib.cache module
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""Unit tests for hs_pylib.cache module."""

import pytest


class TestCacheImports:
    """Test cache module imports."""

    def test_import_cache(self):
        """Test cache can be imported."""
        from hs_pylib.cache import cache

        assert cache is not None

    def test_import_configure_cache(self):
        """Test configure_cache can be imported."""
        from hs_pylib.cache import configure_cache

        assert configure_cache is not None

    def test_import_cached(self):
        """Test cached decorator can be imported."""
        from hs_pylib.cache import cached

        assert cached is not None

    def test_import_get_ttl(self):
        """Test get_ttl can be imported."""
        from hs_pylib.cache import get_ttl

        assert get_ttl is not None

    def test_import_get_cached(self):
        """Test get_cached can be imported."""
        from hs_pylib.cache import get_cached

        assert get_cached is not None

    def test_import_set_cached(self):
        """Test set_cached can be imported."""
        from hs_pylib.cache import set_cached

        assert set_cached is not None

    def test_import_invalidate_source(self):
        """Test invalidate_source can be imported."""
        from hs_pylib.cache import invalidate_source

        assert invalidate_source is not None


class TestGetTtl:
    """Tests for get_ttl function."""

    def test_returns_default_for_unknown_source(self):
        """Test returns default TTL for unknown source."""
        from hs_pylib.cache import cache as cache_mod

        # Access module-level variables through the cache module
        import sys
        cache_module = sys.modules["hs_pylib.cache.cache"]

        # Save original state
        original = cache_module._source_ttls.copy()

        try:
            # Reset module state
            cache_module._source_ttls = {"_default": "1h"}

            from hs_pylib.cache import get_ttl

            assert get_ttl("unknown") == "1h"
        finally:
            # Restore original state
            cache_module._source_ttls = original

    def test_returns_source_specific_ttl(self):
        """Test returns source-specific TTL when configured."""
        from hs_pylib.cache import cache as cache_mod

        import sys
        cache_module = sys.modules["hs_pylib.cache.cache"]

        # Save original state
        original = cache_module._source_ttls.copy()

        try:
            # Setup source TTLs directly
            cache_module._source_ttls = {
                "_default": "1h",
                "http": "24h",
                "db": "30m",
            }

            from hs_pylib.cache import get_ttl

            assert get_ttl("http") == "24h"
            assert get_ttl("db") == "30m"
            assert get_ttl("other") == "1h"
        finally:
            # Restore original state
            cache_module._source_ttls = original


class TestCachedDecorator:
    """Tests for cached decorator."""

    def test_cached_is_callable(self):
        """Test cached returns a callable."""
        from hs_pylib.cache import cached

        decorator = cached("http")
        assert callable(decorator)

    def test_cached_with_key(self):
        """Test cached decorator with key template."""
        from hs_pylib.cache import cached

        # Just verify it doesn't raise
        decorator = cached("http", key="{url}")
        assert callable(decorator)

    def test_cached_with_ttl_override(self):
        """Test cached decorator with TTL override."""
        from hs_pylib.cache import cached

        # Just verify it doesn't raise
        decorator = cached("http", ttl="30m")
        assert callable(decorator)


def _get_cache_module():
    """Helper to get the cache module."""
    from hs_pylib.cache import cache as cache_mod  # noqa: F401 - trigger import
    import sys
    return sys.modules["hs_pylib.cache.cache"]


class TestConfigureCache:
    """Tests for configure_cache function - uses temp directory for real cache."""

    def test_configure_sets_ttls(self, temp_dir):
        """Test configure_cache sets TTLs correctly."""
        cache_module = _get_cache_module()

        # Save original state
        original_ttls = cache_module._source_ttls.copy()
        original_configured = cache_module._configured

        try:
            from hs_pylib.cache import configure_cache, get_ttl

            configure_cache(
                directory=str(temp_dir / "cache"),
                default_ttl="2h",
                source_ttls={"http": "12h", "tavily": "30m"},
            )

            assert get_ttl("http") == "12h"
            assert get_ttl("tavily") == "30m"
            assert get_ttl("other") == "2h"
            assert cache_module._configured is True
        finally:
            # Restore original state
            cache_module._source_ttls = original_ttls
            cache_module._configured = original_configured

    def test_configure_with_metrics(self, temp_dir):
        """Test configure_cache sets up metrics counters."""
        cache_module = _get_cache_module()
        from unittest.mock import MagicMock

        # Save original state
        original_hits = cache_module._hits_counter
        original_misses = cache_module._misses_counter
        original_metrics = cache_module._metrics

        try:
            mock_metrics = MagicMock()
            mock_counter = MagicMock()
            mock_metrics.counter = MagicMock(return_value=mock_counter)

            from hs_pylib.cache import configure_cache

            configure_cache(
                directory=str(temp_dir / "cache"),
                metrics=mock_metrics,
            )

            # Should create hit and miss counters
            assert mock_metrics.counter.call_count == 2
            assert cache_module._hits_counter is not None
            assert cache_module._misses_counter is not None
        finally:
            # Restore original state
            cache_module._hits_counter = original_hits
            cache_module._misses_counter = original_misses
            cache_module._metrics = original_metrics


class TestCacheMetricsIntegration:
    """Tests for cache metrics integration."""

    def test_metrics_counters_created_with_correct_names(self, temp_dir):
        """Test metrics counters are created with correct names."""
        cache_module = _get_cache_module()
        from unittest.mock import MagicMock

        # Save original state
        original_hits = cache_module._hits_counter
        original_misses = cache_module._misses_counter
        original_metrics = cache_module._metrics

        try:
            mock_metrics = MagicMock()
            mock_metrics.counter = MagicMock(return_value=MagicMock())

            from hs_pylib.cache import configure_cache

            configure_cache(directory=str(temp_dir / "cache"), metrics=mock_metrics)

            # Check counter names
            calls = mock_metrics.counter.call_args_list
            call_names = [call[0][0] for call in calls]
            assert "cache_hits_total" in call_names
            assert "cache_misses_total" in call_names
        finally:
            # Restore original state
            cache_module._hits_counter = original_hits
            cache_module._misses_counter = original_misses
            cache_module._metrics = original_metrics
