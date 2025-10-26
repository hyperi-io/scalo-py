# ci-local/ Directory Structure and Usage

## Understanding the Two Environments

Your project uses two completely separate Python environments that serve different purposes. It's important to understand which is which to avoid confusion.

### 1. Your Project Environment (What You're Building)

This is the application or library you're actually developing.

**Location:** Root of the repository
**Virtual environment:** `.venv/` (at project root)
**Dependencies:** Defined in `pyproject.toml` at root, locked in `uv.lock`

**Contains:**
- Your application code (`src/` directory)
- Runtime dependencies your app needs (dynaconf, loguru, pyyaml, requests, etc.)
- Development tools you use interactively (ipython, jupyter, etc.)

**When you use it:**
- Writing code in your IDE
- Running your application manually
- Debugging and testing features interactively
- Any development work on your actual project

**Example:**
```bash
# Activate this environment for normal development
source .venv/bin/activate

# Your app's dependencies work here
python -c "import dynaconf, loguru"  # ✅ Works - these are your project deps

# But CI tools aren't installed here
python -c "import pytest, ruff"      # ❌ Fails - CI tools live elsewhere
```

### 2. CI Environment (Testing & Build Automation)

This is the separate infrastructure that tests, builds, and publishes your project.

**Location:** `ci-local/` directory
**Virtual environment:** `ci-local/.venv/`
**Dependencies:** Defined in `ci-local/pyproject.toml`, locked in `ci-local/uv.lock`

**Contains:**
- Testing tools (pytest, coverage)
- Linters and formatters (ruff, black, mypy)
- Build tools (python-build, twine, semantic-release)
- CI scripts from the `ci/` submodule

**When you use it:**
- You don't use it directly - CI scripts use it automatically
- When you run `./ci/bootstrap --install` or `./ci/run check`
- During automated testing and builds

**Example:**
```bash
# You DON'T activate this manually - it's for automation only
# CI scripts reference it explicitly like this:
ci-local/.venv/bin/python ci/modules/python/run/run.d/20-python-test.py check

# CI tools are installed here
ci-local/.venv/bin/python -c "import pytest, ruff"       # ✅ Works

# Your project dependencies might not be
ci-local/.venv/bin/python -c "import dynaconf, loguru"   # ❌ Probably fails
```

**Important:** Don't install your project's dependencies in `ci-local/.venv/`. Keep the two environments completely separate.

### Quick Reference

| What | Your Project | CI Automation |
|------|--------------|---------------|
| **What is it?** | The app/library you're building | Tools that test and build your app |
| **Source code** | `src/`, `tests/` | `ci/`, `ci-local/` |
| **Virtual env** | `.venv/` | `ci-local/.venv/` |
| **Config file** | `pyproject.toml` | `ci-local/pyproject.toml` |
| **Lock file** | `uv.lock` | `ci-local/uv.lock` |
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
├── .env                      # All CI env settings including JFrog credentials (gitignored, NEVER commit!)
└── ci-local/
    ├── .venv/                # CI tools virtual environment (gitignored, created by bootstrap)
    ├── ci.yaml               # Project CI configuration (committed, project-specific)
    ├── pyproject.toml        # CI tool dependencies (committed)
    ├── uv.lock               # Locked CI tool versions (committed)
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
- `ci.yaml` - Project CI configuration (languages, build settings, JFrog config)
- `pyproject.toml` - CI tool dependencies
- `uv.lock` - Locked CI tool versions (reproducible CI)
- Custom scripts in `*/bootstrap.d/`, `*/ci.d/` (if you create any)

### Gitignored Files (NEVER Commit)

**Never commit these:**
- `.env` - Secrets and credentials (JFrog, GitHub tokens, etc.)
- `.venv/` - Virtual environment (created by bootstrap)
- `logs/` - CI execution logs

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
- `ci-local/.venv/` - CI tools virtual environment
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
ci-local/.venv/bin/python ci-local/python/ci.d/85-my-check.py check

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

### "ci-local/.venv not found"

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
