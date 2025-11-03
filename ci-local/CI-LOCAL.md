<!-- HYPERCI_STATE_MD: /projects/hyperlib/ci/modules/common/templates/CI-LOCAL.md -->
# ci-local/ Directory Structure and Usage

## Understanding the Unified Environment

HyperCI uses a **unified virtual environment** approach: ONE `.venv` at project root contains both your runtime dependencies AND CI tools.

### The Unified .venv Model

**Location:** `.venv/` at project root
**Dependencies:** Defined in `pyproject.toml`, locked in `uv.lock`

**Contains EVERYTHING:**
- Your application code (`src/` directory) - installed in editable mode
- Runtime dependencies (dynaconf, loguru, pyyaml, requests, etc.)
- CI/development tools (pytest, ruff, black, mypy, build, twine, etc.)

**Structure in pyproject.toml:**
```toml
[project]
dependencies = [
    "dynaconf>=3.2.12",  # Runtime deps only
    "loguru>=0.7.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",     # CI tools
    "ruff>=0.1.0",
    "black>=24.0.0",
    # ... all dev/CI tools
]
```

**When you use it:**
- Local development (activate and code)
- Running your application
- CI operations (./ci/run check, ./ci/run build)
- Testing (both manual and automated)

**Example:**
```bash
# Activate for development
source .venv/bin/activate

# Both runtime AND CI tools work
python -c "import dynaconf, loguru"  # ✅ Runtime deps
python -c "import pytest, ruff"      # ✅ CI tools

# Everything is in ONE place
which pytest  # .venv/bin/pytest
which python  # .venv/bin/python
```

### Quick Reference

| What | Unified Environment |
|------|---------------------|
| **Virtual env** | `.venv/` at project root |
| **Config file** | `pyproject.toml` (one file) |
| **Lock file** | `uv.lock` (one file) |
| **Runtime deps** | `[project] dependencies` |
| **CI/Dev tools** | `[project.optional-dependencies] dev` |
| **Installation** | `uv sync --all-extras` |
| **Used by** | Developer AND CI scripts |
| **Example packages** | dynaconf, loguru, requests | pytest, ruff, black, mypy |
| **You activate it?** | Yes, for dev work | No, CI scripts handle it |
| **IDE uses it?** | Yes, for autocomplete | No |

---

## Purpose

The `ci-local/` directory is the **project-writable** counterpart to the **READ-ONLY** `ci/` submodule.

**Separation of Concerns:**
- `ci/` - HyperCI submodule (READ-ONLY, shared scripts from hyperci repo)
- `ci-local/` - **CI-SPECIFIC** configuration and extensions (WRITABLE, gitignored data + committed config)

## Directory Structure

```
PROJECT_ROOT/
├── .venv/                    # Unified virtual environment (runtime + CI tools, gitignored)
├── .env                      # All secrets (project + CI, gitignored, NEVER commit!)
├── uv.lock                   # Locked dependencies (runtime + dev, committed)
├── pyproject.toml            # Project config with [optional-dependencies] dev (committed)
└── ci-local/
    ├── ci.yaml               # Project CI configuration (committed, project-specific)
    ├── logs/                 # CI logs (gitignored)
    │
    ├── common/               # Common (language-agnostic) extensions
    │   ├── bootstrap.d/      # Custom bootstrap scripts (optional, create as needed)
    │   └── ci.d/             # Custom CI scripts (optional, create as needed)
    │
    └── <language>/           # Language-specific extensions (e.g., python/)
        ├── bootstrap.d/      # Custom language bootstrap scripts (optional)
        └── ci.d/             # Custom language CI scripts (optional)
```

## What Goes Where

### Committed Files (Version Controlled)

**Always commit these:**
- `pyproject.toml` - Project config (runtime deps + [optional-dependencies] dev for CI tools)
- `uv.lock` - Locked dependencies (everything - runtime and dev)
- `ci-local/ci.yaml` - CI configuration (languages, build settings, JFrog config)
- Custom scripts in `ci-local/*/bootstrap.d/`, `ci-local/*/ci.d/` (if you create any)

### Gitignored Files (NEVER Commit)

**Never commit these:**
- `.venv/` - Virtual environment (created by bootstrap, contains everything)
- `.env` - Secrets and credentials (JFrog, GitHub tokens, etc.)
- `ci-local/logs/` - CI execution logs

## Configuration: ci.yaml

The `ci.yaml` file is the **single source of truth** for project CI configuration.

**Example ci.yaml:**

```yaml
# Project metadata
project:
  name: hyperlib
  languages:
    - python  # Or 'core' for language-agnostic projects

# Build configuration
nuitka:
  enabled: false
  build_type: package  # Options: package, app
  protection: recommended

# AI assistant configuration
ai:
  merge_mode: skip  # Options: skip, merge, no-overwrite, force
  _tier: pro  # Options: pro, pro-max

# Repository configuration
repository:
  github_org: hypersec-io
  github_repo: hyperlib
  jfrog:
    host: hypersec.jfrog.io
    pypi_repo: hypersec-pypi-local
```

**Config Cascade (Priority Order):**
```
CLI args > ENV vars > .env > ci.yaml > language/defaults.yaml > common/defaults.yaml
```

## Custom Scripts (Extensions)

You can extend HyperCI by adding custom scripts to `ci-local/`:

### Bootstrap Extensions

**When to use:** Add project-specific setup during bootstrap (e.g., install extra tools, configure environments)

**Location:** `ci-local/common/bootstrap.d/` or `ci-local/<language>/bootstrap.d/`

**Naming:** Use numeric prefixes to control execution order:
- `00-*.py` - Early setup
- `50-*.py` - Mid-bootstrap configuration
- `90-*.py` - Late validation

**Example:**
```python
# ci-local/python/bootstrap.d/50-install-custom-tool.py
#!/usr/bin/env python3
"""Install custom development tool."""
import sys
from pathlib import Path

# Standard ci_lib import pattern
_p = Path(__file__).resolve()
for _ in range(10):
    if (_p / "modules" / "common" / "ci_lib.py").exists():
        sys.path.insert(0, str(_p / "modules" / "common"))
        break
else:
    raise ImportError("Cannot find ci_lib.py")

from ci_lib import get_ci_paths

paths = get_ci_paths()
PROJECT_ROOT = paths['project_root']

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: 50-install-custom-tool.py [check|install]")
        return 1

    action = sys.argv[1]

    if action == "check":
        print("[INFO] Custom tool check")
        return 0
    elif action == "install":
        print("[INFO] Installing custom tool...")
        # Your installation logic here
        return 0
    else:
        return 0

if __name__ == "__main__":
    sys.exit(main())
```

### CI Script Extensions

**When to use:** Add custom CI checks, builds, or publish steps

**Location:** `ci-local/common/ci.d/` or `ci-local/<language>/ci.d/`

**Example:**
```python
# ci-local/python/ci.d/85-custom-security-scan.py
#!/usr/bin/env python3
"""Custom security scanning."""
import sys
from pathlib import Path

# Standard ci_lib import pattern
_p = Path(__file__).resolve()
for _ in range(10):
    if (_p / "modules" / "common" / "ci_lib.py").exists():
        sys.path.insert(0, str(_p / "modules" / "common"))
        break
else:
    raise ImportError("Cannot find ci_lib.py")

from ci_lib import get_ci_paths, run_command

paths = get_ci_paths()
PROJECT_ROOT = paths['project_root']

def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: 85-custom-security-scan.py [check|scan]")
        return 1

    action = sys.argv[1]

    if action == "check":
        print("[INFO] Security scan check")
        return 0
    elif action == "scan":
        print("[INFO] Running security scan...")
        # Your scan logic here
        return 0
    else:
        return 0

if __name__ == "__main__":
    sys.exit(main())
```

## Environment Variables (.env)

The `.env` file contains **secrets and credentials** - NEVER commit this file!

**Required variables:**

```bash
# JFrog Artifactory (required for bootstrap)
ARTIFACTORY_USERNAME=your-username
ARTIFACTORY_PASSWORD=your-password
# Or use token auth:
# ARTIFACTORY_TOKEN=your-token
# ARTIFACTORY_TOKEN_USER=artifactory@hypersec.io

# Optional: Override CI behavior
# CI_AI_MERGE_MODE=merge
# CI_AI__TIER=pro-max
# NUITKA_PROTECTION=recommended
```

**Security notes:**
- `.env` is gitignored by default (see `.gitignore` at project root)
- Use token auth for better security (tokens can be scoped and rotated)
- Store production credentials in GitHub Secrets, not `.env`

## Directory Creation

**Bootstrap creates these automatically:**
- `.venv/` - CI tools virtual environment
- `ci-local/logs/` - CI execution logs

**You create these as needed:**
- `ci-local/common/bootstrap.d/` - Only if you have custom bootstrap scripts
- `ci-local/common/ci.d/` - Only if you have custom CI scripts
- `ci-local/<language>/bootstrap.d/` - Only if you have language-specific bootstrap scripts
- `ci-local/<language>/ci.d/` - Only if you have language-specific CI scripts

**Empty directories are NOT created by default** - this keeps the structure clean and intentional.

## Common Workflows

### First-Time Setup

```bash
# 1. Clone project
git clone <project-url>
cd <project-name>

# 2. Create .env with credentials (at project root)
cat > .env << 'EOF'
ARTIFACTORY_USERNAME=your-username
ARTIFACTORY_PASSWORD=your-password
EOF

# 3. Run bootstrap
./ci/bootstrap --install
```

### Adding Custom CI Script

```bash
# 1. Create directory if needed
mkdir -p ci-local/python/ci.d

# 2. Create your script
cat > ci-local/python/ci.d/85-my-check.py << 'EOF'
#!/usr/bin/env python3
"""My custom CI check."""
import sys
from pathlib import Path

# Standard ci_lib import pattern
_p = Path(__file__).resolve()
for _ in range(10):
    if (_p / "modules" / "common" / "ci_lib.py").exists():
        sys.path.insert(0, str(_p / "modules" / "common"))
        break
else:
    raise ImportError("Cannot find ci_lib.py")

from ci_lib import get_ci_paths

paths = get_ci_paths()

def main() -> int:
    print("[INFO] Running my check...")
    return 0

if __name__ == "__main__":
    sys.exit(main())
EOF

# 3. Make executable
chmod +x ci-local/python/ci.d/85-my-check.py

# 4. Test it
.venv/bin/python ci-local/python/ci.d/85-my-check.py check

# 5. Commit it
git add ci-local/python/ci.d/85-my-check.py
git commit -m "feat: add custom CI check"
```

### Updating CI Configuration

```bash
# Edit ci.yaml
vim ci-local/ci.yaml

# Commit changes
git add ci-local/ci.yaml
git commit -m "chore: update CI config"
```

## Troubleshooting

### ".venv not found"

**Solution:** Run bootstrap:
```bash
./ci/bootstrap --install
```

### "Cannot find ci_lib.py"

**Solution:** Use the standard import pattern shown in examples above. The script must walk up to find `ci/modules/common/ci_lib.py`.

### "JFrog authentication failed"

**Solution:** Check `.env` (at project root) has valid credentials:
```bash
cat .env | grep ARTIFACTORY
```

### Custom script not running

**Solution:** Check numeric prefix (controls execution order):
```bash
ls -la ci-local/*/ci.d/*.py
# Should see: 00-*.py, 10-*.py, 20-*.py, etc.
```

## See Also

- [ci/docs/README.md](../../docs/README.md) - Complete HyperCI documentation
- [ci/docs/PROJECT-EXTENSIONS.md](../../docs/PROJECT-EXTENSIONS.md) - Custom scripts guide
- [ci/docs/CONFIG-CASCADE.md](../../docs/CONFIG-CASCADE.md) - Configuration priority rules
