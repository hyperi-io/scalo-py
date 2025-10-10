# Hyperlib Deployment Guide

## Overview

This document describes how to deploy hyperlib to the HyperSec private PyPI repository on JFrog Artifactory.

## Prerequisites

### GitHub Secrets Required

The following organization secrets must be configured:
- `ARTIFACTORY_USERNAME` - JFrog Artifactory username
- `ARTIFACTORY_PASSWORD` - JFrog Artifactory password

These are already configured at: https://github.com/organizations/hypersec-io/settings/secrets/actions

### Repository Details

- **JFrog URL**: `https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local`
- **Install URL**: `https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple`
- **Workflow**: `.github/workflows/hyperlib-jfrog-publish.yml` (at repository root)

## Deployment Process

### Automated Publishing (Recommended)

Hyperlib is published via GitHub Actions workflow:

1. **Navigate to Actions**:
   - Go to: https://github.com/hypersec-io/hypersec-forge/actions
   - Select workflow: "Hyperlib - JFrog Publish"

2. **Trigger Manual Publish**:
   - Click "Run workflow"
   - Select branch: `main`
   - Optionally specify version tag (defaults to current)
   - Click "Run workflow"

3. **Monitor Progress**:
   - Build step: Builds wheel and tarball
   - Publish step: Uploads to JFrog Artifactory
   - Verify step: Installs from Artifactory to confirm availability

### Manual Publishing (Local)

For local testing or manual deployment:

```bash
# Ensure clean build
rm -rf dist/ build/ src/*.egg-info

# Build package
ci/.venv/bin/python -m build

# Publish to JFrog Artifactory
export TWINE_USERNAME="${ARTIFACTORY_USERNAME}"
export TWINE_PASSWORD="${ARTIFACTORY_PASSWORD}"

ci/.venv/bin/twine upload \
  --repository-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local \
  dist/*
```

## Verification

### Check Package Availability

After publishing, verify the package is accessible:

```bash
# Create test environment
python -m venv .test-install
source .test-install/bin/activate

# Install from Artifactory
pip install hyperlib \
  --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple

# Verify import
python -c "import hyperlib; print(f'Hyperlib {hyperlib.__version__} installed successfully')"

# Cleanup
deactivate
rm -rf .test-install
```

### Check Artifactory Web UI

1. Navigate to: https://hypersec.jfrog.io/
2. Log in with Artifactory credentials
3. Browse to: Artifactory → Artifacts → `hypersec-pypi-local`
4. Verify `hyperlib/` directory contains the published version

## Version Management

Hyperlib uses semantic versioning managed via git tags:

- **Current version**: `0.1.0`
- **Version sources**:
  - `VERSION` file (single source of truth)
  - `pyproject.toml`: `project.version`
  - `src/hyperlib/__init__.py`: `__version__`

All three must stay in sync (enforced by CI).

### Creating New Release

1. **Update version** (all three locations):
   ```bash
   echo "0.2.0" > VERSION
   # Edit pyproject.toml: version = "0.2.0"
   # Edit src/hyperlib/__init__.py: __version__ = "0.2.0"
   ```

2. **Commit changes**:
   ```bash
   git add VERSION pyproject.toml src/hyperlib/__init__.py
   git commit -m "chore: bump version to 0.2.0"
   ```

3. **Create git tag**:
   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0"
   git push origin main --tags
   ```

4. **Trigger publish workflow** (as described above)

## Installing Hyperlib in Projects

### Using pip

```bash
pip install hyperlib \
  --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
```

### Using requirements.txt

```text
hyperlib>=0.1.0
```

Configure pip index:
```bash
pip config set global.index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
pip config set global.extra-index-url https://pypi.org/simple
```

### Using pyproject.toml

```toml
[project]
dependencies = [
    "hyperlib>=0.1.0",
]

[[tool.poetry.source]]
name = "hypersec"
url = "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"
priority = "primary"
```

## Troubleshooting

### Authentication Errors

If you see `401 Unauthorized`:
- Verify secrets are correctly configured in GitHub
- Test credentials manually using `curl`:
  ```bash
  curl -u "${ARTIFACTORY_USERNAME}:${ARTIFACTORY_PASSWORD}" \
    https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
  ```

### Package Not Found After Publishing

Wait 1-2 minutes for Artifactory indexing, then:
- Clear pip cache: `pip cache purge`
- Try with `--no-cache-dir` flag
- Check Artifactory UI for package presence

### Build Failures

Common issues:
- Missing dependencies: Run `pip install build twine` in venv
- License warnings: These are deprecation warnings and can be ignored
- Version mismatch: Ensure VERSION, pyproject.toml, and __init__.py match

## Current Status

✅ **Ready for deployment:**
- Package builds successfully: `hyperlib-0.1.0-py3-none-any.whl` (25KB)
- Tests pass: 2 passed, 4 skipped (e2e tests disabled)
- Version sync: All three locations at `0.1.0`
- GitHub workflow: Configured and ready
- Secrets: Available in organization settings

⚠️ **Before first deployment:**
- Test workflow execution manually
- Verify package installs from Artifactory
- Update projects to consume from private PyPI

## Next Steps

1. **First deployment**: Run workflow to publish v0.1.0
2. **Verification**: Test installation in a sample project
3. **Migration planning**: Plan migration from cut-down versions to full package
4. **Documentation**: Update consuming projects with new install instructions