# HyperCI Documentation

Central CI/CD infrastructure for all HyperSec Python projects.

## System Dependencies

### Required (HARD REQUIREMENTS - Bootstrap FAILS without these)

**All Projects:**
- ✅ **Git 2.0+**: Version control (`git --version`)
  - Must have `.git/` directory (initialized repository)
  - Bootstrap validates and FAILS HARD if missing

- ✅ **Python 3.9+**: For CI tools (`python3 --version`)
  - Minimum: 3.9 (for CI tools: pytest, ruff, mypy)
  - Projects can require higher (e.g., 3.11+ in ci.yaml)
  - Bootstrap validates and FAILS HARD if version too low

- ✅ **.gitignore**: Must exist and include:
  ```
  ci/.venv/    # CI environment (required)
  .venv/       # Dev environment (required)
  __pycache__/ # Python cache (recommended)
  dist/        # Build outputs (recommended)
  ```
  - Bootstrap validates and FAILS HARD if missing
  - Run `./ci/bootstrap --install` to auto-create

**Python Projects:**
- ✅ **pyproject.toml**: PEP 621 metadata (required)
  - Bootstrap FAILS HARD if missing
  - Must contain `[project]` section with name, version, dependencies

- ✅ **Package Structure**: One of:
  - `src/package_name/__init__.py` (src-layout, recommended)
  - `package_name/__init__.py` (flat-layout)
  - Bootstrap validates and WARNS if cannot detect

### Optional (Enables Additional Features)

**For JFrog Private Packages:**
- ⚠️  **.env file** with credentials:
  ```bash
  ARTIFACTORY_USERNAME=your-email@hypersec.io
  ARTIFACTORY_PASSWORD=your-password
  # OR
  ARTIFACTORY_TOKEN=your-access-token
  ```
  - Required only for accessing private PyPI repository
  - Without this: Can only use public PyPI packages

**For Nuitka Compilation:**
- ⚠️  **C Compiler**:
  - Linux: `gcc` or `clang` (`gcc --version`)
  - macOS: Xcode Command Line Tools (`clang --version`)
  - Windows: MSVC or MinGW (`cl.exe` or `gcc.exe`)
  - Bootstrap checks and provides installation hints if missing

- ⚠️  **setup.py**: For Nuitka bdist_nuitka (compiled wheels)
  - Required only if building compiled wheels (package mode)
  - Not needed for standalone binaries (app mode)

- ⚠️  **Nuitka Commercial**: Via JFrog Artifactory
  - Requires ARTIFACTORY_* credentials in .env
  - Bootstrap auto-installs if credentials available
  - Falls back to OSS Nuitka if not available

**For Testing:**
- ⚠️  **tests/ directory**: Recommended but not required
  - Bootstrap warns if missing
  - Can auto-create with `./ci/bootstrap --install`

### Network Access

**During Bootstrap (one-time):**
- ✅ **JFrog Artifactory**: For private packages (if using)
  - hypersec.jfrog.io (HTTPS, port 443)
  - Requires: ARTIFACTORY_* credentials in .env

- ✅ **PyPI**: For public packages
  - pypi.org (HTTPS, port 443)
  - Fallback if JFrog unavailable

**After Bootstrap (offline capable):**
- ✅ Can work offline (all tools in ci/.venv)
- ✅ No network required for builds, tests, lint
- ⚠️  Network needed only for publishing to JFrog

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

## Common Patterns (Based on Hyperlib Application Types)

Hyperlib provides 4 application types via `Application` factory methods. HyperCI auto-detects and builds appropriately:

### Pattern 1: Package/Library

**Use Case**: Shared library imported by other projects (like hyperlib itself)

```
my-library/
├── ci/ ← hyperci subtree
├── ci.yaml
├── src/
│   └── my_library/
│       ├── __init__.py
│       └── core.py
├── tests/
│   └── test_core.py
├── pyproject.toml  # No [project.scripts]
└── README.md
```

**ci.yaml:**
```yaml
nuitka:
  enabled: true
  build_type: package  # Compiled wheels (.whl with .so)
```

**Auto-detection**: ✅ Detected as "package" (has src/, no entry points)

**Usage in code**: Not an application, just imported:
```python
from my_library import core
```

### Pattern 2: API Service

**Use Case**: REST API, GraphQL API, web service (using hyperlib Application.api)

```
my-api/
├── ci/ ← hyperci subtree
├── ci.yaml
├── src/
│   └── my_api/
│       ├── __main__.py
│       ├── api.py         # Uses Application.api()
│       ├── routes/
│       └── models/
├── Dockerfile
├── k8s/
├── pyproject.toml
│   [project.scripts]
│     my-api = "my_api.__main__:main"
└── README.md
```

**ci.yaml:**
```yaml
nuitka:
  enabled: true
  build_type: app  # Standalone binary for containers
```

**Auto-detection**: ✅ Detected as "app" (has entry point)

**Usage in code**:
```python
from hyperlib import Application

app = Application.api(
    name="my-api",
    port=8000,
    metrics_port=9090
)
app.run()
```

### Pattern 3: CLI Tool

**Use Case**: Command-line utility (using hyperlib Application.cli)

```
my-tool/
├── ci/ ← hyperci subtree
├── ci.yaml
├── src/
│   └── my_tool/
│       ├── __main__.py
│       ├── cli.py         # Uses Application.cli()
│       └── commands/
├── tests/
├── pyproject.toml
│   [project.scripts]
│     my-tool = "my_tool.__main__:main"
└── README.md
```

**ci.yaml:**
```yaml
nuitka:
  enabled: true
  build_type: app  # Standalone binary (single executable)
```

**Auto-detection**: ✅ Detected as "app" (has entry point)

**Usage in code**:
```python
from hyperlib import Application

app = Application.cli(name="my-tool")

@app.command()
def process(input_file: str):
    """Process input file."""
    print(f"Processing {input_file}")

app.run()
```

### Pattern 4: Daemon/Worker

**Use Case**: Background worker, queue processor, scheduler (using hyperlib Application.daemon)

```
my-worker/
├── ci/ ← hyperci subtree
├── ci.yaml
├── src/
│   └── my_worker/
│       ├── __main__.py
│       ├── daemon.py      # Uses Application.daemon()
│       ├── tasks/
│       └── processors/
├── pyproject.toml
│   [project.scripts]
│     my-worker = "my_worker.__main__:main"
└── README.md
```

**ci.yaml:**
```yaml
nuitka:
  enabled: true
  build_type: app  # Standalone binary for deployment
```

**Auto-detection**: ✅ Detected as "app" (has entry point)

**Usage in code**:
```python
from hyperlib import Application

app = Application.daemon(
    name="my-worker",
    check_interval=60  # Health check every 60s
)

@app.task(schedule="*/5 * * * *")
def process_queue():
    """Process queue every 5 minutes."""
    print("Processing queue...")

app.run()
```

## Auto-Detection Logic

HyperCI auto-detects from project structure:

| Pattern | Detection | Nuitka Build Type |
|---------|-----------|-------------------|
| Package/Library | No `[project.scripts]`, has `src/` | `package` (compiled wheels) |
| API Service | Has `[project.scripts]` entry point | `app` (standalone binary) |
| CLI Tool | Has `[project.scripts]` entry point | `app` (standalone binary) |
| Daemon/Worker | Has `[project.scripts]` entry point | `app` (standalone binary) |

**Note**: API/CLI/Daemon all detect as "app" mode. The difference is in your Python code (which `Application.*` factory you use), not in CI configuration.

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
