# Project:   hyperi-pylib
# File:      examples/postgres-cache/main.py
# Purpose:   Demonstrate hyperi-pylib PostgreSQL cache
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
PostgreSQL Cache Example.

Demonstrates hyperi-pylib's PostgreSQL cache backend for multi-pod deployments.
Run with: uv run python main.py

Requires PostgreSQL running (use docker compose up -d).
"""

import asyncio
import os
from datetime import datetime

from hyperi_pylib.cache import PostgresCache, generate_cache_key
from hyperi_pylib.logger import error, info, success


# Default DSN for local development
DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/cache_example"


async def demonstrate_basic_operations(cache: PostgresCache) -> None:
    """Show basic cache get/set operations."""
    print("\n=== Basic Operations ===")

    # Simple key-value
    key = "user:123:profile"
    value = {"name": "Alice", "email": "alice@example.com", "role": "admin"}

    await cache.set(key, value, ttl_seconds=300)
    info("Set cache value", key=key, ttl=300)

    retrieved = await cache.get(key)
    info("Got cache value", key=key, value=retrieved)

    # Check it matches
    assert retrieved == value
    success("Basic get/set working correctly")


async def demonstrate_key_generation(cache: PostgresCache) -> None:
    """Show deterministic key generation."""
    print("\n=== Key Generation ===")

    # Generate keys with components
    key1 = generate_cache_key("analytics", "events", org_id="acme", date="2026-01-19")
    key2 = generate_cache_key("analytics", "events", org_id="acme", date="2026-01-19")
    key3 = generate_cache_key("analytics", "events", org_id="other", date="2026-01-19")

    info("Generated keys", key1=key1, key2=key2, key3=key3)

    # Same inputs = same key (deterministic)
    assert key1 == key2
    # Different inputs = different key
    assert key1 != key3

    success("Key generation is deterministic")


async def demonstrate_namespaces(cache: PostgresCache) -> None:
    """Show namespace-based organisation."""
    print("\n=== Namespaces ===")

    # Set values in different namespaces
    await cache.set("key1", {"data": "analytics"}, namespace="analytics", ttl_seconds=60)
    await cache.set("key2", {"data": "reports"}, namespace="reports", ttl_seconds=60)
    await cache.set("key3", {"data": "more analytics"}, namespace="analytics", ttl_seconds=60)

    info("Set values in namespaces", analytics=2, reports=1)

    # Invalidate entire namespace
    deleted = await cache.invalidate_by_namespace("analytics")
    info("Invalidated analytics namespace", deleted_count=deleted)

    # Reports namespace should still exist
    reports_value = await cache.get("key2", namespace="reports")
    assert reports_value is not None
    success("Namespace isolation working correctly")


async def demonstrate_bulk_invalidation(cache: PostgresCache) -> None:
    """Show bulk invalidation patterns."""
    print("\n=== Bulk Invalidation ===")

    # Set up test data
    for i in range(5):
        await cache.set(
            f"tenant:acme:item:{i}",
            {"item": i},
            ttl_seconds=300,
            org_id="acme",
        )
        await cache.set(
            f"tenant:other:item:{i}",
            {"item": i},
            ttl_seconds=300,
            org_id="other",
        )

    info("Created test data", acme_items=5, other_items=5)

    # Invalidate by org_id
    deleted = await cache.invalidate_by_org_id("acme")
    info("Invalidated by org_id", org_id="acme", deleted_count=deleted)

    # Check other org still has data
    other_value = await cache.get("tenant:other:item:0")
    assert other_value is not None
    success("Org-based invalidation working correctly")


async def demonstrate_ttl_expiration(cache: PostgresCache) -> None:
    """Show TTL-based expiration."""
    print("\n=== TTL Expiration ===")

    # Set value with short TTL
    key = "expires:soon"
    await cache.set(key, {"temporary": True}, ttl_seconds=1)
    info("Set value with 1 second TTL", key=key)

    # Should exist immediately
    value = await cache.get(key)
    assert value is not None
    info("Value exists immediately")

    # Wait for expiration
    print("Waiting 2 seconds for expiration...")
    await asyncio.sleep(2)

    # Should be expired now
    value = await cache.get(key)
    assert value is None
    success("TTL expiration working correctly")


async def demonstrate_statistics(cache: PostgresCache) -> None:
    """Show cache statistics."""
    print("\n=== Cache Statistics ===")

    # Generate some hits and misses
    await cache.set("stats:test", {"data": "test"}, ttl_seconds=60)

    # Hits
    for _ in range(5):
        await cache.get("stats:test")

    # Misses
    for _ in range(3):
        await cache.get("stats:nonexistent")

    stats = await cache.get_stats()
    info(
        "Cache statistics",
        total_entries=stats.get("total_entries", 0),
        hits=stats.get("hits", 0),
        misses=stats.get("misses", 0),
        hit_rate=f"{stats.get('hit_rate', 0):.1%}",
    )

    success("Statistics collection working")


async def main() -> None:
    """Run the PostgreSQL cache demonstration."""
    dsn = os.environ.get("POSTGRES_DSN", DEFAULT_DSN)
    info("PostgreSQL cache example starting", dsn=dsn.split("@")[1] if "@" in dsn else dsn)

    print("=== hyperi-pylib PostgreSQL Cache Demo ===")

    try:
        # Initialise cache
        cache = PostgresCache(dsn=dsn)
        await cache.init()
        success("Cache initialised")

        # Run demonstrations
        await demonstrate_basic_operations(cache)
        await demonstrate_key_generation(cache)
        await demonstrate_namespaces(cache)
        await demonstrate_bulk_invalidation(cache)
        await demonstrate_ttl_expiration(cache)
        await demonstrate_statistics(cache)

        # Clean up
        await cache.close()
        success("Cache closed")

        print("\n=== All demonstrations completed successfully ===")

    except Exception as e:
        error("Failed to run demonstration", error=str(e))
        print(f"\nError: {e}")
        print("\nMake sure PostgreSQL is running:")
        print("  docker compose up -d")
        raise


if __name__ == "__main__":
    asyncio.run(main())
