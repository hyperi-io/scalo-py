# Bootstrap Analysis & Issues

## Questions Answered

### 1. Is hyperlib self-contained with NO references to other paths?

**Status**: ✅ NOW YES (after fixes)

**Issues Found & Fixed**:
- ❌ `docs/ARTIFACTORY.md` had reference to `../../../docs/GITHUB-SECRETS.md`
- ❌ `docs/TEMPLATE-CHANGES.md` had references to `modules/hypersec-forge-python/`
- ❌ `DEPLOYMENT.md` had absolute path `/projects/hypersec-forge/modules/hyperlib`
- ❌ `ci/ci-actions-python.yaml` had `extends: "../hypersec-forge-core/ci/ci-actions.yaml"`
- ❌ `ci/hyperlib/__init__.py` mentioned `modules/hypersec-forge-core/ci/hyperlib`

**All Fixed**: Changed to either:
- Self-referential paths within hyperlib
- External URLs (e.g., GitHub organization settings)
- Removed unnecessary cross-references

**Result**: Hyperlib is now fully self-contained and can be deployed independently.

---

### 2. Does forge create both ci/.venv (all project types) and .venv (python project type)?

**Current State**: ⚠️ PARTIAL

**What Bootstrap Does**:
1. Creates `ci/.venv` - ✅ YES (universal, all project types)
   - Created by `ensure_ci_venv_and_reexec()` in `hyperlib`
   - Used for ALL CI tools (nox, ruff, black, mypy, pytest, etc.)
   - Consistent across all projects

2. Creates `.venv` - ⚠️ NO (not by bootstrap)
   - Bootstrap script `20-python-dev-tools.py` exists
   - BUT: Only handles `ci/.venv` population
   - Does NOT create developer `.venv`

**Evidence from `bootstrap.d/20-python-dev-tools.py`**:
```python
def install_missing_tools(venv_ci: Path) -> None:
    """Attempt to install missing Python tools into ci/.venv."""
    # Only installs into ci/.venv
```

**Expected Behavior**:
- `ci/.venv` → CI tools (nox, ruff, black, mypy, pytest, etc.) ✅
- `.venv` → Project dependencies for development ❌ NOT CREATED

**Issue**: Developers must manually create `.venv`:
```bash
python -m venv .venv
.venv/bin/pip install -e .[dev]
```

**Should It?**: 🤔 YES - for better developer experience
- Template should create both venvs
- `.venv` for development (project deps)
- `ci/.venv` for CI/tools (isolated)

---

### 3. Shouldn't nox be pre-deployed by the [forge] ci/.venv?

**Status**: ✅ YES - IT SHOULD BE (and mostly is)

**What Actually Happens**:

**Theory** (what should happen):
```python
PYTHON_CI_TOOLS = [
    "nox>=2024.0.0",     # ← Nox IS in the list!
    "ruff>=0.1.0",
    "black>=24.0.0",
    "mypy>=1.8.0",
    "pytest>=8.0.0",
    # ... etc
]
```

**Practice** (what we found):
- Nox IS listed in `PYTHON_CI_TOOLS` ✅
- Bootstrap installs it when `--install` flag is used ✅
- BUT: Default behavior is check-only (no install) ⚠️

**The Problem**:
```bash
# This only checks (doesn't install)
./ci/bootstrap

# This installs
./ci/bootstrap --install  # ← Must use this!
```

**Why It Wasn't There**:
We ran bootstrap in check-only mode, so nox wasn't installed.

**Solution**:
Always run bootstrap with `--install` during project setup:
```bash
./ci/bootstrap --install  # First time setup
./ci/ci                    # Regular CI runs
```

Or better: CI should call `./ci/bootstrap --install` first!

---

## Fixes Applied to Hyperlib

### 1a. Local Fixes (in hyperlib)
✅ Removed all `../../../` references to parent directories
✅ Removed all `modules/` path references
✅ Changed cross-repo links to external URLs
✅ Made all paths self-referential

### 1b. Documented in TEMPLATE-CHANGES.md
✅ Already added issue #8 (noxfile)
✅ All other issues documented (1-7)

### 1c. Apply to Forge Templates
⏳ PENDING - Need to apply 8 documented issues to:
- `hypersec-forge-python` (7 issues)
- `hypersec-forge-core` (1 issue - bootstrap behavior)

---

## Recommendations

### For Bootstrap Improvement

**Issue**: Bootstrap needs two-phase setup
1. **Phase 1**: Create both venvs
   ```python
   ensure_ci_venv_and_reexec()    # ✅ Exists
   ensure_dev_venv()               # ❌ Missing - should create .venv
   ```

2. **Phase 2**: Populate venvs
   ```python
   # ci/.venv gets: nox, ruff, black, mypy, pytest, bandit, etc.
   # .venv gets: pip install -e .[dev]  ← Missing!
   ```

**Add to TEMPLATE-CHANGES.md**:

```markdown
### 9. Bootstrap doesn't create developer .venv

**Issue**: Bootstrap only creates `ci/.venv`, not `.venv` for development.

**Current State**:
- `ci/.venv` created ✅
- `.venv` must be created manually ❌

**Required Fix**:
Add to `bootstrap.d/20-python-dev-tools.py`:
```python
def ensure_dev_venv(root: Path, install: bool) -> None:
    """Create and populate developer .venv"""
    venv = root / ".venv"
    if not venv.exists():
        if install:
            logger.info("Creating developer .venv")
            subprocess.run([sys.executable, "-m", "venv", str(venv)])
            logger.info("Installing project in editable mode")
            subprocess.run([
                str(venv / "bin" / "pip"),
                "install", "-e", ".[dev]"
            ])
```

**Priority**: MEDIUM - Improves developer experience
```

### For Bootstrap Install Flag

**Issue**: Default bootstrap is check-only, tools not installed

**Solutions**:
1. **Option A**: Change default to `--install` (breaking change)
2. **Option B**: Document clearly in README
3. **Option C**: CI should always call `./ci/bootstrap --install`

**Recommended**: Option C - Make CI call bootstrap with --install

---

## Summary

✅ **Question 1**: Hyperlib is NOW self-contained (fixed)
⚠️ **Question 2**: Bootstrap creates `ci/.venv` but NOT `.venv` (needs fix)
✅ **Question 3**: Nox IS pre-deployed (when using `--install` flag)

**Next Steps**:
1. Add issue #9 to TEMPLATE-CHANGES.md about missing .venv creation
2. Update CI to call `./ci/bootstrap --install`
3. Apply all 9 issues to forge templates