# Project:   hs-pylib
# File:      examples/postgres-cache/tests/test_main.py
# Purpose:   Tests for postgres-cache example
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2026 HyperSec

"""Tests for postgres-cache example.

These tests verify the example code structure and key generation.
Integration tests require PostgreSQL (skipped if not available).
"""

import pytest

from hs_pylib.cache import generate_cache_key


class TestKeyGeneration:
    """Tests for cache key generation."""

    def test_generate_cache_key_basic(self) -> None:
        """Should generate a key from components."""
        key = generate_cache_key("analytics", "events")
        assert isinstance(key, str)
        assert len(key) > 0

    def test_generate_cache_key_deterministic(self) -> None:
        """Same inputs should produce same key."""
        key1 = generate_cache_key("analytics", "events", org_id="acme")
        key2 = generate_cache_key("analytics", "events", org_id="acme")
        assert key1 == key2

    def test_generate_cache_key_different_inputs(self) -> None:
        """Different inputs should produce different keys."""
        key1 = generate_cache_key("analytics", "events", org_id="acme")
        key2 = generate_cache_key("analytics", "events", org_id="other")
        assert key1 != key2

    def test_generate_cache_key_with_kwargs(self) -> None:
        """Should handle keyword arguments."""
        key = generate_cache_key("prefix", date="2026-01-19", user_id=123)
        assert isinstance(key, str)


class TestImports:
    """Tests for module imports."""

    def test_postgres_cache_import(self) -> None:
        """Should be able to import PostgresCache."""
        from hs_pylib.cache import PostgresCache

        assert PostgresCache is not None

    def test_main_module_import(self) -> None:
        """Should be able to import main module."""
        import main

        assert hasattr(main, "main")
        assert hasattr(main, "demonstrate_basic_operations")


@pytest.mark.skipif(
    True,  # Skip by default - requires PostgreSQL
    reason="Integration tests require PostgreSQL (run with docker compose up -d)",
)
class TestIntegration:
    """Integration tests requiring PostgreSQL.

    Run with: docker compose up -d && uv run pytest -k Integration
    """

    @pytest.mark.asyncio
    async def test_cache_round_trip(self) -> None:
        """Should be able to set and get a value."""
        from hs_pylib.cache import PostgresCache

        cache = PostgresCache(dsn="postgresql://postgres:postgres@localhost:5432/cache_example")
        await cache.init()

        try:
            key = "test:round_trip"
            value = {"test": True}

            await cache.set(key, value, ttl_seconds=60)
            retrieved = await cache.get(key)

            assert retrieved == value
        finally:
            await cache.close()
