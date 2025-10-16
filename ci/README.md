# HyperCI - HyperSec CI/CD Infrastructure

Central repository for CI/CD scripts used by all HyperSec Python projects.

## Overview

HyperCI provides a standardized, self-contained CI/CD system based on:
- **Bootstrap** - Automated environment setup
- **Configuration** - YAML-based project settings (`ci/ci.yaml`)
- **Scripts** - Python-based CI actions (`ci/python/ci.d/*.py`)
- **Isolation** - Dedicated `ci/.venv` environment

## Architecture

```
hyperci/ (this repo)
  └── ci/
      ├── bootstrap              # Environment setup entry point
      ├── run                    # CI action runner (./ci/run check, build, etc.)
      ├── ci.yaml.template       # Example configuration (copy to ci/ci.yaml)
      ├── pyproject.toml         # CI tools dependencies
      ├── python/
      │   ├── bootstrap.py       # Bootstrap orchestrator
      │   ├── bootstrap.d/       # Bootstrap phase scripts
      │   ├── ci.d/              # CI action scripts
      │   │   ├── 20-python-test.py
      │   ├── 85-build-nuitka.py
      │   │   └── 90-semantic-release.py
      │   └── ci_lib.py          # Shared utilities
      └── common/
          ├── bootstrap.d/       # Common bootstrap scripts
          └── ci.d/              # Common CI scripts
```

## Usage

### Adding to Your Project (Git Subtree)

```bash
# Initial setup
cd your-project
git subtree add --prefix ci https://github.com/hypersec-io/hyperci.git main --squash

# Copy and customize configuration
cp ci/ci.yaml.template ci/ci.yaml
# Edit ci/ci.yaml with project-specific settings

# Add to .gitattributes to prevent overwrite
echo "ci/ci.yaml merge=ours" >> .gitattributes
```

### Updating to Latest

```bash
# Pull latest ci/ updates from hyperci
git subtree pull --prefix ci https://github.com/hypersec-io/hyperci.git main --squash

# Your ci/ci.yaml stays unchanged (merge=ours strategy)
```

### Contributing Back

```bash
# If you improve a script in your project
git subtree push --prefix ci https://github.com/hypersec-io/hyperci.git main
```

## Local Usage

```bash
# Setup environment
./ci/bootstrap --install

# Run CI checks
ci/.venv/bin/python ci/python/ci.d/20-python-test.py check

# Build package
ci/.venv/bin/python ci/python/ci.d/80-build.py build

# Build with Nuitka
ci/.venv/bin/python ci/python/ci.d/85-build-nuitka.py build
```

## GitHub Actions Integration

Projects using HyperCI can use minimal workflows:

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/bootstrap --install
      - run: ci/.venv/bin/python ci/python/ci.d/20-python-test.py check
```

## Configuration

Each project has its own `ci/ci.yaml` with settings:
- Python version requirements
- Nuitka build configuration
- Platform matrix (x64, ARM64, macOS)
- Third-party runners (BuildJet, Cirrus)
- Protection levels
- Trigger conditions

See `ci/ci.yaml.template` for full example.

## Features

- ✅ Self-contained (dedicated `ci/.venv`, no pollution)
- ✅ Platform-agnostic (works locally, GitHub Actions, GitLab, etc.)
- ✅ Configuration-driven (`ci/ci.yaml`)
- ✅ Nuitka support (compiled wheels and standalone binaries)
- ✅ Multi-architecture builds (x64, ARM64, macOS)
- ✅ Cost optimization (BuildJet, Cirrus runners)
- ✅ JFrog Artifactory integration
- ✅ Semantic versioning
- ✅ Security scanning

## Projects Using HyperCI

- [hyperlib](https://github.com/hypersec-io/hyperlib) - Shared Python library
- (More projects as they migrate...)

## License

MIT License - See LICENSE file
