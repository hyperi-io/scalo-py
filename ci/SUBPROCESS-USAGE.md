# Subprocess Usage in CI Infrastructure

This document catalogs all subprocess usage in the CI infrastructure and explains the rationale for each.

## Philosophy

**Use native Python where it provides value, use subprocess for standard tools.**

- ✅ **Native Python**: build, twine, requests, semantic-release
- ✅ **Subprocess**: git (standard tool), bash (bootstrap scripts)
- ❌ **Avoid**: Wrapper libraries that just call subprocess internally (GitPython, PyGithub)

## Subprocess Calls Inventory

### Git Operations (via ci_lib.py)

**Rationale**: git is a standard tool, available everywhere, well-tested

```python
# ci_lib.py consolidated helpers
get_current_branch() → git rev-parse --abbrev-ref HEAD
get_git_root() → git rev-parse --show-toplevel
get_latest_tag() → git describe --tags --abbrev=0
```

**Used in**:
- `ci/ci.d/90-semantic-release.py` - Get current branch for release checks
- `ci/ci.d/10-branch-name.py` - Validate branch naming convention
- Various CI scripts via ci_lib helpers

**Why not GitPython?**
- GitPython wraps git CLI via subprocess internally
- Adds dependency without real benefit
- Direct subprocess is more transparent
- ci_lib.py helpers already consolidate the logic

### Build and Publishing (Pure Python ✅)

**Already using Python modules directly**:

```python
# 80-build.py
python -m build        # Pure Python build
python -m twine        # Pure Python JFrog upload
```

No subprocess wrapping needed - these are true Python libraries.

### Bootstrap Scripts (Bash)

**Checked in bootstrap.d/**:
- `00-check-git.sh` - System dependency check
- `10-check-python.sh` - Python version validation
- `11-check-uv.sh` - UV package manager check

**Rationale**:
- Simple checks better expressed in bash
- System-level validation before Python venv exists
- Standard idioms (command -v, etc.)

### Python Semantic Release

**Using Python module directly**:

```python
# 90-semantic-release.py
python -m semantic_release version --commit --tag --changelog
```

✅ Pure Python library, no Node.js dependency
✅ Configuration in pyproject.toml
✅ Replaces previous Node.js semantic-release

## Summary

| Tool | Method | Rationale |
|------|--------|-----------|
| git | subprocess | Standard tool, no benefit from wrapper |
| build | Python module | Native library |
| twine | Python module | Native library |
| semantic-release | Python module | Native library (replaced Node.js) |
| bash scripts | subprocess | Bootstrap validation before Python available |

## What We Avoid

- ❌ **GitPython** - Wraps git CLI anyway
- ❌ **PyGithub** - Not needed (not using GitHub API in CI)
- ❌ **JFrog CLI** - twine handles it natively

## Conclusion

Current approach balances:
- **Simplicity**: Fewer dependencies
- **Transparency**: Direct tool invocation
- **Pythonic**: Use Python where it makes sense
- **Practical**: Use standard tools (git) via subprocess

All git operations are consolidated into ci_lib.py helpers for consistency and maintainability.
