# HyperCI Subtree Usage Guide

## Overview

HyperCI is HyperSec's centralized CI/CD infrastructure for all Python projects. Instead of copying CI scripts to every project, we use **git subtree** to embed the shared infrastructure while keeping project-specific configuration separate.

## Architecture

```
hypersec-io/hyperci (Central Repository)
  ├── bootstrap              # Entry point for environment setup
  ├── run                    # CI action runner
  ├── ci.yaml.template       # Example configuration
  ├── python/
  │   ├── bootstrap.d/*.py   # Bootstrap phase scripts
  │   ├── ci.d/*.py          # CI action scripts (test, build, release)
  │   └── ci_lib.py          # Shared utilities
  └── common/
      ├── bootstrap.d/*.py   # Common bootstrap scripts
      └── ci.d/*.py          # Common CI checks

Each Project (e.g., hyperlib)
  ├── ci/ ← Git subtree from hypersec-io/hyperci
  │   ├── bootstrap
  │   ├── python/ci.d/*.py   # All scripts from central repo
  │   └── ... (all from hyperci)
  ├── ci/ci.yaml ← PROJECT-SPECIFIC (protected from subtree updates)
  ├── .gitattributes → ci/ci.yaml merge=ours (protection)
  └── src/...
```

## Adding HyperCI to a New Project

### Step 1: Add HyperCI as Git Subtree

```bash
cd your-project

# Add hyperci as a subtree under ci/
git subtree add --prefix ci https://github.com/hypersec-io/hyperci.git main --squash

# This creates:
#   your-project/ci/bootstrap
#   your-project/ci/python/ci.d/*.py
#   etc.
```

### Step 2: Create Project-Specific Configuration

```bash
# Copy the template
cp ci/ci.yaml.template ci/ci.yaml

# Customize for your project
vim ci/ci.yaml
# Edit: python.min_version, nuitka settings, platforms, etc.
```

### Step 3: Protect ci/ci.yaml from Subtree Updates

```bash
# Add to .gitattributes
echo "ci/ci.yaml merge=ours" >> .gitattributes

# This ensures 'git subtree pull' won't overwrite your config
```

### Step 4: Commit Everything

```bash
git add ci/ci.yaml .gitattributes
git commit -m "feat: add HyperCI infrastructure via git subtree

Added HyperCI (hypersec-io/hyperci) as git subtree under ci/.
Created project-specific ci/ci.yaml configuration.
Protected ci/ci.yaml from subtree updates via .gitattributes.
"
```

### Step 5: Bootstrap and Test

```bash
# Setup environment
./ci/bootstrap --install

# Verify it works
ci/.venv/bin/python ci/python/ci.d/20-python-test.py check
```

## Adding HyperCI to an Existing Project

If your project already has a `ci/` directory:

### Option A: Replace Existing ci/

```bash
# 1. Backup your current ci/ci.yaml
cp ci/ci.yaml .tmp/ci.yaml.backup

# 2. Remove existing ci/
git rm -r ci
git commit -m "refactor: remove ci/ (will be replaced with hyperci subtree)"
rm -rf ci

# 3. Add hyperci subtree
git subtree add --prefix ci https://github.com/hypersec-io/hyperci.git main --squash

# 4. Restore your ci/ci.yaml
cp .tmp/ci.yaml.backup ci/ci.yaml

# 5. Protect from future updates
echo "ci/ci.yaml merge=ours" >> .gitattributes

# 6. Commit
git add ci/ci.yaml .gitattributes
git commit -m "feat: migrate to hyperci subtree with project-specific config"
```

### Option B: Migrate Gradually

```bash
# 1. Add hyperci to a different prefix temporarily
git subtree add --prefix ci-new https://github.com/hypersec-io/hyperci.git main --squash

# 2. Compare ci-new/ with your current ci/
diff -r ci/ ci-new/

# 3. Merge any project-specific scripts into hyperci (contribute back)
# 4. Then replace ci/ with ci-new/
mv ci ci-old
mv ci-new ci

# 5. Restore ci/ci.yaml
cp ci-old/ci.yaml ci/ci.yaml
```

## Updating to Latest HyperCI

When improvements are made to hyperci, update all projects:

```bash
# Pull latest updates from hyperci
git subtree pull --prefix ci https://github.com/hypersec-io/hyperci.git main --squash

# Your ci/ci.yaml is protected (merge=ours in .gitattributes)
# All scripts update automatically
# Review changes and test

# Commit the update
git commit -m "chore: update hyperci subtree to latest"
```

## Contributing Improvements Back

If you improve a script in your project:

```bash
# Push your changes back to hyperci
git subtree push --prefix ci https://github.com/hypersec-io/hyperci.git your-feature-branch

# Then create a PR in hyperci repo
# Once merged, all projects can pull the improvement
```

## Local Development

With hyperci subtree:

```bash
# Setup
./ci/bootstrap --install

# Run tests
ci/.venv/bin/python ci/python/ci.d/20-python-test.py check

# Build package
ci/.venv/bin/python ci/python/ci.d/80-build.py build

# Build with Nuitka (if enabled in ci/ci.yaml)
ci/.venv/bin/python ci/python/ci.d/85-build-nuitka.py build

# Or use the runner
./ci/run check      # Run all CI checks
./ci/run build      # Build package
./ci/run test       # Run tests
```

## GitHub Actions Integration

With hyperci subtree, GitHub Actions workflows become SIMPLE:

### Minimal Workflow Example

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for subtree

      - name: Bootstrap
        run: ./ci/bootstrap --install
        env:
          ARTIFACTORY_USERNAME: ${{ secrets.ARTIFACTORY_USERNAME }}
          ARTIFACTORY_PASSWORD: ${{ secrets.ARTIFACTORY_PASSWORD }}

      - name: Run Tests
        run: ci/.venv/bin/python ci/python/ci.d/20-python-test.py check
```

### Nuitka Build Workflow Example

```yaml
# .github/workflows/nuitka.yml
name: Nuitka Build

on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Bootstrap
        run: ./ci/bootstrap --install
        env:
          ARTIFACTORY_USERNAME: ${{ secrets.ARTIFACTORY_USERNAME }}
          ARTIFACTORY_PASSWORD: ${{ secrets.ARTIFACTORY_PASSWORD }}

      - name: Build Compiled Wheel
        run: ci/.venv/bin/python ci/python/ci.d/85-build-nuitka.py build

      - uses: actions/upload-artifact@v4
        with:
          name: wheels
          path: dist/*.whl
```

## Configuration

Each project has its own `ci/ci.yaml` with:

```yaml
# Python settings
python:
  min_version: 3.11

# Nuitka settings (if using compiled builds)
nuitka:
  enabled: true
  build_type: package  # or 'app'
  protection_level: recommended
  platforms:
    linux_x64: true
    linux_arm64: true
    macos_arm64: false  # Expensive!
  buildjet:
    enabled: true  # Use BuildJet for Linux (50% cheaper)
  cirrus:
    enabled: true  # Use Cirrus for macOS (95% cheaper)
```

See `ci/ci.yaml.template` for full options.

## Best Practices

### 1. Never Edit ci/ Scripts Directly

```bash
# ❌ DON'T: Edit ci/python/ci.d/85-build-nuitka.py in your project
# ✅ DO: Contribute to hyperci repo, then subtree pull

# If you need to test a change:
# 1. Edit in your project
# 2. Test it works
# 3. Use 'git subtree push' to contribute back
# 4. Get it merged in hyperci
# 5. Then 'git subtree pull' to get the official version
```

### 2. Keep ci/ci.yaml Project-Specific

```bash
# ✅ DO: Customize ci/ci.yaml for each project
# ✅ DO: Commit ci/ci.yaml with your project
# ✅ DO: Add 'ci/ci.yaml merge=ours' to .gitattributes
```

### 3. Update Regularly

```bash
# Monthly or when improvements are made
git subtree pull --prefix ci https://github.com/hypersec-io/hyperci.git main --squash
```

### 4. Test After Updates

```bash
# After subtree pull, always test:
./ci/bootstrap --install
ci/.venv/bin/python ci/python/ci.d/20-python-test.py check
```

## Troubleshooting

### Subtree Pull Overwrites ci/ci.yaml

**Solution**: Check .gitattributes has:
```
ci/ci.yaml merge=ours
```

If missing, add it and retry:
```bash
echo "ci/ci.yaml merge=ours" >> .gitattributes
git add .gitattributes
git commit -m "fix: protect ci/ci.yaml from subtree updates"
```

### Bootstrap Fails After Subtree Update

**Cause**: Incompatible changes in hyperci
**Solution**: Check hyperci changelog, update your ci/ci.yaml if needed

### Want to Contribute a Fix

```bash
# 1. Make your changes in your project's ci/
# 2. Test thoroughly
# 3. Push to hyperci (creates a branch)
git subtree push --prefix ci https://github.com/hypersec-io/hyperci.git fix/your-bug

# 4. Create PR in hyperci repo
gh pr create --repo hypersec-io/hyperci

# 5. After merge, pull it back
git subtree pull --prefix ci https://github.com/hypersec-io/hyperci.git main --squash
```

## Migration Checklist

For existing forge-python projects:

- [ ] Backup current `ci/ci.yaml`
- [ ] Remove existing `ci/` directory
- [ ] Add hyperci subtree: `git subtree add --prefix ci ...`
- [ ] Restore `ci/ci.yaml` from backup
- [ ] Add `ci/ci.yaml merge=ours` to `.gitattributes`
- [ ] Test: `./ci/bootstrap --install`
- [ ] Test: Run CI checks
- [ ] Update `.github/workflows/` to use subtree ci/ scripts
- [ ] Commit and push
- [ ] Test GitHub Actions workflows

## Related Documentation

- [ci/README.md](../README.md) - HyperCI overview
- [ci/docs/NUITKA.md](NUITKA.md) - Nuitka usage guide
- [](/) - Hyperlib project state (example project using hyperci)

## Support

Questions or issues:
- HyperCI repo: https://github.com/hypersec-io/hyperci
- Issues: https://github.com/hypersec-io/hyperci/issues
- Discussions: https://github.com/hypersec-io/hyperci/discussions
