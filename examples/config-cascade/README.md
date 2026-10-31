# Config Cascade Example

Demonstrates scalo's 7-layer configuration cascade system.

## Features

- Automatic configuration merging from multiple sources
- Environment variable override support
- YAML configuration files
- Dynaconf-based settings management

## Quick Start

```bash
# Install dependencies
uv sync

# Run with default config
uv run python main.py

# Override with environment variables
DATABASE__HOST=prod-db.example.com uv run python main.py

# Load local values from .env
cp .env.example .env
uv run python main.py

# Run tests
uv run pytest
```

## Configuration Cascade (Priority Order)

1. **CLI arguments** (highest priority)
2. **Environment variables** - `DATABASE__HOST`
3. **.env file** - Local secrets (gitignored), loaded by the `get_config()` call at the top of `main()`
4. **settings.{env}.yaml** - Environment-specific, picked by `APP_ENV` (`APP_ENV=dev` loads `settings.dev.yaml`)
5. **settings.yaml** - Project base config
6. **defaults.yaml** - Safe fallback defaults
7. **Hard-coded defaults** (lowest priority)

Importing scalo reads no `.env`. An app that reads `settings` directly calls `get_config()` once at startup, as `main()` does here.

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

Variable names are bare by default. A double underscore nests the key:

```bash
# For settings.database.host
export DATABASE__HOST=localhost

# For settings.api.timeout
export API__TIMEOUT=30
```

With `ENV_PREFIX=MYAPP` set, the same keys read as `MYAPP_DATABASE__HOST` and `MYAPP_API__TIMEOUT`.

## Example Output

`DATABASE__HOST=prod-db uv run python main.py` ends with:

```
=== Environment Variable Override ===
Resolved database.host: prod-db
DATABASE__HOST env var: prod-db
(Environment variable takes precedence over config file)

=== Summary ===
Database: prod-db:5432
API: 0.0.0.0:8000
Cache: memory (TTL: 300s)
```

## See Also

- [scalo Configuration Documentation](../../docs/core-pillars/config.md)
