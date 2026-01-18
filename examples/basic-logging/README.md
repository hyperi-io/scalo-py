# Basic Logging Example

Demonstrates hs-pylib's structured logging with automatic environment detection.

## Features

- RFC 3339 timestamps with timezone
- Structured key-value logging
- Automatic console/JSON format switching
- Log level convenience functions

## Quick Start

```bash
# Install dependencies
uv sync

# Run the example
uv run python main.py

# Run with JSON output (simulates container environment)
HS_LOG_FORMAT=json uv run python main.py

# Run tests
uv run pytest
```

## What It Shows

1. **Basic logging** - info, debug, warning, error levels
2. **Structured context** - key-value pairs in log messages
3. **Environment detection** - auto-switches format based on environment
4. **Success/failure helpers** - semantic logging functions

## Output Formats

**Console (development):**

```
2026-01-19T10:30:00.123+11:00 | INFO     | main:main:15 - Application starting
2026-01-19T10:30:00.124+11:00 | INFO     | main:main:16 - Processing user user_id=123 action=login
```

**JSON (container/CI):**

```json
{"timestamp": "2026-01-19T10:30:00.123+11:00", "level": "INFO", "message": "Application starting"}
{"timestamp": "2026-01-19T10:30:00.124+11:00", "level": "INFO", "message": "Processing user", "user_id": 123, "action": "login"}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |
| `HS_LOG_FORMAT` | Output format (console, json) | auto-detected |
| `NO_COLOR` | Disable coloured output | unset |

## See Also

- [hs-pylib Logging Documentation](../../docs/LOGGING.md)
