# Hyperlib

HyperSec shared library for Python projects - Enterprise infrastructure for configuration, logging, metrics, and runtime management.

## Features

- **Application Framework**: Primary API for application lifecycle management
- **Logging**: Structured logging with Loguru and RFC 3339 timestamps
- **Configuration**: Cascading configuration with Dynaconf
- **Runtime Management**: Container paths, environment detection, and resource management
- **Prometheus Metrics**: Built-in metrics collection and export
- **Database Utilities**: Connection URL building and configuration
- **Test Harness**: Centralized test execution with logging

## Installation

### From JFrog Artifactory (Production)

```bash
# Install from HyperSec private PyPI
pip install hyperlib --extra-index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple

# With credentials from environment
export JF_USER="your-email@hypersec.io"
export JF_PASSWORD="your-jfrog-password"
pip install hyperlib --extra-index-url "https://${JF_USER}:${JF_PASSWORD}@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"
```

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/hypersec-io/hyperlib
cd hyperlib

# Bootstrap (3-phase: creates ci/.venv, installs hyperlib, runs bootstrap.d scripts)
./ci/bootstrap --install

# Or set up manually
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start

```python
# Application Framework (recommended)
from hyperlib import Application

app = Application()
app.logger.info("Application started")

# Or use components directly
from hyperlib import get_logger, get_runtime_paths, create_metrics

logger = get_logger()
logger.info("Application started")

runtime = get_runtime_paths()
logger.info(f"Config path: {runtime.config_dir}")

metrics = create_metrics(namespace="myapp")
```

## Local CI (default)

```bash
./ci/ci
```

CI is local-first. GitHub Actions are disabled by default and should be enabled only for tasks requiring hosted secrets (e.g., publishing).

## Documentation

- **STATE.md** (or ) - Project state and AI assistant instructions
- **docs/CHARS-POLICY.md** - Character restrictions (ASCII logs, limited emoji)
- **docs/CONTRIBUTING.md** - Development workflow and conventions
- **docs/DEVELOPMENT.md** - Setup, bootstrap, and build instructions
- **ci/docs/JFROG.md** - JFrog Artifactory setup and publishing
- **ci/docs/BOOTSTRAP-INTERNALS.md** - Bootstrap implementation details
- **docs/TEMPLATE-CHANGES.md** - Template change tracking
- **TODO.md** - Authoritative task list
- **CHANGELOG.md** - Version history (auto-generated)

## Requirements

- Python 3.11+
- Dependencies: `loguru`, `dynaconf`, `pyyaml`

## CI and Publishing

### CI Commands

```bash
./ci/ci [action] [flags]

Actions:
  check     - Run all CI checks (lint, test, type-check)
  build     - Build wheel and sdist locally (for testing)
  release   - Full semantic-release (version, tag, build)
  publish   - Release + push to GitHub (triggers GitHub Actions to publish to JFrog)
  clean     - Remove build artifacts
```

### Automated Release

```bash
# Full release with automatic versioning and publishing
FORCE_RELEASE=1 ./ci/ci publish
```

This will:
1. Analyze conventional commits since last release
2. Calculate next version (patch/minor/major)
3. Update VERSION, pyproject.toml, __init__.py
4. Generate/update CHANGELOG.md
5. Create git tag
6. Build wheel and sdist locally
7. Push commits and tags to GitHub
8. **GitHub Actions** automatically builds and publishes to JFrog Artifactory

### Publishing Workflow

**Publishing happens ONLY via GitHub Actions:**

1. Local: `./ci/ci publish` creates version, tag, and pushes
2. GitHub Actions: Triggered by tag push, builds and publishes to JFrog
3. Uses GitHub Secrets: `ARTIFACTORY_USERNAME` and `ARTIFACTORY_PASSWORD`

**Note:** `JF_USER`/`JF_PASSWORD` in `.env` are for bootstrap only (installing hyperlib during development), NOT for publishing.

## Development

This package is built using the HyperSec Forge template system and serves as a real-world test case for forge-python package template development.

### Testing

```bash
pytest tests/
```

## License

Licensed under HyperSec EULA. See [LICENSE](LICENSE) for details.
