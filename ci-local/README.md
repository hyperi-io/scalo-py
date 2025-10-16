# Project-Specific CI Extensions

This directory contains custom CI scripts for this project.

## Directory Structure

- `common/bootstrap.d/` - Common bootstrap scripts (runs during setup)
- `common/ci.d/` - Common CI scripts (runs during checks)
- `python/bootstrap.d/` - Python-specific bootstrap scripts
- `python/ci.d/` - Python-specific CI scripts

## Numbering Convention

Scripts are executed in numerical order, interleaved with standard scripts from ci/:

- **50-59**: Additional testing (runs between standard test and build)
- **60-79**: Custom build steps
- **90-99**: Custom deployment (runs after standard scripts)

## Example: Custom Bootstrap Script

`python/bootstrap.d/90-custom-setup.py`:
```python
#!/usr/bin/env python3
"""
Custom Bootstrap: Example Setup

Runs after all standard bootstrap scripts (90+).
"""
import sys

def check_action():
    print("[OK] Custom bootstrap check passed")
    return 0

def install_action():
    print("[INFO] Running custom bootstrap setup...")
    # Your custom setup here
    print("[OK] Custom bootstrap complete")
    return 0

def main():
    if len(sys.argv) < 2:
        return 0
    action = sys.argv[1]
    if action == "check":
        return check_action()
    elif action == "install":
        return install_action()
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Example: Custom CI Script

`python/ci.d/50-custom-check.py`:
```python
#!/usr/bin/env python3
"""
Custom CI: Example Check

Runs between standard tests (20) and build (80).
"""
import sys
from pathlib import Path

# Import from ci_lib (from ci/ submodule)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "ci/common"))
from ci_lib import logger

def main():
    logger.info("Running custom CI check...")
    # Your custom CI logic here
    logger.info("✅ Custom check passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Documentation

See [ci/docs/PROJECT-EXTENSIONS.md](ci/docs/PROJECT-EXTENSIONS.md) for complete guide.
