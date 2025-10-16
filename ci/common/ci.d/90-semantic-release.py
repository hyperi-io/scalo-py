#!/usr/bin/env python3
"""
Semantic Release Automation using Python Semantic Release

This script is a thin wrapper around python-semantic-release CLI.
Configuration is in pyproject.toml [tool.semantic_release]

Run modes:
- check: Verify semantic-release is available and configured
- install: Not applicable (semantic-release installed by bootstrap)
- release: Run semantic-release to create a new version (CI only)
"""

import os
import sys
import subprocess
from pathlib import Path

# CRITICAL: Enforce ci/.venv usage (FAIL HARD if not in ci/.venv)
if "ci/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci/.venv")
    print(f"Current Python: {sys.executable}")
    print("Expected: ci/.venv/bin/python")
    print("Run via: ./ci/run release")
    sys.exit(1)

# Import from ci_lib (installed in ci/.venv by bootstrap)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ci_lib import logger


def check_semantic_release() -> bool:
    """Check if python-semantic-release is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "semantic_release", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def run_semantic_release(logger, root: Path, dry_run: bool = False) -> bool:
    """
    Run python-semantic-release to create a new version.

    This uses the native Python semantic-release CLI which handles:
    1. Analyzing commits to determine next version
    2. Updating version in pyproject.toml and __init__.py
    3. Writing VERSION file (via build_command)
    4. Generating CHANGELOG.md
    5. Creating commit with all changes
    6. Creating git tag
    7. Optionally pushing to remote

    CRITICAL: Tests must pass before release!
    Set CI_TESTS_PASSED=1 to confirm tests ran successfully.

    Returns True if a new version was created.
    """
    # CRITICAL: Ensure tests have been run before releasing
    tests_marker = root / ".tmp" / "tests-passed"
    tests_passed = tests_marker.exists() and tests_marker.read_text().strip() == "1"
    force_release = os.environ.get("FORCE_RELEASE") == "1"

    if not tests_passed and not force_release:
        logger.error("Tests have not been run! Cannot release without passing tests.")
        logger.error("Marker file not found: .tmp/tests-passed")
        logger.error("")
        logger.error("Either:")
        logger.error("  1. Run: ./ci/run release (runs all checks including tests)")
        logger.error("  2. Set FORCE_RELEASE=1 to bypass (dangerous!)")
        return False

    # Check if we're in CI or if release is explicitly requested
    is_ci = os.environ.get("CI") == "true"

    if not is_ci and not force_release:
        logger.info("Not in CI and FORCE_RELEASE not set, skipping release")
        return False

    # Get current branch
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        current_branch = result.stdout.strip()
    except Exception as e:
        logger.error(f"Failed to get current branch: {e}")
        return False

    # Check if on release branch
    is_release_branch = current_branch in ["main", "master"]
    if not is_release_branch and not force_release:
        logger.info(f"Not on release branch (current: {current_branch}), skipping release")
        return False

    # Build the semantic-release command
    cmd = [sys.executable, "-m", "semantic_release", "version"]

    # Add flags based on mode
    if dry_run:
        cmd.append("--print")
        logger.info("Dry run mode - checking what version would be released")
    else:
        # Control what semantic-release does
        cmd.append("--commit")      # Create commit with version changes
        cmd.append("--tag")          # Create git tag
        cmd.append("--changelog")    # Update CHANGELOG.md

        # Handle push flag
        if os.environ.get("CI_PUSH") == "1":
            cmd.append("--push")     # Push to remote
            logger.info("CI_PUSH=1: Will push changes and tags to remote")
        else:
            cmd.append("--no-push")  # Don't push (local only)
            logger.info("CI_PUSH not set: Changes will stay local")

        # Don't create VCS release (GitHub Actions handles this)
        cmd.append("--no-vcs-release")

    # Run semantic-release
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=root,
        env={**os.environ, "CI": "true"}
    )

    if result.returncode != 0:
        logger.error(f"semantic-release failed with code {result.returncode}")
        return False

    if dry_run:
        logger.info("Dry run complete")
    else:
        # Get the version that was just released
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                check=True
            )
            new_version = result.stdout.strip()
            logger.info(f"✓ Release {new_version} completed successfully")
        except Exception:
            logger.info("✓ Release completed successfully")

    return True


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|release]", sys.argv[0])
        return 1

    action = sys.argv[1]
    root = Path(__file__).resolve().parent.parent.parent

    if action == "check":
        if not check_semantic_release():
            logger.error("python-semantic-release not found")
            logger.info("It should be installed by bootstrap in ci/.venv")
            return 1

        # Check for configuration
        pyproject_path = root / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path) as f:
                if "[tool.semantic_release]" in f.read():
                    logger.info("✓ python-semantic-release is configured in pyproject.toml")
                else:
                    logger.warning("No [tool.semantic_release] configuration found in pyproject.toml")
                    return 1
        else:
            logger.error("pyproject.toml not found")
            return 1

        return 0

    elif action == "install":
        # Installation handled by bootstrap
        logger.info("python-semantic-release installation is handled by bootstrap")
        return 0

    elif action == "release":
        if not check_semantic_release():
            logger.error("python-semantic-release not found")
            return 1

        # Run release process
        dry_run = "--dry-run" in sys.argv
        if run_semantic_release(logger, root, dry_run):
            logger.info("Release process completed successfully")
            return 0
        else:
            return 1

    else:
        # Unknown action - skip silently (other scripts may handle it)
        return 0


if __name__ == "__main__":
    sys.exit(main())
