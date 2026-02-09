# hyperi-pylib Logging

Auto-configured structured logging with sensible defaults.

## Quick Start

```python
from hyperi_pylib import logger

logger.info("Application started")
logger.error("Failed to connect", database="prod-db", retry=3)
logger.success("Deployment complete")
```

Output:
```
2025-11-04T10:00:00.000+1100 | INFO | myapp:main:42 - Application started
2025-11-04T10:00:01.000+1100 | ERROR | myapp:main:45 - Failed to connect database=prod-db retry=3
```

## Auto-Configuration

Logger configures itself on import with production-ready defaults:

- **Output:** stderr (standard for logs)
- **Level:** INFO
- **Format:** RFC 3339 timestamps + Solarized colors
- **Emojis:** Auto-detect (TTY: yes, containers: no)

Opt-out of auto-config:
```bash
export HYPERI_LIB_NO_LOGGER_CONFIG=1  # Configure manually
```

## Configuration

Override defaults via ENV variables or settings.yaml (7-layer cascade).

### Environment Variables

Standard cloud-native/K8s variables:

```bash
LOG_LEVEL=DEBUG              # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json              # json, text, console, logfmt
LOG_OUTPUT=stdout            # stdout, stderr, file
LOG_COLOR=false              # Disable colors (or NO_COLOR=1)
LOG_TIMESTAMP_FORMAT=rfc3339 # iso8601, rfc3339, unix, epoch
LOG_CALLER=true              # Include source location
LOG_STACKTRACE_LEVEL=ERROR   # Minimum level for stack traces
```

### settings.yaml

```yaml
logging:
  level: INFO
  format: console       # Human-readable for dev
  output: stderr
  color: true           # Auto-disabled if not TTY
  timestamp_format: rfc3339
  caller: true          # Show file:line
  stacktrace_level: ERROR
```

## Container Deployment

Production K8s (JSON logs for aggregation):
```bash
LOG_FORMAT=json LOG_OUTPUT=stdout LOG_LEVEL=INFO
```

Staging (human-readable):
```bash
LOG_FORMAT=console LOG_OUTPUT=stderr LOG_LEVEL=DEBUG
```

## Features

- **RFC 3339 Timestamps** - Standard across all environments
- **Structured Logging** - Key-value pairs for searchability
- **CHARS-POLICY.md Compliant** - ASCII logs, approved emojis only
- **Container-Aware** - Auto-detects TTY, disables colors in K8s
- **Sensitive Data Masking** - Automatic password/token redaction
- **Configuration Cascade** - ENV > .env > settings.yaml > defaults

## Sensitive Data Masking

Automatically masks passwords, tokens, API keys, secrets in logs.

Enabled by default. Disable (not recommended):
```bash
export HYPERI_LIB_LOGGING__MASK_SENSITIVE_DATA=false
```

### Supported Formats

- JSON: `{"password": "secret"}` → `{"password": "***REDACTED***"}`
- Form data: `password=secret` → `password=***REDACTED***`
- Database URLs: `postgres://user:pass@host` → `postgres://user:***REDACTED***@host`

### Custom Sensitive Fields

```python
from hyperi_pylib.logger.filters import SensitiveDataFilter

SensitiveDataFilter.add_sensitive_fields({"employee_id", "ssn"})
```

## Advanced: Presidio ML-Based Masking

For compliance-critical logs (HIPAA, GDPR, PCI-DSS):

```bash
pip install hyperi-pylib[presidio]
```

```python
from hyperi_pylib.logger import configure_logger

configure_logger(masking_level="advanced")  # Uses Presidio
```

Detects 50+ entity types (SSNs, credit cards, phone numbers, etc.) with ML.

Note: Slower than regex (5-50ms vs <1ms per log message).

## Technical Details

Built on Loguru with:
- RFC 3339 timestamp compliance
- Solarized color palette (terminal only)
- Emoji support for log levels (✅ ❌ ⚠️ 💥)
- Automatic emoji → text conversion for machine logs
- Source location tracking (file:line:function)

## API Reference

See module docstring: `help(hyperi-pylib.logger)`
