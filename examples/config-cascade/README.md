# Config Cascade Example

Demonstrates hyperi-pylib's 7-layer configuration cascade system.

## Features

- Automatic configuration merging from multiple sources
- Environment variable override support
- YAML/JSON/TOML configuration files
- Dynaconf-based settings management

## Quick Start

```bash
# Install dependencies
uv sync

# Run with default config
uv run python main.py

# Override with environment variables
DATABASE_HOST=prod-db.example.com uv run python main.py

# Run tests
uv run pytest
```

## Configuration Cascade (Priority Order)

1. **CLI arguments** (highest priority)
2. **Environment variables** - `MYAPP_DATABASE_HOST`
3. **.env file** - Local secrets (gitignored)
4. **settings.local.yaml** - Local overrides
5. **settings.{env}.yaml** - Environment-specific (dev, prod)
6. **settings.yaml** - Project base config
7. **Hard-coded defaults** (lowest priority)

## Files in This Example

```
config-cascade/
├── main.py              # Application code
├── settings.yaml        # Base configuration
├── settings.dev.yaml    # Development overrides
├── .env.example         # Example environment file
└── tests/
    └── test_main.py     # Tests
```

## Environment Variables

Environment variables use the prefix from your app name:

```bash
# For settings.database.host
export MYAPP_DATABASE_HOST=localhost

# For settings.api.timeout
export MYAPP_API_TIMEOUT=30
```

## Example Output

```
=== Configuration Sources ===
Base config (settings.yaml):
  database.host = localhost
  database.port = 5432

With environment override (DATABASE_HOST=prod-db):
  database.host = prod-db
  database.port = 5432
```

## See Also

- [hyperi-pylib Configuration Documentation](../../docs/CONFIG.md)
