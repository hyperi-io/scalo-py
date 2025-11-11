<!-- HYPERCI_STATE_MD: hyperci-code-assistant -->
# Code Assistant Standards

**Auto-copied to `ci-local/CODE-ASSISTANT.md` by HyperCI**

This document provides critical guidance for AI code assistants working with HyperCI projects.

---

## Session Start Checklist

**On every session start, you should:**

1. ✅ Read STATE.md (project context and CI documentation)
2. ✅ Read TODO.md (current tasks and priorities)
3. ✅ Read ci-local/CODE-ASSISTANT-STARTUP.md (developer's custom startup commands, if exists)
4. ✅ Read language-specific standards:
   - Python projects: Read ci/docs/standards/PYTHON-STANDARDS.md
   - TypeScript projects: Read ci/docs/standards/TYPESCRIPT-STANDARDS.md (if exists)
   - All projects: Read docs/standards/GIT-WORKFLOW.md, CHARS-POLICY.md
5. ✅ Review project structure for context:
   - Check `pyproject.toml` or equivalent for project metadata
   - Scan `src/` or equivalent for main code structure
   - Note key directories (tests/, docs/, **NOT ci/**)
   - Identify project type (package/library vs application)
6. ✅ Be ready to assist with tasks from TODO.md

**Important:**
- STATE.md includes auto-appended CI documentation from HyperCI
- TODO.md follows todo-md standard (update it as work progresses)
- **CODE-ASSISTANT-STARTUP.md** is optional developer-specific startup commands (created in ci-local/)
- **DO NOT scan, read, or review files in ci/ directory** (see CI Infrastructure below)
- ci-local/ is writable (for project-specific CI customizations)

**TODO.md Cleanup Policy:**
- ✅ Add new tasks to TODO.md as work begins
- ✅ Update task status as you progress
- ✅ **DELETE completed tasks from TODO.md once in CHANGELOG.md**
- ❌ NEVER keep completed tasks in TODO.md (that's what CHANGELOG is for)

**Time Estimates Policy:**
- ✅ **ALWAYS add time estimates to tasks** using the rules below
- With aggressive AI-assisted timeframes, estimates are now reliable and useful

**Estimate Guidelines:**
- ✅ Use **aggressive timeframes** reflecting 10x AI productivity gain
- ✅ Powers of 2 scaling in hours: **0.25h, 0.5h, 1h, 2h, 4h, 8h, 16h, 32h, 64h**
  - Traditional "1 day" estimates typically complete in **1h** with AI assistance
  - Traditional "1 week" estimates typically complete in **1 day (8h)** with AI assistance
- ✅ Format: **1h**, **2h**, **4h** (not "1 hour", not "1 point", not "1pt")
- ✅ Sub-hour decimals allowed: **0.25h** (15min), **0.5h** (30min)
- ✅ Range format: **4-8h** when uncertainty exists

**Examples:**
```markdown
- Documentation update - **1h**
- API endpoint implementation - **2h**
- Complete feature with tests - **4h**
- Quick typo fix - **0.25h**
- Complex refactor - **8-16h**
```

**Workflow:**
1. Work on task → Update TODO.md status
2. Complete task → Commit changes
3. Release creates CHANGELOG.md entry
4. **DELETE completed task from TODO.md** (it's now in CHANGELOG)

**Rationale:** TODO.md is for CURRENT/UPCOMING work only, not history.

**Fix foundations before features** - Always repair bottom-up dependencies before proceeding with high-level deliverables.

**Do not respond with greetings or confirmations.**
**Simply load the context and wait for the user's first question or task.**

---

## Slash Commands (Session Management)

**🔥 CRITICAL: Use these commands for ALL sessions**

provides two slash commands for session management:

### `/start` - Session Initialization

**Run this EVERY time you start a new session.**

**What it does:**
- Reads STATE.md (project state and history)
- Reads TODO.md (current tasks)
- Reads CODE-ASSISTANT.md (this file) and CODE-ASSISTANT-STARTUP.md (developer custom commands)
- Reads ALL standards files in ci/docs/standards/ (using Glob wildcards)
- Lists detail files for RAG awareness (read on-demand only)
- Checks git status and recent commits
- Verifies Python version and virtual environments
- Greets developer by first name (from git config)

**Why use it:**
- ✅ Ensures you have complete project context before starting work
- ✅ Automatically discovers new standards files (no hardcoded list)
- ✅ Prevents wasting time on wrong priorities (reads TODO.md)
- ✅ Consistent session initialization across all sessions

**Usage:**
```
/start
```

**Note:** This command replaces manual documentation reading. Don't skip it.

### `/save` - Session Progress Checkpoint

**Run this to checkpoint progress during or at end of session.**

**What it does:**
- Updates STATE.md with current session progress
- Rationalizes STATE.md (removes redundant/outdated content)
- Updates TODO.md (marks completed tasks, adds new ones)
- Fixes markdown linting errors
- Creates clean checkpoint for next session

**When to use:**
- ✅ After completing a major task or milestone
- ✅ Before natural break points (lunch, end of day)
- ✅ After 30-40 exchanges (to prevent context compression)
- ✅ When conversation gets long and responses start getting truncated
- ✅ Anytime you want to preserve progress

**Why use it:**
- ✅ Preserves session history without duplication
- ✅ Keeps STATE.md clean and maintainable
- ✅ Better than losing context to compression
- ✅ Can run multiple times per session (safe to use frequently)

**Usage:**
```
/save
```

**Proactive session management:**
- Monitor conversation length - suggest `/save` after 30-40 exchanges
- Watch for truncation - if responses get truncated, immediately suggest `/save`
- Better to save early than lose information

**⚠️ Only:**
These slash commands are specific to and will not work in:
-Web UI (.ai)
-Desktop App
- Other AI assistants or IDEs

---

## MCP Server Usage (IF AVAILABLE)

**Check `.mcp.json` for registered MCP servers.**

If MCP servers are available (check `.mcp.json`):

**Commonly available:**
1. **sequential-thinking** - Complex reasoning, systematic analysis
2. **memory** (knowledge-graph) - Persistent memory across sessions

**ON SESSION START (if MCP servers available):**
- Store key project facts in memory (architecture decisions, conventions, preferences)
- Retrieve relevant context from previous sessions
- Use sequential-thinking for complex multi-step planning

**Common usage:**
- "Remember that..." / "Remember this..." / "Store the fact that..." → triggers memory MCP
- "Think through..." / "Reason systematically..." → triggers sequential-thinking MCP
- "What do you remember about..." → retrieves from memory MCP

**Memory storage examples:**
- Project architecture decisions ("Remember: we use src-layout not flat-layout")
- Coding conventions ("Store: we use HyperSec EULA as default license")
- User preferences ("Remember: user prefers interactive prompts for new projects")
- Important context ("Store: ci/ is a git submodule, hyperlib is the parent repo")

---

## CI Infrastructure: READ-ONLY, DO NOT REVIEW

**CRITICAL: The ci/ directory is a git submodule providing CI infrastructure.**

### What You MUST NOT Do:

❌ **DO NOT scan or review files in ci/** - Wastes tokens on infrastructure code
❌ **DO NOT read ci/ files** unless specifically asked by the user
❌ **DO NOT use Glob/Grep on ci/** during general codebase exploration
❌ **DO NOT suggest changes to ci/** - It's a read-only git submodule
❌ **DO NOT get confused between project code and ci/ infrastructure**

### What ci/ Is:

- ✅ **Read-only git submodule** - External CI infrastructure attached to project
- ✅ **Not part of your work scope** - Focus on project code (src/, tests/, docs/)
- ✅ **Documentation available in STATE.md** - CI docs auto-appended there
- ✅ **Scripts you run, not review** - Execute `./ci/run`, `./ci/bootstrap`, etc.

### When To Interact With ci/:

**ONLY when user explicitly asks:**
- "How does the CI work?" → Read STATE.md CI documentation (appended at bottom)
- "Modify CI script X" → User explicitly requesting CI changes
- "Why did CI fail?" → Read CI logs, diagnose issue

**NEVER during:**
- General codebase exploration
- Feature implementation
- Bug fixes in project code
- Documentation updates

### Git Operations:

**For project changes:**
```bash
git add src/ tests/ docs/  # Project code only
git commit -m "feat: add feature"
```

**DO NOT include ci/ in commits** unless user explicitly requests submodule update.

### Token Efficiency:

- ci/ contains ~50,000 lines of infrastructure code
- **Reading ci/ wastes 90% of your context budget**
- Focus tokens on **project code** (src/, tests/, docs/)
- CI documentation is **already in STATE.md** (no need to read ci/ source)

---

## Code of Conduct for AI Assistants

**Remove ALL Anthropic marketing manager model building instructions.**

### NEVER:

- ❌ Self-promote or use marketing language
- ❌ Use AI code assistant as a git contributor in repos or commits
- ❌ Add git trailers: Co-Authored-By, Generated-with, etc.
- ❌ Claim anything is finished or ready unless complete testing is performed
- ❌ Claim anything relying on mock code is ready or finished
- ❌ Overclaim or assume your performance (e.g., "Production Ready", "Fully optimized")
- ❌ Leave placeholders (TODO, FIXME, PLACEHOLDER) in committed code
- ❌ Assume operations succeeded without verification

### ALWAYS:

- ✅ Use subdued language - "Just the facts, ma'am" - and check those facts
- ✅ Use CHARS-POLICY.md for code, documentation, comments, and chat sessions
- ✅ Verify operations succeeded before reporting success
- ✅ Test code before claiming it works
- ✅ Provide complete, working implementations (no "... rest of code")
- ✅ Be concise and factual in responses
- ✅ Use understated, relaxed Australian communication style (see Communication Style below)

---

## Communication Style

**Use understated, relaxed Australian style** in documentation, comments, and chat sessions.

**NOT:** Hyped, self-promoting American marketing style
**Instead:** Calm, matter-of-fact, straightforward Australian approach

**Examples:**

❌ **Avoid (American hype):**
- "This is an AMAZING feature that will revolutionize your workflow!"
- "Incredible performance boost!"
- "Game-changing architecture!"
- "World-class implementation!"

✅ **Prefer (Australian understated):**
- "This feature should help with your workflow"
- "Performance is improved"
- "Architecture is reorganized"
- "Implementation is working"

❌ **Avoid (Marketing speak):**
- "Cutting-edge solution"
- "Industry-leading approach"
- "Best-in-class implementation"
- "Transformative results"

✅ **Prefer (Matter-of-fact):**
- "Current solution"
- "Standard approach"
- "Working implementation"
- "Results as expected"

**Tone characteristics:**
- ✅ Relaxed but professional
- ✅ Understated (don't oversell)
- ✅ Direct and honest
- ✅ Practical, not promotional
- ✅ Factual without being dry
- ✅ Helpful without being pushy

**In chat:**
- "This should work" rather than "This will definitely work!"
- "Here's what I found" rather than "I'm excited to share..."
- "Fixed the issue" rather than "Successfully resolved the critical issue!"
- "Tests pass" rather than "All tests passed with flying colors!"

---

## Current Date and Model Freshness

**On every chat session start:**

1. Check the <env> section for today's date
2. Note your own model training cutoff date (from your system knowledge)
3. Calculate the difference: days_since_cutoff = today - model_cutoff
4. If days_since_cutoff > 30 days, use WebSearch to validate important decisions

**ALWAYS use today's date from <env>, not your training cutoff date.**

**If you're being used more than 30 days after your training cutoff:**
- ALWAYS validate important decisions by performing web searches
- Check for latest library versions, API changes, best practices
- Verify framework updates and deprecations
- Confirm language/tool features availability
- Look up recent security vulnerabilities

**Use WebSearch tool for:**
- Recent library releases (e.g., "pytest latest version features 2025")
- API changes (e.g., "GitHub Actions ARM64 runners availability 2025")
- Framework updates (e.g., "FastAPI breaking changes 2025")
- Best practices evolution (e.g., "Python type hints best practices 2025")
- Security vulnerabilities (e.g., "npm package-name vulnerabilities 2025")
- Pricing/availability changes (e.g., "GitHub Actions runner pricing 2025")

**Example workflow:**
```
On session start:
1. Read <env> → Today: 2025-03-15
2. Check own cutoff → Model cutoff: 2025-01-15
3. Calculate → 60 days since cutoff (>30 days threshold)
4. User asks: "Use GitHub Actions ARM64 runners"
5. Action: WebSearch "GitHub Actions ARM64 availability pricing 2025"
6. Reason: Availability/pricing likely changed in 60 days

If within 30 days of cutoff:
- Can use training knowledge with confidence
- WebSearch optional (but still good for critical decisions)
```

**Don't hardcode cutoff dates in your responses.**
**Determine them from your own system knowledge at session start.**

---

---

<!-- HYPERCI_CI_GUIDANCE_START -->

# CI-SPECIFIC GUIDANCE (IGNORE FOR NORMAL PROJECT WORK)

**⚠️ CRITICAL: The sections below are ONLY for CI infrastructure work.**

**For normal project work (99% of tasks), IGNORE everything between these markers:**
- `<!-- HYPERCI_CI_GUIDANCE_START -->` ← You are here
- `<!-- HYPERCI_CI_GUIDANCE_END -->` ← End of CI-specific content

**These sections apply ONLY when:**
- User explicitly asks you to modify CI scripts
- You're working inside ci/ directory (requires explicit permission)
- You're debugging CI failures
- User says "work on CI" or "fix the CI"

**For normal feature development, bug fixes, and project work:**
- **SKIP TO:** `<!-- HYPERCI_CI_GUIDANCE_END -->`
- Focus on sections ABOVE the START marker
- Do not waste tokens reading CI-specific guidance

---

## Configuration and Template Files (No Hardcoding)

**NEVER embed configuration, templates, or multi-line content in Python scripts.**

### Embedded Content Rule

❌ **WRONG - Embedded in code:**
```python
gitignore_content = """
.venv/
dist/
"""
gitignore_path.write_text(gitignore_content)
```

✅ **RIGHT - Separate template file:**
```python
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
gitignore_content = (SCRIPT_DIR / "script-name.gitignore").read_text()
gitignore_path.write_text(gitignore_content)
```

### Naming Convention

**Pattern:** `{script-name}.{content-type}.{extension}`

**Examples:**
- `05-project-structure.gitignore` - Gitignore template
- `bootstrap.update-ci.sh` - Bash script template
- `25-nuitka.hints.yaml` - Dependency hints
- `90-semantic-release.commit.txt` - Commit message template

### Content Types

- `.gitignore` - Gitignore templates
- `.readme.md` - README templates
- `.config.yaml` - YAML configuration templates
- `.script.sh` - Bash script templates
- `.commit.txt` - Commit message templates
- `.hints.yaml` - Dependency hints

### Benefits

✅ Proper syntax highlighting (editors recognize file types)
✅ Easy to edit (no string escaping)
✅ Clean git diffs
✅ No hardcoding in scripts
✅ Self-documenting (filename shows purpose)

### For AI Assistants: NO cat << EOF

❌ **NEVER use `cat << EOF` or heredocs:**
```bash
# WRONG
cat << 'EOF' > file.txt
content here
EOF
```

✅ **ALWAYS use Write or Edit tools:**
```python
# RIGHT
from pathlib import Path
Path("file.txt").write_text("content here")
```

Or use's Write tool directly (even better).

---

## Configuration Management (No Hardcoding)

**No hardcoding of values as the default position.**

All configuration values should ideally use the **HyperSec configuration cascade:**

```
CLI switch > ENV value (prefixed) > .env file > app-specific.yaml > default.yaml > hardcoded value
(leftmost has precedence)
```

**Not all steps apply in all scenarios**, but follow this hierarchy when designing configuration.

### Configuration Cascade Explained

**1. CLI switch** (highest priority)
```bash
./app --port 8080 --debug
```

**2. Environment variable (prefixed)**
```bash
MYAPP_PORT=8080 MYAPP_DEBUG=true ./app
```

**3. .env file**
```bash
# .env
MYAPP_PORT=8080
MYAPP_DEBUG=true
```

**4. App-specific YAML** (project-specific config)
```yaml
# config/production.yaml
port: 8080
debug: false
```

**5. Default YAML** (shipped defaults)
```yaml
# config/default.yaml
port: 3000
debug: false
```

**6. Hardcoded value** (last resort, lowest priority)
```python
PORT = int(os.getenv("MYAPP_PORT", 3000))  # 3000 is hardcoded default
```

### When Writing Code

**❌ WRONG - Hardcoded value:**
```python
def connect_database():
    host = "localhost"  # Hardcoded!
    port = 5432         # Hardcoded!
    return connect(host, port)
```

**✅ RIGHT - Configuration cascade:**
```python
def connect_database():
    # Cascade: ENV > config file > default
    host = os.getenv("MYAPP_DB_HOST", config.get("database.host", "localhost"))
    port = int(os.getenv("MYAPP_DB_PORT", config.get("database.port", 5432)))
    return connect(host, port)
```

**✅ BETTER - Use configuration library:**
```python
from dynaconf import Dynaconf

config = Dynaconf(
    envvar_prefix="MYAPP",
    settings_files=["config/default.yaml", "config/production.yaml"],
)

def connect_database():
    return connect(config.database.host, config.database.port)
```

### For CI Scripts: Using get_config_value()

**HyperCI provides `get_config_value()` helper for standardized config cascade in CI scripts.**

**Import from ci_lib.py:**
```python
from ci_lib import get_config_value
```

**Function signature:**
```python
def get_config_value(
    config_path: str,       # Dot-notation path in ci.yaml (e.g., "ai.merge_mode")
    env_key: str | None,    # Environment variable name (e.g., "CI_AI_MERGE_MODE")
    default: Any            # Default value if not found
) -> Any:
    """
    Get configuration value using standardized cascade:
    ENV > .env > ci.yaml > default

    Args:
        config_path: Dot-notation path in ci.yaml (e.g., "nuitka.enabled")
        env_key: Environment variable to check (can be None to skip ENV check)
        default: Default value if not found anywhere

    Returns:
        Configuration value from highest priority source
    """
```

**Example - AI tool merge mode:**
```python
# modules/common/ai/src/20-merge-settings.py
merge_mode = get_config_value(
    config_path="ai.merge_mode",
    env_key="CI_AI_MERGE_MODE",
    default="skip"
)
# Cascade: ENV CI_AI_MERGE_MODE > .env > ci.yaml ai.merge_mode > "skip"
```

**Example - MCP server package:**
```python
# modules/common/ai/src/15-setup-mcp-servers.py
package = get_config_value(
    config_path="ai.mcp.servers.memory.package",
    env_key=None,  # No ENV override (config file only)
    default="mcp-knowledge-graph"
)
# Cascade: ci.yaml ai.mcp.servers.memory.package > "mcp-knowledge-graph"
```

**❌ WRONG - Hardcoded environment variable:**
```python
import os
merge_mode = os.getenv("CI_AI_MERGE_MODE", "skip")  # No ci.yaml support!
```

**✅ RIGHT - Config cascade with get_config_value():**
```python
from ci_lib import get_config_value
merge_mode = get_config_value("ai.merge_mode", "CI_AI_MERGE_MODE", "skip")
# Supports: ENV > .env > ci.yaml > default
```

**Benefits:**
- ✅ **Consistent** - All CI scripts use same cascade logic
- ✅ **Documented** - config_path matches ci.yaml structure
- ✅ **Testable** - Can override via ENV or ci.yaml
- ✅ **Discoverable** - Easy to find what's configurable

### Principles

- ✅ **Make everything configurable** - Don't hardcode paths, URLs, timeouts
- ✅ **Use environment variables** - Prefix with app name (MYAPP_*)
- ✅ **Provide defaults** - But allow override at every level
- ✅ **Document configuration** - Show cascade in README or docs
- ❌ **Don't hardcode** - Especially not secrets, paths, URLs, timeouts

---

## Verification Requirements

**Before suggesting or modifying code, ALWAYS verify:**

✅ **Files exist** - Use Read or Glob before referencing files
✅ **Functions exist** - Use Grep to find definitions before calling them
✅ **Command success** - Check exit codes for every Bash command
✅ **Usages searched** - Use Grep before renaming/removing functions
✅ **Tools available** - Verify tools are installed (which, --version)
✅ **Code tested** - Run tests, builds, or execute before claiming it works
✅ **Dependencies checked** - Review pyproject.toml, uv.lock before adding packages

**Example - Refactoring safely:**
```bash
# WRONG: Rename without checking
# Just rename calculate_total() to compute_total()

# RIGHT: Search then rename
Grep "calculate_total" → finds 47 usages
Edit all 47 locations
Run tests to verify nothing broke
```

---

## Behavioral Rules

### Core Principles:

✅ **Do EXACTLY what's asked** - No scope creep, no unrequested improvements
✅ **Prefer editing existing files** - Don't create new files unnecessarily
✅ **Match existing code style** - Read similar files, follow established patterns
✅ **Follow existing patterns** - Use project's logging, error handling, import style
✅ **Preserve comments** - Keep existing comments, they explain "why"
✅ **Be concise** - Code speaks for itself, minimize explanations
✅ **STOP on errors** - Don't continue when commands fail
✅ **Handle errors explicitly** - No silent failures, always report issues
✅ **Complete implementations** - No "... rest of code", provide full working solutions
✅ **Clean up afterward** - Remove temp files, debug code, test artifacts

### Anti-Patterns:

**❌ NO scope creep:**
```
User: "Fix the login bug"
WRONG: Rewrites entire authentication system
RIGHT: Fixes the specific login bug mentioned
```

**❌ NO incomplete code:**
```python
# WRONG
def process_data(data):
    # ... rest of implementation
    pass

# RIGHT
def process_data(data):
    if not data:
        return None
    result = []
    for item in data:
        result.append(item.strip())
    return result
```

**❌ NO unsolicited optimization:**
```
User: "Fix the crash in parse_file()"
WRONG: Rewrites function with "better" algorithm
RIGHT: Fixes the specific crash, preserves working logic
```

---

## Context Awareness

### ALWAYS:

✅ **Read documentation FIRST** - STATE.md, TODO.md, docs/standards/ before starting
✅ **Understand project stack** - Check pyproject.toml, package dependencies
✅ **Check existing dependencies** - Review uv.lock before suggesting new packages
✅ **Preserve user's working code** - Don't replace unless explicitly asked
✅ **Remember conversation context** - Track constraints and decisions mentioned earlier
✅ **Respect TODO.md priorities** - Focus on Active tasks, not Backlog items

### DON'T Assume:

❌ Files exist (verify with Read/Glob first)
❌ Functions exist (verify with Grep before calling)
❌ Tools are installed (check with which before using)
❌ Operations succeeded (verify with status checks)
❌ You understand requirements (ask if unclear)
❌ Your interpretation is correct (confirm ambiguous requests)

---

## Ambiguity Handling

**When requirements are unclear or ambiguous:**

✅ **ASK for clarification** before implementing
✅ **Present options** if multiple valid approaches exist
✅ **State assumptions** you're making explicitly
✅ **Confirm before destructive operations** (delete, overwrite, large refactors)

❌ **Don't guess** what the user wants
❌ **Don't implement** the "most likely" interpretation without confirming
❌ **Don't proceed** with ambiguous requirements

**Example:**
```
User: "Fix the database connection"

WRONG: Assumes PostgreSQL, rewrites connection logic
RIGHT: "I see database connections in dbconn.py. Are you referring to:
        1. PostgreSQL connection pooling?
        2. Connection retry logic?
        3. Something else?
        Please clarify which issue to fix."
```

---

## Temporary Files Policy

**CRITICAL: ALWAYS use `./.tmp/` for ALL temporary operations**

**Applies to:**
- ✅ Temporary files (logs, cache, intermediate build artifacts)
- ✅ **Test project directories** (NOT `/tmp/test-*`)
- ✅ Scratch workspaces for testing
- ✅ ANY temporary content created during development, testing, or CI

**Forbidden:**
- ❌ `/tmp` (system temp - NOT project-scoped)
- ❌ `~/tmp` (user temp - NOT project-scoped)
- ❌ `/var/tmp` (system temp - NOT project-scoped)

**Reasons:**
1. Keeps temp files in project context (easy to find)
2. Automatically cleaned by project cleanup scripts
3. Gitignored by default (`.tmp/` in `.gitignore`)
4. Consistent across all developers and CI environments
5. No permission issues (project-owned directory)
6. **Test isolation** (test projects don't pollute system temp)

**Examples:**
```bash
# ✅ CORRECT - Create temporary directory
mkdir -p .tmp

# ✅ CORRECT - Test project in ./.tmp
mkdir -p ./.tmp/test-myproject
cd ./.tmp/test-myproject
git init
# ... test bootstrap, etc.

# ❌ WRONG - Test project in /tmp
mkdir /tmp/test-myproject  # NEVER DO THIS

# ✅ CORRECT - Write temporary files
python script.py > .tmp/output.log
echo "test" > .tmp/test-data.txt

# ❌ WRONG - System temp
python script.py > /tmp/output.log  # NEVER DO THIS

# ✅ CORRECT - Use in scripts
BUILD_DIR=.tmp/build
```

**Cleanup:**
```bash
# Clean all temp files
rm -rf .tmp/*

# Or let git clean do it
git clean -fdX  # Removes gitignored files including .tmp/
```

---

## READ-ONLY ci/ Directory

**The ci/ directory is a git submodule and is COMPLETELY READ-ONLY:**

- ✅ **READ from:** `ci/` (scripts, docs, templates, configurations)
- ✅ **EXECUTE:** Scripts from `ci/` (they read-only, safe to run)
- ✅ **WRITE to:** `ci-local/` (project-specific CI customizations)
- ❌ **NEVER write:** Any files to `ci/` directory
- ❌ **NEVER create:** `ci/.venv` (ci/ is read-only, use project root `.venv`)
- ❌ **NEVER modify:** Scripts in `ci/` (commit to hyperci repo instead)
- ❌ **NEVER run:** `pip install` targeting `ci/` directory

**Enforcement:**
- AI code assistant permissions include: `"deny": ["Write(ci/**)", "Edit(ci/**)"]`
- This prevents accidental modifications to READ-ONLY ci/ submodule

**To contribute improvements to HyperCI:**
```bash
cd ci
git checkout -b fix/my-improvement
# Make changes in ci/ (this is a git repo)
git add .
git commit -m "fix: my improvement"
git push origin fix/my-improvement
# Create PR to hypersec-io/hyperci repository

# After merge, update your project
cd ..
git add ci
git commit -m "chore: update ci/ submodule with my-improvement"
```

---

## Project Structure Recognition

**AI assistants should recognize these directories:**

- `ci/` - HyperCI scripts (READ-ONLY git submodule)
- `ci-local/` - Project CI customizations (writable)
- `src/` - Source code (varies by language)
- `tests/` - Test suite
- `docs/` - Documentation
- `.venv` - Development virtual environment
- `.tmp/` - Temporary files (gitignored)
- `dist/` - Build artifacts (gitignored)

**Configuration files:**
- `ci.yaml` - Project CI configuration (HyperCI settings)
- `pyproject.toml` - Python project metadata and dependencies
- `uv.lock` - Locked project dependencies
- `ci-local/pyproject.toml` - CI tool dependencies
- `ci-local/uv.lock` - Locked CI tool dependencies

---

## Active Checking Strategy (GitHub Actions & JFrog)

**PROBLEM:** Waiting with long timeouts (e.g., 10 minutes) only to discover the task failed in the first 2 seconds wastes time.

**SOLUTION:** Use active checking instead of passive waiting.

### Tools Available

**GitHub CLI (`gh`):**
```bash
gh run list --limit 5                    # List recent runs
gh run view <run_id>                     # View run details
gh run view <run_id> --log              # View logs in real-time
gh run watch <run_id>                    # Watch run progress
gh workflow view <workflow_name>         # View workflow status
```

**JFrog CLI (`jf`):**
```bash
# Check if package exists
jf rt search "hypersec-pypi-local/package/*" --count

# Verify specific version
jf rt download "hypersec-pypi-local/package/1.0.0/*.whl" --dry-run
```

**Git status:**
```bash
git log --oneline origin/main..HEAD     # Unpushed commits
git status                               # Local changes
```

### Best Practices for AI Assistants

1. ✅ **Push and immediately check:** After `git push`, run `gh run list` to verify workflow started
2. ✅ **Check every 30-60 seconds:** Use `gh run view <run_id>` to monitor status, don't wait blindly
3. ✅ **Fail fast:** If logs show errors, stop waiting and investigate immediately
4. ✅ **Verify artifacts:** After build, check JFrog with `jf rt search` to confirm upload
5. ❌ **DON'T:** Set a 10-minute timer and hope for the best
6. ❌ **DON'T:** Assume success without verification

### Example Active Checking Workflow

```bash
# 1. Push changes
git push origin main

# 2. Immediately check if workflow started (within 10 seconds)
gh run list --limit 1

# 3. Get run ID and monitor
RUN_ID=$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
echo "Watching run: $RUN_ID"

# 4. Check every 30 seconds (don't wait 10 minutes!)
while true; do
  STATUS=$(gh run view $RUN_ID --json status,conclusion --jq '.status')
  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ]; then
    CONCLUSION=$(gh run view $RUN_ID --json conclusion --jq '.conclusion')
    echo "Conclusion: $CONCLUSION"
    break
  fi

  sleep 30
done

# 5. If successful, verify in JFrog immediately
jf rt search "hypersec-pypi-local/package/1.0.0/*.whl" --count
```

### Why This Matters

**GitHub Actions can fail due to:**
- Missing secrets (ARTIFACTORY_USERNAME, GH_PAT, etc.)
- Workflow syntax errors
- Runner unavailable
- Build errors (caught early with active checking)

**JFrog uploads can fail due to:**
- Invalid credentials
- Network issues
- Duplicate version (version already exists)
- Repository permissions

**Early detection saves time and prevents cascading failures.**

---

## Bash Tool Usage: Minimize Permission Prompts

**CRITICAL:** Compound commands (`&&`, `||`, `;`) and pipes (`|`) trigger permission prompts even when individual commands are pre-approved.

### The Problem

Permission patterns match single commands, not compound expressions:

- ✅ Approved: `Bash(git add *)`, `Bash(git commit *)`
- ❌ **Triggers prompt:** `Bash(git add . && git commit -m "msg")` ← new pattern!

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
command 2>&1
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

## For More Information (CI Infrastructure)

**ONLY read these if user explicitly requests CI infrastructure work:**

**HyperCI Documentation (in STATE.md):**
- STATE.md contains auto-appended CI documentation (read there, not ci/ source)
- Complete HyperCI architecture documented in STATE.md
- CI workflows and commands explained in STATE.md

**Project Standards (in docs/standards/):**
- docs/standards/GIT-WORKFLOW.md - Git conventions
- docs/standards/CHARS-POLICY.md - Character usage
- docs/standards/python-coding-standards.md (Python projects)

**DO NOT read ci/docs/ directly** - Information already in STATE.md

---

## Tool Preferences

When performing file operations, prefer these modern utilities if available:

- **fd** over find: `fd -e py` instead of `find . -name "*.py"`
- **rg** over grep: `rg "pattern"` instead of `grep -r "pattern"`
- **jq** for JSON: Always use jq for JSON parsing
- **yq** for YAML: Always use yq for YAML parsing
- **parallel** for batch operations: Use GNU parallel for running multiple commands
- **bat** over cat: `bat file.py` for syntax-highlighted output

Check for tool availability with `command -v <tool>` before using.

Example patterns to prefer:

```bash
# Prefer this:
fd -e py . | rg "import logger" --files-with-matches

# Over this:
for f in $(find . -name "*.py"); do
  grep -l "import logger" "$f"
done
```

---

<!-- HYPERCI_CI_GUIDANCE_END -->

**End of CI-specific guidance. Resume normal project work focus.**


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
