<!-- HYPERCI_STATE_MD: hyperci-code-assistant -->
# Code Assistant Guidance

**Project-specific guidance for AI code assistants.**

This file is auto-created by `./ci/ai install` and merges:
- Common guidance from `ci/modules/common/templates/CODE-ASSISTANT.md`
- Language-specific guidance (e.g., Python) from `ci/modules/{language}/templates/CODE-ASSISTANT.md`

You can customize this file with project-specific guidelines below the auto-merged sections.

---

## Bash Tool Usage: Minimize Permission Prompts

**CRITICAL:** Compound commands (`&&`, `||`, `;`) and pipes (`|`) trigger permission prompts even when individual commands are pre-approved.

### Solutions (in order of preference)

**1. Separate Bash tool calls** (preferred):
```bash
# Instead of: git add . && git commit -m "message"
git add .
git commit -m "message"
```

**2. Use intermediate files in `.tmp/`** (for pipes):
```bash
# Instead of: jq '.foo' file | grep bar
jq '.foo' file.json > .tmp/output.json
grep bar .tmp/output.json
```

**3. Output redirection** (SAFE - no prompt):
```bash
# These DON'T trigger prompts:
command > .tmp/output.txt
command >> .tmp/output.txt
command 2> .tmp/error.log
```

### When Compound Commands ARE Acceptable

**ONLY when technically required:**

✅ `cd dir && command` - cd doesn't persist across Bash calls
✅ `export VAR=val && command` - env vars don't persist
✅ Critical cleanup: `operation || cleanup`

❌ Everything else - use separate calls or `.tmp/` intermediate files

### Key Points

- **Redirection (`>`, `>>`, `2>`)**: SAFE, no extra prompts
- **Pipes (`|`)**: Use `.tmp/` intermediate files instead
- **Compound (`&&`, `||`, `;`)**: Use separate Bash calls
- **Default strategy**: Separate calls + `.tmp/` files for chaining

---

## Project-Specific Guidelines

<!-- Add your project-specific AI assistant guidelines below -->



---

<!-- HYPERCI_STATE_MD: hyperci-code-assistant-python -->
# Python Development - AI Assistant Guidance

**Python-specific guidance (auto-merged into ci-local/CODE-ASSISTANT.md).**

---

## Python Virtual Environments

**Two separate venvs - NEVER mix:**
- `ci-local/.venv` - CI tools only (pytest, ruff, mypy, build, twine)
- `.venv` - Project runtime dependencies only

**CI scripts enforcement:**
```python
if "ci-local/.venv" not in sys.prefix:
    sys.exit("ERROR: Must run in ci-local/.venv")
```

## Python Testing

**Framework:** pytest + coverage + mypy + ruff

**Coverage targets:**
- Overall: 80% minimum (configurable in ci.yaml)
- Docstrings: 60% minimum

## Python Version Sync

**VERSION file auto-synced across:**
- `VERSION` (source of truth)
- `pyproject.toml`
- `src/<package>/__init__.py`

**NEVER manually edit VERSION** - semantic-release updates it.

---

**See:** `ci/docs/PYTHON.md`, `ci/docs/TESTING.md`
