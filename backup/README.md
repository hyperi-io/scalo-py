# Backup Files - Pre-Bootstrap Test

**Date:** 2025-10-28
**Purpose:** Backup of files before running `./ci/bootstrap --install` test

## Backed Up Files

### Root Files
- `gitignore.backup` - Original .gitignore (will be merged with HyperCI patterns)
- `gitattributes.backup` - Original .gitattributes (will be merged)

### Git Hooks
- `commit-msg.backup` - Existing commit-msg hook (will be replaced)
- `pre-commit.backup` - Existing pre-commit hook (will be replaced)

### ci-local Files
- `ci-local-pyproject.toml.backup` - CI tools dependency spec (may be updated)

### pip Configuration  
- `pip.backup/pip.conf` - JFrog authentication config

## Files NOT Backed Up (per user request)
- `.env` - User credentials (excluded from backup)

## Restore Instructions

If bootstrap test fails or produces unwanted results:

```bash
# Restore root files
cp backup/gitignore.backup .gitignore
cp backup/gitattributes.backup .gitattributes

# Restore git hooks
cp backup/commit-msg.backup .git/hooks/commit-msg
cp backup/pre-commit.backup .git/hooks/pre-commit
chmod +x .git/hooks/commit-msg .git/hooks/pre-commit

# Restore ci-local files
cp backup/ci-local-pyproject.toml.backup ci-local/pyproject.toml

# Restore pip config
cp -r backup/pip.backup .pip
```

## Files That Will Be Created/Modified

**Modified (merged):**
- `.gitignore` - CI patterns added via marker-based merge
- `.gitattributes` - Line ending rules added  via marker-based merge
- `ci-local/.env.sample` - Will be created with JFrog/build var templates

**Created (if missing):**
- `ci-local/CI-LOCAL.md` - Documentation for ci-local/ directory
- `tests/` - Test directory structure (if missing)

**Replaced:**
- `.git/hooks/commit-msg` - New HyperCI validation hook
- `.git/hooks/pre-commit` - New HyperCI pre-commit hook (if configured)
