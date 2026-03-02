# Project-Specific Code Assistant Guidance

**Purpose:** This directory contains project-specific or developer-specific guidance for AI code assistants.

## What Goes Here

**Add markdown files with custom guidance:**

- Project-specific coding patterns
- Developer workflow preferences
- Team-specific conventions
- Project architecture notes

## How It Works

**The `/start` command loads ALL .md files from this directory:**

- Files are read automatically on session start
- Supplements corporate standards from `ci/docs/standards/`
- Overrides/customizations without modifying corporate standards

## Examples

**Example: PROJECT-SPECIFIC.md**

```markdown
# Project-Specific Guidance

This project uses:
- FastAPI for web framework
- PostgreSQL for database
- Redis for caching

When implementing features, follow the layered architecture:
- Routes in `src/myapp/api/`
- Business logic in `src/myapp/services/`
- Data access in `src/myapp/repositories/`
```

**Example: DEVELOPER-PREFERENCES.md**

```markdown
# Developer Preferences (Derek)

- Prefer explicit over implicit
- Use descriptive variable names
- Write tests first for bug fixes
```

## Architecture

```
ci/docs/standards/           # Corporate standards (read-only)
├── code-assistant/          # AI guidance (loaded by /start)
├── common/                  # Universal standards
└── python/                  # Python standards

ci-local/code-assistant/     # Project overrides (writable)
└── *.md                     # Custom guidance (loaded by /start)
```

**Loaded by:** `/start` command via `Glob: ci-local/code-assistant/*.md`

---

**Note:** This directory is gitignored by default. Add `.md` files here for personal preferences or commit them for team-shared guidance.
