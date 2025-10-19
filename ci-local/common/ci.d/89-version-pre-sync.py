#!/usr/bin/env python3
"""
Version Pre-sync Script (Common - ALL project types)

Handles VERSION file pre-sync for ALL project types.
This is the common layer that all project types use.

Part of dual pre-sync strategy:
- Option 1: Pre-commit hook (.git/hooks/pre-commit) - local development
- Option 2: This script - CI environments and explicit releases
"""

import os
import sys
from pathlib import Path

# CRITICAL: Enforce ci-local/.venv usage
if "ci-local/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci-local/.venv")
    print(f"Current Python: {sys.executable}")
    sys.exit(1)

# Import from ci_local_lib
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ci_local_lib import (
        logger, get_project_root, get_version_from_file,
        get_next_semantic_version, is_valid_version
    )
except ImportError as e:
    print(f"ERROR: ci_local_lib not found: {e}")
    sys.exit(1)


def sync_version_file(root: Path, version: str) -> bool:
    """Write version to VERSION file. Returns True if updated."""
    version_file = root / "VERSION"
    current = get_version_from_file(root)

    if current == version:
        logger.info(f"VERSION already synced to {version}")
        return False

    try:
        version_file.write_text(f"{version}\n")
        logger.info(f"✓ VERSION pre-synced: {current or '(empty)'} → {version}")
        return True
    except Exception as e:
        logger.error(f"Failed to write VERSION file: {e}")
        return False


def check_version_file(root: Path) -> int:
    """Check if VERSION file exists and is valid. Returns 0 if valid, 1 if not."""
    version = get_version_from_file(root)

    if not version:
        logger.error("VERSION file is empty or corrupted")
        return 1

    if not is_valid_version(version):
        logger.error(f"VERSION has invalid format: {version}")
        return 1

    logger.info(f"✓ VERSION valid: {version}")
    return 0


def pre_sync_before_release(root: Path) -> int:
    """Pre-sync VERSION before semantic-release runs. Returns 0 on success."""
    if os.environ.get("CI_SKIP_VERSION_SYNC") == "1":
        logger.info("CI_SKIP_VERSION_SYNC=1, skipping pre-sync")
        return 0

    logger.info("Running semantic-release dry-run to determine next version...")
    next_version = get_next_semantic_version(root)

    if not next_version:
        logger.info("No new version to release")
        return 0

    logger.info(f"Next version from semantic-release: {next_version}")

    if sync_version_file(root, next_version):
        logger.info("✓ Pre-sync complete - VERSION ready for semantic-release")

    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|release]", sys.argv[0])
        return 1

    action = sys.argv[1]
    root = get_project_root()

    if action == "check":
        return check_version_file(root)
    elif action == "install":
        logger.info("Version pre-sync requires no installation")
        return 0
    elif action == "release":
        return pre_sync_before_release(root)
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
