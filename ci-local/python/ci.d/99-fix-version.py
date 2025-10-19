#!/usr/bin/env python3
"""
Version Recovery Script (Auto-Detection and Repair)

Detects and fixes VERSION file corruption (e.g., {version} template literals).

This script runs automatically during 'ci/run check' to catch version
corruption early. It can also be run manually to fix VERSION issues.

Run modes:
- check: Detect corruption and report (exit 1 if corrupted)
- fix: Auto-fix VERSION from pyproject.toml or git tag
- install: Not applicable (no installation needed)

Usage:
    ci-local/.venv/bin/python ci-local/python/ci.d/99-fix-version.py check
    ci-local/.venv/bin/python ci-local/python/ci.d/99-fix-version.py fix

Sources of truth (in order of preference):
1. Latest git tag (v*) - for released versions
2. pyproject.toml version field - for current development version
3. Manual intervention required if both missing
"""

import os
import sys
import subprocess
import re
from pathlib import Path

# CRITICAL: Enforce ci-local/.venv usage (FAIL HARD if not in ci-local/.venv)
if "ci-local/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci-local/.venv")
    print(f"Current Python: {sys.executable}")
    print("Expected: ci-local/.venv/bin/python")
    sys.exit(1)

# Import from ci_local_lib (project-specific extensions)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
    from ci_local_lib import logger, get_project_root
except ImportError as e:
    # Fallback if ci_local_lib not available
    print(f"WARNING: ci_local_lib not found: {e}")
    class SimpleLogger:
        def info(self, msg, *args): print(f"INFO: {msg % args if args else msg}")
        def warning(self, msg, *args): print(f"WARNING: {msg % args if args else msg}")
        def error(self, msg, *args): print(f"ERROR: {msg % args if args else msg}")
    logger = SimpleLogger()

    def get_project_root() -> Path:
        return Path(__file__).resolve().parent.parent.parent.parent


def get_version_from_file(root: Path) -> tuple[str, bool]:
    """
    Get version from VERSION file.

    Returns:
        (version, is_corrupted) tuple
    """
    version_file = root / "VERSION"

    if not version_file.exists():
        return ("", True)

    content = version_file.read_text().strip()

    # Check for template corruption
    if "{version}" in content:
        return (content, True)

    # Check for empty
    if not content:
        return ("", True)

    # Check for valid version format
    if not re.match(r'^\d+\.\d+\.\d+', content):
        return (content, True)

    return (content, False)


def get_version_from_pyproject(root: Path) -> str:
    """Get version from pyproject.toml."""
    pyproject = root / "pyproject.toml"

    if not pyproject.exists():
        return ""

    content = pyproject.read_text()
    match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)

    if match:
        return match.group(1)

    return ""


def get_version_from_git_tag(root: Path) -> str:
    """Get latest version from git tags."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            return ""

        tag = result.stdout.strip()

        # Remove 'v' prefix if present
        if tag.startswith('v'):
            tag = tag[1:]

        # Validate version format
        if re.match(r'^\d+\.\d+\.\d+', tag):
            return tag

        return ""

    except Exception:
        return ""


def fix_version_file(root: Path, dry_run: bool = False) -> bool:
    """
    Fix VERSION file from available sources.

    Returns:
        True if fix was applied (or would be applied in dry-run)
    """
    version_file = root / "VERSION"
    current_content, is_corrupted = get_version_from_file(root)

    if not is_corrupted:
        logger.info(f"✓ VERSION is valid: {current_content}")
        return False

    logger.warning(f"VERSION file is corrupted: '{current_content}'")

    # Try git tag first
    git_version = get_version_from_git_tag(root)
    if git_version:
        logger.info(f"Found version from git tag: {git_version}")
        if not dry_run:
            version_file.write_text(f"{git_version}\n")
            logger.info(f"✓ Fixed VERSION from git tag: {git_version}")
        else:
            logger.info(f"[DRY-RUN] Would fix VERSION from git tag: {git_version}")
        return True

    # Fall back to pyproject.toml
    pyproject_version = get_version_from_pyproject(root)
    if pyproject_version:
        logger.info(f"Found version from pyproject.toml: {pyproject_version}")
        if not dry_run:
            version_file.write_text(f"{pyproject_version}\n")
            logger.info(f"✓ Fixed VERSION from pyproject.toml: {pyproject_version}")
        else:
            logger.info(f"[DRY-RUN] Would fix VERSION from pyproject.toml: {pyproject_version}")
        return True

    # No source of truth found
    logger.error("Cannot fix VERSION: no git tag or pyproject.toml version found")
    logger.error("Manual intervention required:")
    logger.error("  1. Check latest git tag: git describe --tags --abbrev=0")
    logger.error("  2. Or use pyproject.toml version")
    logger.error("  3. Run: echo 'X.Y.Z' > VERSION")

    return False


def check_version_corruption(root: Path) -> int:
    """
    Check VERSION file for corruption.

    Returns:
        0 if valid, 1 if corrupted
    """
    current_content, is_corrupted = get_version_from_file(root)

    if is_corrupted:
        logger.error(f"✗ VERSION file is corrupted: '{current_content}'")
        logger.error("Run: ci-local/.venv/bin/python ci-local/python/ci.d/99-fix-version.py fix")
        return 1

    logger.info(f"✓ VERSION is valid: {current_content}")
    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|fix|install]", sys.argv[0])
        return 1

    action = sys.argv[1]
    root = get_project_root()

    if action == "check":
        return check_version_corruption(root)

    elif action == "fix":
        dry_run = "--dry-run" in sys.argv
        if fix_version_file(root, dry_run):
            return 0 if not dry_run else 1  # Exit 1 in dry-run to signal would fix
        return 1  # Failed to fix

    elif action == "install":
        # No installation needed
        logger.info("Version recovery requires no installation")
        return 0

    else:
        # Unknown action - skip silently
        return 0


if __name__ == "__main__":
    sys.exit(main())
