<!-- HYPERCI_STATE_MD: core/standards/GIT-WORKFLOW.md -->
# Git Workflow Standards (HyperCI)

**Auto-copied to `docs/standards/` by CI_MERGE**

## Branch Naming Convention

**Format:** `<type>/<issue-ref>/<short-description>`

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `chore` - Maintenance (deps, config)
- `docs` - Documentation
- `test` - Tests only
- `refactor` - Code refactoring
- `hotfix` - Critical production fix
- `release` - Release preparation

**Issue Reference:**
- Ticket ID (e.g., `PROJ-123`)
- `no-ref` if no ticket

**Examples:**
```
feat/PROJ-123/add-oauth
fix/no-ref/memory-leak
chore/PROJ-456/update-deps
docs/no-ref/api-guide
```

**Validation:**
- Enforced by `ci/common/ci.d/10-branch-name.py`
- Runs during CI checks
- Fails if branch name doesn't match pattern

## Commit Message Convention

**Format:** Conventional Commits (https://www.conventionalcommits.org/)

```
<type>: <description>

[optional body]

[optional footer]
```

**Types for semantic versioning:**
- `feat:` - New feature (minor version bump)
- `fix:` - Bug fix (patch version bump)
- `perf:` - Performance improvement (patch bump)
- `BREAKING CHANGE:` - Breaking change (major version bump)

**Other types (no version bump):**
- `chore:` - Maintenance
- `docs:` - Documentation
- `style:` - Formatting
- `refactor:` - Code refactoring
- `test:` - Tests
- `build:` - Build system
- `ci:` - CI configuration

**Examples:**
```
feat: add user authentication module

Implements OAuth2 authentication with JWT tokens.

Closes #123
```

```
fix: prevent VERSION file corruption

Implement dual pre-sync strategy with pre-commit hook
and CI script to ensure VERSION is always correct.
```

```
BREAKING CHANGE: remove deprecated API endpoints

The /v1/old-endpoint has been removed. Use /v2/endpoint instead.
```

## Git Workflow

**1. Create feature branch:**
```bash
git checkout -b feat/PROJ-123/my-feature
```

**2. Make changes and commit:**
```bash
git add .
git commit -m "feat: implement my feature"
# Pre-commit hook auto-runs (version pre-sync, linting, etc.)
```

**3. Push to remote:**
```bash
git push -u origin feat/PROJ-123/my-feature
```

**4. Create pull request:**
```bash
gh pr create --title "feat: implement my feature" --body "Description..."
```

**5. After PR merge, create release (on main):**
```bash
git checkout main
git pull
CI_FORCE_RELEASE=1 CI_PUSH=1 ci-local/.venv/bin/python ci/common/ci.d/90-semantic-release.py release
# Creates version tag, updates CHANGELOG, triggers GitHub Actions
```

## Pre-commit Hooks

**HyperCI provides these pre-commit hooks:**

1. **VERSION pre-sync** (`.git/hooks/pre-commit`)
   - Auto-syncs VERSION file before commits on main/master
   - Prevents {version} template corruption
   - Runs automatically (no user action needed)

**To skip hooks (not recommended):**
```bash
git commit --no-verify -m "message"
```

## Submodule Management

**ci/ is a READ-ONLY git submodule** - never commit directly to it.

**To update ci/ submodule:**
```bash
cd ci
git pull origin main  # Or: git checkout v1.2.0
cd ..
git add ci
git commit -m "chore: update ci/ submodule to latest"
```

**To contribute to HyperCI:**
```bash
cd ci
git checkout -b fix/my-improvement
# Make changes
git add .
git commit -m "fix: my improvement"
git push origin fix/my-improvement
# Create PR to hypersec-io/hyperci
```

## Semantic Versioning

**Versions follow semver:** `MAJOR.MINOR.PATCH`

**Version bumps:**
- `feat:` commits → MINOR bump (1.0.0 → 1.1.0)
- `fix:` commits → PATCH bump (1.0.0 → 1.0.1)
- `BREAKING CHANGE:` → MAJOR bump (1.0.0 → 2.0.0)
- Other commits (`chore:`, `docs:`) → No bump

**Managed by:**
- `python-semantic-release` (in ci-local/.venv)
- Configuration in `pyproject.toml` [tool.semantic_release]
- Automatic CHANGELOG.md generation
- Git tag creation and pushing

**For more details, see:**
- https://www.conventionalcommits.org/
- https://semver.org/
- https://python-semantic-release.readthedocs.io/
