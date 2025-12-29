# hs-pylib CI Setup Guide

Step-by-step guide for setting up HyperSec CI on this project. Use this as a reference for other projects.

## Prerequisites

- Git repository with GitHub remote
- GitHub App configured with `GH_APP_ID` and `GH_APP_PRIVATE_KEY` secrets
- JFrog Artifactory credentials: `ARTIFACTORY_CI_USERNAME`, `ARTIFACTORY_CI_TOKEN`
- JFrog variables: `ARTIFACTORY_PYPI_URL`, `ARTIFACTORY_PYPI_PUBLISH_URL`

## Quick Start

### 1. Add CI Submodule

```bash
git submodule add https://github.com/hypersec-io/ci.git ci
git submodule update --init ci
```

### 2. Attach CI (Generates Workflows)

```bash
./ci/attach.sh --force --python
```

This creates:
- `.github/workflows/ci.yml` - Quality + Test pipeline
- `.github/workflows/publish.yml` - Build + Publish to JFrog
- `.github/workflows/semantic-release.yml` - Version tagging
- `.hypersec-ci.yaml` - Project configuration
- `.releaserc.json` - Semantic release config

### 3. Configure `.hypersec-ci.yaml`

For a Python package (library):

```yaml
build:
  type: package    # REQUIRED: 'app' for CLI, 'package' for library
```

That's all that's needed for defaults. The CI will:
- Run quality checks (ruff, gitleaks)
- Run tests (pytest)
- Build native wheel on release
- Publish to JFrog PyPI

### 4. Add Gitleaks Allowlist (If Needed)

If gitleaks finds false positives (test fixtures, historical commits), create `.gitleaks.toml`:

```toml
[extend]
useDefault = true

[allowlist]
description = "Project false positives"

# Historical commits with rotated credentials
commits = [
    "abc123...",  # Description
]

# Test files with fake secrets
paths = [
    '''tests/.*test_anonymizer\.py''',
    '''tests/.*test_logger_filters\.py''',
]

# Fake secrets in test fixtures
regexes = [
    '''sk-proj-abc123''',
    '''sk_live_51Hqx2''',
]
```

### 5. Commit and Push

```bash
git add .
git commit -m "fix: add HyperSec CI v1.31.0"
git push origin main
```

## Updating CI

### Refresh Submodule

```bash
git -C ci fetch origin main
git -C ci reset --hard origin/main
```

### Regenerate Workflows

```bash
./ci/attach.sh --force-workflows --python
```

This updates workflows without touching `.hypersec-ci.yaml`.

### Full Refresh

```bash
git -C ci reset --hard origin/main
./ci/attach.sh --force --python
git add .
git commit -m "chore: update CI to hs-ci vX.Y.Z"
```

## Monitoring Workflow Runs

```bash
# List recent runs
gh run list --repo hypersec-io/hs-pylib --limit 5

# Watch a specific run
gh run watch <run-id> --repo hypersec-io/hs-pylib --exit-status

# View failed logs
gh run view <run-id> --repo hypersec-io/hs-pylib --log-failed
```

## Verifying JFrog Publish

```bash
# Search for package
jf rt search "hypersec-pypi/hs-pylib/<version>/*"

# Download and test
jf rt download "hypersec-pypi-local/hs-pylib/<version>/hs_pylib-<version>-py3-none-any.whl" . --flat
python3 -m venv .venv
.venv/bin/pip install hs_pylib-<version>-py3-none-any.whl
.venv/bin/python -c "import hs_pylib; print(hs_pylib.__version__)"
```

## Troubleshooting

### Gitleaks Failures

1. Check the log for the specific finding:
   ```bash
   gh run view <run-id> --repo hypersec-io/hs-pylib --log-failed | grep -A 10 "Finding:"
   ```

2. If it's a false positive (test data, rotated credential), add to `.gitleaks.toml`

3. If it's a real secret, rotate it immediately and use `git filter-branch` or BFG to remove

### CI Workflow Failures

1. Check the quality action output for linting/formatting errors
2. Check test output for pytest failures
3. Ensure all dependencies are in `pyproject.toml`

### Publish Failures

1. Verify JFrog credentials are set in GitHub secrets
2. Check `ARTIFACTORY_PYPI_PUBLISH_URL` org variable is correct
3. Ensure version doesn't already exist in JFrog

## Architecture

```
ci/                      # Submodule
├── actions/
│   └── jobs/           # Composite actions (quality, test)
├── scripts/
│   └── core/           # Shell scripts (gitleaks.sh)
├── templates/
│   └── workflows/      # Workflow templates
└── attach.sh           # Setup script

.github/workflows/
├── ci.yml              # Quality + Test (thin, uses job actions)
├── publish.yml         # Build + Publish (verbose, has Nuitka matrix)
└── semantic-release.yml

.hypersec-ci.yaml       # Project config (minimal)
.gitleaks.toml          # Secret scanning allowlist
.releaserc.json         # Semantic release config
```

## Version History

| Date | CI Version | Changes |
|------|------------|---------|
| 2025-11-28 | v1.31.0 | Initial setup with thin workflows, gitleaks |
