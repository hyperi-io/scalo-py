# CI Bugs (ci repository issues)

**Repository:** https://github.com/hypersec-io/ci
**Purpose:** Track bugs in the ci infrastructure (not hs-lib bugs)

---

## Active Bugs

### BUG-CI-001: bootstrap doesn't create .venv for Python projects

**Status:** IDENTIFIED
**Severity:** HIGH
**Affects:** ci/scripts/bootstrap, ci/scripts/build_and_publish.sh

**Description:**
The `bootstrap` script installs git hooks but doesn't create a Python virtual environment (.venv). However, `build_and_publish.sh` expects .venv to exist and fails with "Missing .venv. Run python-setup before invoking build_and_publish."

**Current behavior:**
```bash
./ci/scripts/bootstrap        # Installs hooks only
./ci/scripts/build_and_publish.sh  # FAILS - no .venv
```

**Expected behavior:**
Bootstrap should either:
1. Create .venv and install dependencies (uv sync), OR
2. build_and_publish.sh should handle missing .venv gracefully

**Workaround for GitHub Actions:**
Add explicit Python setup step before build_and_publish:
```yaml
- name: Setup Python Environment
  run: |
    # Create venv and install dependencies
    uv venv
    source .venv/bin/activate
    uv sync --frozen

- name: Build and Publish
  run: ./ci/scripts/build_and_publish.sh
```

**Fix location:** ci/scripts/bootstrap (should run uv venv + uv sync)

---

### BUG-CI-002: build_and_publish.sh assumes twine is installed

**Status:** IDENTIFIED
**Severity:** HIGH
**Affects:** ci/scripts/build_and_publish.sh line 55

**Description:**
The script runs `twine check dist/*` but twine is not installed in the venv, causing "command not found" error (exit 127).

**Current behavior:**
```bash
./ci/scripts/build_and_publish.sh
# ...builds successfully...
# Running twine check
# ./ci/scripts/build_and_publish.sh: line 55: twine: command not found
# exit code 127
```

**Expected behavior:**
build_and_publish.sh should either:
1. Check if twine is available and install if missing, OR
2. Skip twine check if not available (uv publish validates anyway)

**Workaround for .github/workflows/ci-publish.yml:**
```yaml
- name: Setup Python Environment
  run: |
    uv venv
    source .venv/bin/activate
    uv sync --frozen
    uv pip install twine  # Workaround for BUG-CI-002
```

**Fix location:** ci/scripts/build_and_publish.sh (add twine check/install or make it optional)

---

### BUG-CI-003: Workflow template references obsolete ci structure paths

**Status:** FIXED (in hs-lib, but template needs update)
**Severity:** HIGH
**Affects:** ci/templates/ci-publish.yml (if it exists)

**Description:**
Generated workflow files reference old hs-ci paths:
- `ci/bootstrap` instead of `ci/scripts/bootstrap`
- `ci/modules/python/run.d/51-publish.py` instead of `ci/scripts/build_and_publish.sh`

**Fix needed:** Update workflow template in ci repository to use correct paths

---

## Resolved Bugs

_(None yet)_

---

**Last Updated:** 2025-11-24
