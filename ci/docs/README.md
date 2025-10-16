# HyperCI Documentation

Central CI/CD infrastructure for all HyperSec Python projects.

## Quick Start

### New Project Setup (5 minutes)

```bash
# 1. Add hyperci as git subtree
git subtree add --prefix ci https://github.com/hypersec-io/hyperci.git main --squash

# 2. Bootstrap creates ci.yaml from template automatically
./ci/bootstrap --install

# 3. Customize your project settings
vim ci.yaml  # Edit: python.min_version, nuitka settings, etc.

# 4. Commit
git add ci.yaml .gitignore
git commit -m "feat: add HyperCI infrastructure"

# 5. Run CI locally
ci/.venv/bin/python ci/python/ci.d/20-python-test.py check
ci/.venv/bin/python ci/python/ci.d/85-build-nuitka.py build
```

That's it! You now have the full HyperCI pipeline.

## Project Structure Requirements

HyperCI expects projects to follow this structure:

### Required Structure

```
your-project/
├── ci/                    # ← Git subtree from hypersec-io/hyperci
│   ├── bootstrap          # Entry point
│   ├── python/ci.d/*.py   # CI scripts
│   └── ...                # (all from hyperci)
│
├── ci.yaml                # ← PROJECT-SPECIFIC (created from ci/ci.yaml.template)
│
├── .env                   # JFrog credentials (ARTIFACTORY_USERNAME, ARTIFACTORY_PASSWORD)
├── .gitignore             # Must include: ci/.venv/
│
└── (Python package structure - see below)
```

### Python Package Structure (Assumed)

**For Libraries:**
```
your-project/
├── src/
│   └── your_package/
│       ├── __init__.py
│       └── *.py
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml         # Package metadata and dependencies
├── setup.py               # Optional: For Nuitka bdist_nuitka
├── README.md
└── VERSION                # Optional: Semantic version (auto-managed)
```

**For Applications:**
```
your-project/
├── src/
│   └── your_app/
│       ├── __main__.py    # Entry point
│       └── *.py
├── pyproject.toml
│   [project.scripts]      # Entry point definition
│     your-app = "your_app:main"
├── tests/
└── README.md
```

### Configuration Files

**ci.yaml** (Project root - created from template):
```yaml
# Project-specific CI configuration
python:
  min_version: 3.11

nuitka:
  enabled: true
  build_type: package  # Auto-detected from structure
  # ... see ci/ci.yaml.template for all options
```

**.env** (Project root - NOT committed):
```bash
ARTIFACTORY_USERNAME=your-email@hypersec.io
ARTIFACTORY_PASSWORD=your-jfrog-password
# OR
ARTIFACTORY_TOKEN=your-jfrog-token
```

**.gitignore** (Must include):
```
.venv/
ci/.venv/
.env
dist/
dist-nuitka/
.keys/
*.pyc
__pycache__/
```

## What Gets Auto-Detected

HyperCI automatically detects:

1. **Build Type** (from project structure):
   - Has `src/` directory + no `[project.scripts]` → **Library** (package mode)
   - Has `[project.scripts]` in pyproject.toml → **Application** (app mode)
   - Can override in ci.yaml: `nuitka.build_type: package` or `app`

2. **Python Version** (from ci.yaml):
   - `python.min_version: 3.11` (default)
   - Bootstrap validates Python version
   - Nuitka uses correct Python

3. **Platform/Architecture** (from host):
   - Local builds: Current CPU (x64 or ARM64)
   - GitHub Actions: Matrix from ci.yaml (linux_x64, linux_arm64, macos_arm64)

4. **Nuitka Commercial vs OSS**:
   - Checks JFrog for nuitka-commercial
   - Falls back to OSS if not available
   - Auto-selects compatible protection profile

## Bootstrap Behavior

The `./ci/bootstrap` script:

1. ✅ Creates `ci.yaml` from template (if not present)
2. ✅ Loads `.env` credentials (if present)
3. ✅ Creates `ci/.venv` (CI tools environment)
4. ✅ Creates `.venv` (development environment with uv)
5. ✅ Installs CI tools (pytest, ruff, black, mypy, etc.)
6. ✅ Configures JFrog access (if credentials available)
7. ✅ Installs Nuitka Commercial (if enabled in ci.yaml)

### First-Time Bootstrap

```bash
$ ./ci/bootstrap --install

[INFO] Creating ci.yaml from template...
[OK] Created ci.yaml
[INFO] Customize ci.yaml for your project settings
[INFO] Creating ci/.venv...
[OK] ci/.venv created
[OK] CI tools installed
[OK] Bootstrap complete

# Now customize:
$ vim ci.yaml
```

### Subsequent Runs

```bash
$ ./ci/bootstrap

[OK] ci.yaml already exists
[OK] ci/.venv already exists
[OK] Bootstrap complete
```

## Directory Conventions

HyperCI follows these conventions:

### Source Code
- `src/your_package/` - Package source (library)
- `src/your_app/` - Application source (app)
- Auto-detected based on structure

### Tests
- `tests/` - All tests (unittest, pytest)
- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `tests/e2e/` - End-to-end tests
- Optional: Tests can be anywhere, configured in pyproject.toml

### Build Outputs
- `dist/` - Built wheels and sdist (standard Python build)
- `dist-nuitka/` - Standalone binaries (Nuitka app mode)
- `.keys/` - Nuitka encryption keys (gitignored)
- `build/` - Temporary build directory (gitignored)

### Temporary Files
- `.tmp/` - Project-specific temp files (if used)
- Prefer `.tmp/` over `/tmp` for project-local temp files

## Environment Variables

### Bootstrap Phase (JFrog Access)

**Username/Password:**
```bash
ARTIFACTORY_USERNAME=your-email@hypersec.io
ARTIFACTORY_PASSWORD=your-password
```

**Or Token Auth (Preferred):**
```bash
ARTIFACTORY_TOKEN=your-access-token
ARTIFACTORY_TOKEN_USER=artifactory@hypersec.io  # Optional, default shown
```

### CI Phase (Configuration Overrides)

Any `ci.yaml` setting can be overridden with environment variables:

```bash
# Override Nuitka enabled setting
HYPERLIB_CI_NUITKA_ENABLED=false ./ci/run build

# Override protection level
HYPERLIB_CI_NUITKA_PROTECTION_LEVEL=none ./ci/run build

# Override platform
HYPERLIB_CI_NUITKA_PLATFORMS_MACOS_ARM64=true ./ci/run build
```

Pattern: `HYPERLIB_CI_<PATH>` where PATH is the ci.yaml key in UPPERCASE with dots→underscores.

## Assumptions and Requirements

### Assumptions

HyperCI assumes:

1. **Git Repository**: Project is a git repository
   - Used for versioning, branch name validation
   - `.git/` must exist

2. **Python 3.9+**: System Python is at least 3.9
   - CI tools (pytest, ruff) require Python 3.9+
   - Project can require higher (configure in ci.yaml)

3. **Internet Access** (for bootstrap):
   - JFrog Artifactory (for Nuitka Commercial, hyperlib, etc.)
   - PyPI (fallback for public packages)
   - Can work offline after initial bootstrap

4. **Standard Python Package**:
   - Has `pyproject.toml` (PEP 621 metadata)
   - Has `src/` or flat layout
   - Has `tests/` directory (optional but recommended)

5. **.env File** (for JFrog access):
   - Contains ARTIFACTORY_USERNAME/PASSWORD or TOKEN
   - Required only if using private PyPI packages

### Hard Requirements

MUST have:
- ✅ Git installed (`git --version`)
- ✅ Python 3.9+ (`python3 --version`)
- ✅ `pyproject.toml` (package metadata)
- ✅ `.gitignore` including `ci/.venv/`

MUST NOT have:
- ❌ `ci/` directory before adding subtree (will conflict)
- ❌ Conflicting ci scripts (will be overwritten by subtree)

### Optional Requirements

For Nuitka builds:
- C compiler (gcc on Linux, clang on macOS, MSVC on Windows)
- Nuitka Commercial access via JFrog

For JFrog publishing:
- JFrog credentials in `.env`
- GitHub secrets configured

## Common Patterns

### Pattern 1: Library Package

```
my-library/
├── ci/ ← hyperci subtree
├── ci.yaml ← Project settings
├── .env ← JFrog credentials
├── src/
│   └── my_library/
│       ├── __init__.py
│       └── core.py
├── tests/
│   └── test_core.py
├── pyproject.toml
└── README.md
```

**ci.yaml:**
```yaml
nuitka:
  enabled: true
  build_type: package  # Compiled wheels
```

**Auto-detection**: ✅ Detected as "package" (has src/, no entry points)

### Pattern 2: CLI Application

```
my-app/
├── ci/ ← hyperci subtree
├── ci.yaml ← Project settings
├── src/
│   └── my_app/
│       ├── __main__.py
│       └── cli.py
├── pyproject.toml
│   [project.scripts]
│     my-app = "my_app.cli:main"
└── README.md
```

**ci.yaml:**
```yaml
nuitka:
  enabled: true
  build_type: app  # Standalone binary
```

**Auto-detection**: ✅ Detected as "app" (has project.scripts entry point)

### Pattern 3: Microservice/API

```
my-service/
├── ci/ ← hyperci subtree
├── ci.yaml
├── src/
│   └── my_service/
│       ├── api.py
│       ├── models.py
│       └── __main__.py
├── Dockerfile
├── k8s/
└── pyproject.toml
```

HyperCI builds the package, Docker builds the container.

## Documentation Index

- **[README.md](../README.md)** - HyperCI overview (in hyperci repo)
- **[SUBTREE-USAGE.md](SUBTREE-USAGE.md)** - Git subtree usage guide
- **[NUITKA.md](NUITKA.md)** - Nuitka compilation guide
- **ci.yaml.template** - Example configuration with all options

## Troubleshooting

### "ci.yaml not found"

**Bootstrap will create it automatically**:
```bash
./ci/bootstrap --install
# Creates ci.yaml from ci/ci.yaml.template
```

**Or create manually**:
```bash
cp ci/ci.yaml.template ci.yaml
vim ci.yaml
```

### "ci/.venv showing in git status"

**Check .gitignore**:
```bash
# Should include:
ci/.venv/
.venv/
```

**If missing**:
```bash
echo "ci/.venv/" >> .gitignore
git add .gitignore
```

### "Bootstrap fails with JFrog authentication"

**Check .env file**:
```bash
# Should have:
ARTIFACTORY_USERNAME=your-email@hypersec.io
ARTIFACTORY_PASSWORD=your-password
# OR
ARTIFACTORY_TOKEN=your-token
```

### "Nuitka build fails"

**Check ci.yaml**:
```yaml
nuitka:
  enabled: true  # Must be true
```

**Check C compiler**:
```bash
gcc --version  # Linux
clang --version  # macOS
```

**Check Nuitka installed**:
```bash
ci/.venv/bin/python -m nuitka --version
```

## Support

- **Issues**: https://github.com/hypersec-io/hyperci/issues
- **Discussions**: https://github.com/hypersec-io/hyperci/discussions
- **Source**: https://github.com/hypersec-io/hyperci
