#!/usr/bin/env python3
"""
Settings Merge (Bootstrap Step)

Merges settings from HyperCI into project .ai/ directory.

This allows HyperCI to provide standardized configuration while
letting projects customize settings.

Merge Sources (in order):
  1. ci/common/ai/          # Universal settings (all projects)
  2. ci/python/ai/          # Language-specific (Python only)
  3. ci-local/common/ai/    # Project overrides (optional)
  4. ci-local/python/ai/    # Project Python overrides (optional)

Merge Target:
  .ai/                      # Project's settings

Environment Control:
  CI_MERGE=merge         # Overwrite existing settings
  CI_MERGE=no-overwrite  # Keep existing, only add new
  CI_MERGE=skip          # Skipsettings merge (default - opt-in model)

Run modes:
- check: Verifysettings can be merged (always succeeds)
- install: Perform the actual merge

Usage:
    ci-local/.venv/bin/python ci-local/common/bootstrap.d/95-ai-settings.py check
    ci-local/.venv/bin/python ci-local/common/bootstrap.d/95-ai-settings.py install
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Get project root (this script is at ci-local/common/bootstrap.d/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CI_DIR = PROJECT_ROOT / "ci"
CI_LOCAL_DIR = PROJECT_ROOT / "ci-local"
AI_DIR = PROJECT_ROOT / "."


def deep_merge_json(target: Dict[str, Any], source: Dict[str, Any], overwrite: bool = True) -> Dict[str, Any]:
    """
    Deep merge two JSON dictionaries.

    Args:
        target: Target dictionary (will be modified)
        source: Source dictionary (merged into target)
        overwrite: If True, overwrite existing keys. If False, keep existing.

    Returns:
        Merged dictionary
    """
    for key, value in source.items():
        if key in target:
            # Key exists in target
            if isinstance(target[key], dict) and isinstance(value, dict):
                # Both are dicts, recurse
                target[key] = deep_merge_json(target[key], value, overwrite)
            elif overwrite:
                # Overwrite existing value
                target[key] = value
            # else: keep target[key] (no-overwrite mode)
        else:
            # New key, always add
            target[key] = value

    return target


def merge_json_file(target_file: Path, source_file: Path, overwrite: bool = True) -> bool:
    """
    Merge a JSON file from source into target with template variable substitution.

    Template variables (replaced before merge):
    - {{PROJECT_ROOT}} → Absolute path to project root

    Args:
        target_file: Target JSON file (in )
        source_file: Source JSON file (from ci/ or ci-local/)
        overwrite: If True, overwrite existing keys

    Returns:
        True if merge was performed, False if skipped
    """
    if not source_file.exists():
        return False

    # Load source with template substitution
    try:
        source_content = source_file.read_text()

        # Replace template variables
        source_content = source_content.replace("{{PROJECT_ROOT}}", str(PROJECT_ROOT))

        # Parse JSON after substitution
        source_data = json.loads(source_content)
    except Exception as e:
        print(f"[WARN] Failed to load {source_file}: {e}")
        return False

    # Load target (or start with empty dict)
    target_data = {}
    if target_file.exists():
        try:
            with open(target_file) as f:
                target_data = json.load(f)
        except Exception as e:
            print(f"[WARN] Failed to load {target_file}, starting fresh: {e}")

    # Merge
    merged_data = deep_merge_json(target_data, source_data, overwrite)

    # Write back
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, 'w') as f:
        json.dump(merged_data, f, indent=2)
        f.write('\n')  # Add trailing newline

    return True


def copy_file(target_file: Path, source_file: Path, overwrite: bool = True) -> bool:
    """
    Copy a file from source to target.

    Args:
        target_file: Target file path
        source_file: Source file path
        overwrite: If True, overwrite existing file

    Returns:
        True if copy was performed, False if skipped
    """
    if not source_file.exists():
        return False

    # Skip if target exists and overwrite is False
    if target_file.exists() and not overwrite:
        return False

    # Copy
    target_file.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(source_file, target_file)
    return True


def append_or_copy_standard(target_file: Path, source_file: Path, source_label: str) -> tuple[bool, str]:
    """
    Append or copy a standards file (MERGE behavior for same filename).

    If target exists:
    - Appends source content with separator and marker
    - Uses marker to prevent duplicate appends (idempotent)

    If target doesn't exist:
    - Copies source file

    Args:
        target_file: Target file in docs/standards/
        source_file: Source file from ci/*/ai/standards/
        source_label: Label for source (e.g., "ci/common/ai/standards")

    Returns:
        (was_modified, log_message) tuple
    """
    if not source_file.exists():
        return (False, "")

    # Create marker for idempotent append
    marker = f"<!-- HYPERCI_STANDARD: {source_label}/{source_file.name} -->"

    if target_file.exists():
        # File exists - append if not already present
        target_content = target_file.read_text()

        # Check if already appended (idempotent)
        if marker in target_content:
            return (False, "")

        # Append with marker
        source_content = source_file.read_text()
        separator = "\n\n---\n\n"
        appended_content = f"{separator}{marker}\n{source_content}"

        with open(target_file, 'a') as f:
            f.write(appended_content)

        return (True, f"  docs/standards/{source_file.name} (appended) ← {source_label}")
    else:
        # File doesn't exist - copy
        import shutil
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)

        return (True, f"  docs/standards/{source_file.name} (created) ← {source_label}")


def copy_standards_directory(overwrite: bool = True) -> list[str]:
    """
    Copy/merge standards/*.md files from ci/ to docs/standards/ (IDEMPOTENT).

    MERGE behavior: If same filename exists in multiple sources, they are MERGED (appended)
    not replaced. Example: CODE-ASSISTANT.md from common + Python = merged file.

    Copies/merges from (in order):
    1. ci/common/ai/standards/*.md
    2. ci/python/ai/standards/*.md
    3. ci-local/common/ai/standards/*.md (if exists)
    4. ci-local/python/ai/standards/*.md (if exists)

    Args:
        overwrite: If True, allow appending to existing files (merge)
                   If False, skip files that already exist

    Returns:
        List of copied/merged files (for logging)
    """
    target_dir = PROJECT_ROOT / "docs" / "standards"
    target_dir.mkdir(parents=True, exist_ok=True)

    merged_files = []

    # Discover source directories (in order)
    source_dirs = [
        (CI_DIR / "common" / "ai" / "standards", "ci/common/ai/standards"),
        (CI_DIR / "python" / "ai" / "standards", "ci/python/ai/standards"),
        (CI_LOCAL_DIR / "common" / "ai" / "standards", "ci-local/common/ai/standards"),
        (CI_LOCAL_DIR / "python" / "ai" / "standards", "ci-local/python/ai/standards"),
    ]

    for source_dir, label in source_dirs:
        if not source_dir.exists():
            continue

        # Process all .md files
        for source_file in source_dir.glob("*.md"):
            target_file = target_dir / source_file.name

            # Use append/copy logic (merges same filenames)
            was_modified, log_msg = append_or_copy_standard(target_file, source_file, label)

            if was_modified:
                merged_files.append(log_msg)

    return merged_files


def create_todo_md_from_template(force: bool = False) -> bool:
    """
    Create TODO.md from template if it doesn't exist (IDEMPOTENT).

    Safety rules:
    - NEVER overwrites existing TODO.md (unless force=True)
    - Only creates if file doesn't exist
    - Replaces YYYY-MM-DD with current date

    Args:
        force: If True, overwrite existing TODO.md (CI_MERGE=force)

    Returns:
        True if TODO.md was created, False if already exists or template missing
    """
    target_file = PROJECT_ROOT / "TODO.md"

    # SAFETY: Never overwrite existing TODO.md (unless force mode)
    if target_file.exists() and not force:
        return False

    # Find template (prefer common, no language-specific TODO templates)
    template_file = CI_DIR / "common" / "ai" / "TODO.md"

    if not template_file.exists():
        return False

    # Read template
    template_content = template_file.read_text()

    # Replace date placeholder
    import datetime
    today = datetime.date.today().strftime("%Y-%m-%d")
    content = template_content.replace("YYYY-MM-DD", today)

    # Write TODO.md
    target_file.write_text(content)

    return True


def append_state_md(target_file: Path, source_file: Path) -> bool:
    """
    Append STATE.md content from source to target (IDEMPOTENT).

    Uses markers to prevent duplicate appends:
    - Marker: <!-- HYPERCI_STATE_MD: <relative_path> -->

    Args:
        target_file: Target STATE.md (project root)
        source_file: Source STATE.md (ci/*/ai/)

    Returns:
        True if content was appended, False if already present or skipped
    """
    if not source_file.exists():
        return False

    # Ensure target exists (create if needed)
    if not target_file.exists():
        target_file.touch()

    # Read source content
    source_content = source_file.read_text()

    # Create marker (relative path from PROJECT_ROOT)
    try:
        relative_source = source_file.relative_to(PROJECT_ROOT)
    except ValueError:
        # Not relative to PROJECT_ROOT, use absolute
        relative_source = source_file

    marker = f"<!-- HYPERCI_STATE_MD: {relative_source} -->"

    # Read target content
    target_content = target_file.read_text()

    # Check if already appended (idempotent check)
    if marker in target_content:
        # Already appended, skip
        return False

    # Append with marker
    separator = "\n\n---\n\n"
    appended_content = f"{separator}{marker}\n{source_content}"

    # Write back
    with open(target_file, 'a') as f:
        f.write(appended_content)

    return True


def merge_ai_settings(merge_mode: str = "merge", force: bool = False) -> int:
    """
    Merge settings from ci/ and ci-local/ into .ai/.

    Args:
        merge_mode: "merge" (overwrite), "no-overwrite" (keep existing), or "skip"
        force: If True, overwrite TODO.md (force mode)

    Returns:
        0 on success, 1 on failure
    """
    if merge_mode == "skip":
        print("[INFO] CI_MERGE=skip, skippingsettings merge")
        return 0

    overwrite = (merge_mode == "merge")
    mode_label = "OVERWRITE" if overwrite else "NO-OVERWRITE"

    print(f"[INFO] Mergingsettings (mode: {mode_label})...")

    # Discover source directories (in order)
    source_dirs = [
        CI_DIR / "common" / "ai",
        CI_DIR / "python" / "ai",
        CI_LOCAL_DIR / "common" / "ai",
        CI_LOCAL_DIR / "python" / "ai",
    ]

    # Track what was merged
    merged_files = []

    # Merge settings.json from all sources
    for source_dir in source_dirs:
        settings_file = source_dir / "settings.json"
        if settings_file.exists():
            if merge_json_file(AI_DIR / "settings.json", settings_file, overwrite):
                merged_files.append(f"  settings.json ← {source_dir.relative_to(PROJECT_ROOT)}")

    # Copy command files (*.md) from all sources
    for source_dir in source_dirs:
        commands_dir = source_dir / "commands"
        if not commands_dir.exists():
            continue

        for source_file in commands_dir.glob("*.md"):
            target_file = AI_DIR / "commands" / source_file.name
            if copy_file(target_file, source_file, overwrite):
                merged_files.append(f"  commands/{source_file.name} ← {source_dir.relative_to(PROJECT_ROOT)}")

    # Append STATE.md files (idempotent - uses markers)
    state_md_target = PROJECT_ROOT / "STATE.md"
    for source_dir in source_dirs:
        state_md_source = source_dir / "STATE.md"
        if state_md_source.exists():
            if append_state_md(state_md_target, state_md_source):
                merged_files.append(f"  STATE.md (appended) ← {source_dir.relative_to(PROJECT_ROOT)}")

    # Copy standards/*.md files to docs/standards/
    standards_copied = copy_standards_directory(overwrite)
    merged_files.extend(standards_copied)

    # Create TODO.md from template (ONLY if doesn't exist - never overwrite unless force)
    if create_todo_md_from_template(force=force):
        if force:
            merged_files.append(f"  TODO.md (FORCE OVERWRITTEN from template)")
        else:
            merged_files.append(f"  TODO.md (created from template)")

    if merged_files:
        print(f"[INFO] Merged {len(merged_files)}settings file(s):")
        for f in merged_files:
            print(f)
    else:
        print("[INFO] Nosettings to merge (no source files found)")

    return 0


def check_nodejs_available() -> bool:
    """
    Check if Node.js and npx are available.

    Returns:
        True if both node and npx are available
    """
    import shutil

    node_available = shutil.which("node") is not None
    npx_available = shutil.which("npx") is not None

    return node_available and npx_available


def check_ai_settings() -> int:
    """
    Check ifsettings can be merged.

    Verifies:
    - Node.js is available (required for)
    - npx is available (required for)

    Returns:
        0 if requirements met, 1 if missing Node.js/npx
    """
    # Check Node.js/npx availability
    if not check_nodejs_available():
        print("[ERROR] Node.js and/or npx not found")
        print("[ERROR] requires Node.js with npx")
        print("[ERROR] Install: https://nodejs.org/ (includes npx)")
        return 1

    print("[INFO] Node.js and npx available (required for)")
    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("ERROR: Usage: 95-ai-settings.py [check|install]")
        return 1

    action = sys.argv[1]

    # Get merge mode from environment (default: skip - opt-in model)
    merge_mode = os.environ.get("CI_MERGE", "skip").lower()
    valid_modes = ["merge", "no-overwrite", "skip", "force"]

    if merge_mode not in valid_modes:
        print(f"[WARN] Invalid CI_MERGE='{merge_mode}', using 'skip'")
        merge_mode = "skip"

    # Force mode = merge + overwrite TODO.md
    force_mode = (merge_mode == "force")
    if force_mode:
        merge_mode = "merge"  # Treat as merge for settings/STATE
        print("[WARN] CI_MERGE=force - Will overwrite TODO.md (nuclear option)")

    if action == "check":
        return check_ai_settings()

    elif action == "install":
        # Check Node.js/npx availability if not skipping
        if merge_mode != "skip":
            if not check_nodejs_available():
                print("[ERROR] Cannot mergesettings: Node.js and/or npx not found")
                print("[ERROR] requires Node.js with npx")
                print("[ERROR] Install: https://nodejs.org/ (includes npx)")
                print("[ERROR] Or set CI_MERGE=skip to skipsetup")
                return 1

        return merge_ai_settings(merge_mode, force=force_mode)

    else:
        print(f"ERROR: Unknown action '{action}'")
        return 1


if __name__ == "__main__":
    sys.exit(main())
