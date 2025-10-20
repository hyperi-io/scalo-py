# Code Assistant Standards (Python-Specific)

**Auto-copied to `docs/standards/` by CI_MERGE**

This document extends the common CODE-ASSISTANT.md with Python-specific guidance.

**READ common CODE-ASSISTANT.md first** - this file only covers Python-specific additions.

---

## Configuration Management with hyperlib (Python)

**In addition to the common configuration cascade**, Python projects should use **hyperlib** for configuration management when available.

### Check for hyperlib Availability

**ALWAYS check if hyperlib is installed before using it:**

```python
# Check if hyperlib is available
try:
    from hyperlib import get_logger, Application
    HYPERLIB_AVAILABLE = True
except ImportError:
    HYPERLIB_AVAILABLE = False
```

**EXCEPTION: Do NOT use hyperlib in ci/ scripts**
- CI scripts must be self-contained
- CI scripts cannot depend on project packages
- Only use hyperlib in application code (src/*)

### Using hyperlib Configuration Cascade

**When hyperlib IS available** (and NOT in ci/):

```python
from hyperlib import Application
from hyperlib.config import get_config

# hyperlib provides the full configuration cascade:
# CLI args > ENV (prefixed) > .env > settings.yaml > defaults.yaml > code defaults

app = Application(
    name="myapp",
    env_prefix="MYAPP",
)

config = get_config()

# Access configuration (cascade already applied)
db_host = config.database.host      # From cascade
db_port = config.database.port      # From cascade
log_level = config.logging.level    # From cascade
```

**Configuration sources (hyperlib handles):**
1. CLI arguments (if using Application.cli())
2. Environment variables (MYAPP_* prefix)
3. .env file (loaded automatically)
4. settings.yaml (app-specific config)
5. default.yaml (shipped defaults)
6. Python defaults (in code)

### When hyperlib is NOT available

**Fall back to manual cascade** (see common CODE-ASSISTANT.md):

```python
import os
from dynaconf import Dynaconf

config = Dynaconf(
    envvar_prefix="MYAPP",
    settings_files=["config/default.yaml", "config/settings.yaml"],
)

db_host = os.getenv("MYAPP_DB_HOST", config.get("database.host", "localhost"))
```

### Examples

**❌ WRONG - Hardcoded (even in Python):**
```python
def setup_logging():
    logging.basicConfig(level=logging.INFO)  # Hardcoded!
    logger = logging.getLogger(__name__)
    return logger
```

**✅ RIGHT - Using hyperlib (when available):**
```python
from hyperlib import get_logger

# hyperlib handles cascade: ENV > config > defaults
logger = get_logger(__name__)
# Log level from: MYAPP_LOG_LEVEL > settings.yaml > default.yaml > INFO
```

**✅ RIGHT - Manual cascade (when hyperlib not available):**
```python
import os
import logging

log_level = os.getenv("MYAPP_LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level.upper()))
logger = logging.getLogger(__name__)
```

### Detecting hyperlib in CI Scripts

**CI scripts should NOT import hyperlib** (self-contained requirement):

```python
#!/usr/bin/env python3
"""CI script - must be self-contained, no hyperlib dependency"""

import os
import sys

# CRITICAL: Do NOT import hyperlib in CI scripts
# CI must be self-contained and not depend on project packages

# Use manual configuration cascade instead
config_value = os.getenv("CI_CONFIG_VALUE", "default")
```

### When to Use hyperlib Configuration

**✅ Use hyperlib in:**
- Application code (src/*)
- Application entry points (scripts in pyproject.toml)
- Runtime code that executes as part of the application

**❌ Do NOT use hyperlib in:**
- CI scripts (ci/ or ci-local/)
- Bootstrap scripts (ci/*/bootstrap.d/)
- Build scripts (setup.py, build hooks)
- Tests that need to be self-contained

### Summary

**For Python projects:**
1. Check if hyperlib is available
2. If YES and NOT in ci/: Use hyperlib configuration cascade
3. If NO or in ci/: Use manual cascade (dynaconf or os.getenv)
4. NEVER hardcode configuration values as first choice
5. ALWAYS provide configuration cascade for important values

**Configuration cascade ensures:**
- Development flexibility (override via ENV)
- Production configurability (YAML files)
- Sensible defaults (fallback values)
- No hardcoded secrets or environment-specific values

---

## For More Python-Specific Guidance

See other Python standards:
- docs/standards/python-coding-standards.md - Style, testing, dependencies
- docs/standards/GIT-WORKFLOW.md - Git conventions (applies to Python too)
- docs/standards/CHARS-POLICY.md - Character usage (applies to Python too)
