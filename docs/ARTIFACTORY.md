# JFrog Artifactory Configuration for Hyperlib

## Overview

Hyperlib is published to the HyperSec private PyPI repository on JFrog Artifactory. This document describes the configuration and usage.

## Repository URLs

### PyPI Repository
- **Base URL**: `https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local`
- **Pip install URL**: `https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple`

### Docker Registry
- **Registry**: `hypersec.jfrog.io`
- **Repository**: `hypersec-docker`
- **Full image path**: `hypersec.jfrog.io/hypersec-docker/{image-name}:{tag}`

## Authentication

### GitHub Actions Secrets

The following organization secrets are available:

**Primary credentials:**
- `ARTIFACTORY_USERNAME` - Standard Artifactory username
- `ARTIFACTORY_PASSWORD` - Standard Artifactory password

**Alternative token-based auth (preferred):**
- `JFROG_ACCESS_TOKEN` - JFrog access token
- `JFROG_TOKEN` - Alternative token name

**Tenant-specific (if needed):**
- `ARTIFACTORY_TENANT_USERNAME`
- `ARTIFACTORY_TENANT_PASSWORD`
- `ARTIFACTORY_TENANT_REGISTRY`

### Local Development

For local development, store credentials in environment variables:

```bash
export ARTIFACTORY_USERNAME="your-username"
export ARTIFACTORY_PASSWORD="your-password"
# Or use token
export JFROG_ACCESS_TOKEN="your-token"
```

## Publishing Hyperlib

### Via GitHub Actions (Recommended)

Hyperlib uses automated publishing via GitHub Actions workflow:

1. Navigate to: https://github.com/hypersec-io/hypersec-forge/actions
2. Select: "Hyperlib - JFrog Publish"
3. Click "Run workflow" on main branch
4. Monitor the build → publish → verify process

See [DEPLOYMENT.md](../DEPLOYMENT.md) for detailed deployment instructions.

### Manual Publishing

For local testing or manual deployment:

```bash
# Build package
rm -rf dist/ build/
ci/.venv/bin/python -m build

# Publish using twine
export TWINE_USERNAME="${ARTIFACTORY_USERNAME}"
export TWINE_PASSWORD="${ARTIFACTORY_PASSWORD}"

ci/.venv/bin/twine upload \
  --repository-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local \
  dist/*
```

### Using Poetry

```bash
# Configure repository
poetry config repositories.hypersec https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local

# Set credentials
poetry config http-basic.hypersec "${ARTIFACTORY_USERNAME}" "${ARTIFACTORY_PASSWORD}"

# Build and publish
poetry build
poetry publish --repository hypersec
```

## Installing Hyperlib

### Using pip

**Simple install:**
```bash
pip install hyperlib \
  --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
```

**With credentials in URL:**
```bash
pip install hyperlib \
  --index-url https://${ARTIFACTORY_USERNAME}:${ARTIFACTORY_PASSWORD}@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
```

**Specific version:**
```bash
pip install hyperlib==0.1.0 \
  --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
```

### Configure pip Globally

**Using pip.conf (Linux/macOS: `~/.pip/pip.conf`, Windows: `%APPDATA%\pip\pip.ini`):**

```ini
[global]
index-url = https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
extra-index-url = https://pypi.org/simple

# If authentication required in config (not recommended for security)
# index-url = https://username:password@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
```

**Using pip config command:**
```bash
pip config set global.index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
pip config set global.extra-index-url https://pypi.org/simple
```

### Using requirements.txt

```text
# requirements.txt
hyperlib>=0.1.0
```

Then install with:
```bash
pip install -r requirements.txt \
  --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
```

### Using pyproject.toml

**For setuptools/pip:**
```toml
[project]
dependencies = [
    "hyperlib>=0.1.0",
]
```

**For Poetry:**
```toml
[tool.poetry.dependencies]
hyperlib = "^0.1.0"

[[tool.poetry.source]]
name = "hypersec"
url = "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"
priority = "primary"
```

## Verification

### Verify Installation

After installing, verify hyperlib is accessible:

```python
import hyperlib
print(f"Hyperlib version: {hyperlib.__version__}")
```

### Check Package in Artifactory

**Web UI:**
1. Navigate to: https://hypersec.jfrog.io/
2. Log in with Artifactory credentials
3. Browse: Artifactory → Artifacts → `hypersec-pypi-local`
4. Verify `hyperlib/` directory contains published versions

**API Check:**
```bash
curl -u "${ARTIFACTORY_USERNAME}:${ARTIFACTORY_PASSWORD}" \
  https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple/hyperlib/
```

## Troubleshooting

### 401 Unauthorized

- Verify credentials are correct and not expired
- Check organization secrets are properly configured
- Test credentials manually:
  ```bash
  curl -u "${ARTIFACTORY_USERNAME}:${ARTIFACTORY_PASSWORD}" \
    https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
  ```

### Package Not Found

- Wait 1-2 minutes for Artifactory indexing after publishing
- Clear pip cache: `pip cache purge`
- Use `--no-cache-dir` flag
- Verify package exists in Artifactory UI

### SSL Certificate Errors

If you encounter SSL errors:
```bash
pip install hyperlib \
  --index-url https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple \
  --trusted-host hypersec.jfrog.io
```

**Note**: Only use `--trusted-host` if necessary and you trust the source.

### Slow Downloads

- Check network connectivity to JFrog
- Verify no proxy/firewall blocking
- Use `--verbose` flag for debugging:
  ```bash
  pip install hyperlib --index-url <url> --verbose
  ```

## Security Notes

1. **Never commit credentials** to repositories
2. **Use environment variables** for local credentials
3. **Use GitHub Secrets** for CI/CD credentials
4. **Prefer token-based auth** over username/password
5. **Rotate credentials** regularly according to security policy
6. **Use HTTPS only** - never use HTTP for Artifactory access

## Related Documentation

- [Hyperlib Deployment Guide](../DEPLOYMENT.md)
- [JFrog Artifactory Documentation](https://www.jfrog.com/confluence/display/JFROG/PyPI+Repositories)
- [GitHub Organization Secrets](https://github.com/organizations/hypersec-io/settings/secrets/actions)