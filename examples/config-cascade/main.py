# Project:   hyperi-pylib
# File:      examples/config-cascade/main.py
# Purpose:   Demonstrate hyperi-pylib configuration cascade
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Config Cascade Example.

Demonstrates hyperi-pylib's 8-layer configuration cascade system.
Run with: uv run python main.py
"""

import os
from pathlib import Path

from hyperi_pylib.config import get_settings, settings
from hyperi_pylib.logger import info


def show_database_config() -> dict:
    """Display database configuration from cascade."""
    # Access config using attribute syntax
    config = {
        "host": settings.get("database.host", "localhost"),
        "port": settings.get("database.port", 5432),
        "name": settings.get("database.name", "myapp"),
        "pool_size": settings.get("database.pool_size", 5),
    }

    info("Database configuration loaded", **config)
    return config


def show_api_config() -> dict:
    """Display API configuration from cascade."""
    config = {
        "host": settings.get("api.host", "0.0.0.0"),
        "port": settings.get("api.port", 8000),
        "timeout": settings.get("api.timeout", 30),
    }

    info("API configuration loaded", **config)
    return config


def show_cache_config() -> dict:
    """Display cache configuration from cascade."""
    config = {
        "enabled": settings.get("cache.enabled", True),
        "ttl_seconds": settings.get("cache.ttl_seconds", 300),
        "backend": settings.get("cache.backend", "memory"),
    }

    info("Cache configuration loaded", **config)
    return config


def demonstrate_env_override() -> None:
    """Show how environment variables override config files."""
    print("\n=== Environment Variable Override ===")

    # Get current value
    original = settings.get("database.host", "localhost")
    print(f"Original database.host: {original}")

    # Show that env vars take precedence
    env_value = os.environ.get("DATABASE_HOST")
    if env_value:
        print(f"DATABASE_HOST env var: {env_value}")
        print("(Environment variable takes precedence over config file)")
    else:
        print("No DATABASE_HOST env var set")
        print("Set it with: DATABASE_HOST=prod-db uv run python main.py")


def demonstrate_config_files() -> None:
    """Show which config files are loaded."""
    print("\n=== Configuration Files ===")

    config_dir = Path(__file__).parent
    files = [
        ("settings.yaml", "Base configuration"),
        ("settings.dev.yaml", "Development overrides"),
        ("settings.prod.yaml", "Production overrides"),
        (".env", "Local secrets (gitignored)"),
    ]

    for filename, description in files:
        filepath = config_dir / filename
        status = "✓ exists" if filepath.exists() else "✗ not found"
        print(f"  {filename}: {description} [{status}]")


def get_all_config() -> dict:
    """Get all configuration as a dictionary."""
    return {
        "database": show_database_config(),
        "api": show_api_config(),
        "cache": show_cache_config(),
    }


def main() -> None:
    """Run the configuration demonstration."""
    info("Config cascade example starting")

    print("=== hyperi-pylib Configuration Cascade Demo ===\n")

    print("=== Current Configuration ===")
    config = get_all_config()

    demonstrate_config_files()
    demonstrate_env_override()

    print("\n=== Summary ===")
    print(f"Database: {config['database']['host']}:{config['database']['port']}")
    print(f"API: {config['api']['host']}:{config['api']['port']}")
    print(f"Cache: {config['cache']['backend']} (TTL: {config['cache']['ttl_seconds']}s)")

    info("Config cascade example finished")


if __name__ == "__main__":
    main()
