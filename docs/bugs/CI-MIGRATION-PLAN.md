# CI Migration Plan for feat/DFE-523-modular-multi-language-ci

**Purpose:** Document required changes for the ci repository development branch
**Target Branch:** feat/DFE-523-modular-multi-language-ci
**Bugs to Fix:** See [BUGS-CI.md](BUGS-CI.md)

---

## Overview

The new ci repository structure (hyperi-io/ci) has several issues that need to be fixed before it can fully replace the old hs-ci infrastructure. These bugs were discovered during hyperi-pylib v2.10.1 publish testing.

---

## Required Fixes for feat/DFE-523-modular-multi-language-ci Branch

### 1. Fix BUG-CI-001: bootstrap should create Python venv

**File:** `ci/scripts/bootstrap`

**Current behavior:**

```bash
#!/usr/bin/env bash
# Only installs git hooks
ln -sf ../../ci/hooks/commit-msg .git/hooks/commit-msg
ln -sf ../../ci/hooks/pre-commit .git/hooks/pre-commit
```

**Required behavior:**

```bash
#!/usr/bin/env bash
# Install git hooks
ln -sf ../../ci/hooks/commit-msg .git/hooks/commit-msg
ln -sf ../../ci/hooks/pre-commit .git/hooks/pre-commit

# Detect project language
if [ -f "pyproject.toml" ]; then
  # Python project - create venv and install dependencies
  echo "Setting up Python environment..."
  uv venv
  source .venv/bin/activate
  uv sync --frozen
  echo "Python environment ready"
fi
```

**Why:** build_and_publish.sh expects .venv to exist, but bootstrap doesn't create it

---

### 2. Fix BUG-CI-002: build_and_publish.sh missing twine dependency

**File:** `ci/scripts/build_and_publish.sh` line 55

**Current code:**

```bash
echo "Running twine check"
twine check dist/*
```

**Option A - Graceful fallback (recommended):**

```bash
echo "Running twine check"
if command -v twine &> /dev/null; then
  twine check dist/*
else
  echo "⚠️  twine not found, skipping check (uv publish validates anyway)"
fi
```

**Option B - Install if missing:**

```bash
echo "Running twine check"
if ! command -v twine &> /dev/null; then
  echo "Installing twine..."
  uv pip install twine
fi
twine check dist/*
```

**Why:** twine is not guaranteed to be in venv, causing "command not found" errors

---

### 3. Fix BUG-CI-003: Update workflow template

**File:** `ci/templates/ci-publish.yml` (if exists) OR create new template

**Required changes:**

1. Change `ci/bootstrap` → `ci/scripts/bootstrap`
2. Change `ci/modules/python/run.d/51-publish.py` → `ci/scripts/build_and_publish.sh`
3. Add Python environment setup step if BUG-CI-001 is not fixed:

```yaml
- name: Bootstrap CI
  run: ./ci/scripts/bootstrap

# Only needed if bootstrap doesn't create venv (BUG-CI-001)
- name: Setup Python Environment
  run: |
    uv venv
    source .venv/bin/activate
    uv sync --frozen
    uv pip install twine  # Only needed if BUG-CI-002 not fixed

- name: Build and Publish
  env:
    ARTIFACTORY_USERNAME: ${{ secrets.ARTIFACTORY_USERNAME }}
    ARTIFACTORY_PASSWORD: ${{ secrets.ARTIFACTORY_PASSWORD }}
  run: |
    if [ "${{ matrix.build_type }}" = "standard" ]; then
      ./ci/scripts/build_and_publish.sh
    elif [ "${{ matrix.build_type }}" = "nuitka" ]; then
      ./ci/scripts/build_nuitka.sh
      ./ci/scripts/publish_binary.sh
    fi
```

**Why:** Old hs-ci paths no longer exist in new ci structure

---

## Testing Checklist

After implementing fixes on feat/DFE-523-modular-multi-language-ci:

- [ ] Test bootstrap creates venv for Python projects
- [ ] Test bootstrap installs dependencies (uv sync)
- [ ] Test build_and_publish.sh works without manual venv setup
- [ ] Test build_and_publish.sh handles missing twine gracefully
- [ ] Test ci-publish.yml workflow end-to-end
- [ ] Test with hyperi-pylib (package build type)
- [ ] Test with test-cli-build (app build type, Nuitka)
- [ ] Verify published packages in JFrog PyPI

---

## Migration Path for Projects

Once fixes are merged to feat/DFE-523-modular-multi-language-ci:

### For hyperi-pylib

```bash
# Update ci submodule to dev branch
cd /projects/hyperi-pylib
git -C ci checkout feat/DFE-523-modular-multi-language-ci
git -C ci pull origin feat/DFE-523-modular-multi-language-ci
git add ci
git commit -m "fix: update ci submodule to dev branch (DFE-523 fixes)"

# Remove workarounds from workflow (if all bugs fixed)
# Edit .github/workflows/ci-publish.yml
# - Remove manual venv setup (if BUG-CI-001 fixed)
# - Remove twine install (if BUG-CI-002 fixed)

# Test
./ci/scripts/bootstrap
# Should create .venv and install dependencies automatically

./ci/scripts/build_and_publish.sh
# Should work without errors
```

---

## Current Workarounds (hyperi-pylib only)

Until fixes are merged, hyperi-pylib uses these workarounds in `.github/workflows/ci-publish.yml`:

1. **Manual venv creation:**

   ```yaml
   - name: Setup Python Environment
     run: |
       uv venv
       source .venv/bin/activate
       uv sync --frozen
       uv pip install twine
   ```

2. **Updated script paths:**
   - `ci/scripts/bootstrap` (not `ci/bootstrap`)
   - `ci/scripts/build_and_publish.sh` (not `ci/modules/python/run.d/51-publish.py`)

These workarounds should be removed once the ci development branch has the fixes.

---

## Impact Assessment

**Projects affected:** ALL projects using ci submodule (hyperi-io/ci)

**Breaking changes:** None if fixes are backward compatible

**Migration effort:**

- Low (if all bugs fixed in ci) - just update submodule
- Medium (if bugs not fixed) - each project needs workflow workarounds

---

**Created:** 2025-11-24
**Status:** Waiting for feat/DFE-523-modular-multi-language-ci branch to be created
