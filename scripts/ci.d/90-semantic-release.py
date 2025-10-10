#!/usr/bin/env python3
"""
Semantic Release Automation

This script handles automatic versioning and releases using semantic-release.
It ensures version consistency across all files and the VERSION file.

Run modes:
- check: Verify semantic-release is available and configured
- install: Not applicable (semantic-release installed by bootstrap)
- release: Run semantic-release to create a new version (CI only)
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional

# CRITICAL: Enforce .venv-ci usage (FAIL HARD if not in .venv-ci)
if ".venv-ci" not in sys.prefix:
    print("ERROR: This script must run in .venv-ci")
    print(f"Current Python: {sys.executable}")
    print("Expected: .venv-ci/bin/python")
    print("Run via: ./scripts/ci release")
    sys.exit(1)

# Import hyperlib from pip-installed package (installed by bootstrap)
from hyperlib import get_logger  # type: ignore


def get_current_version(root: Optional[Path] = None) -> Optional[str]:
    """Get current version from git tags, respecting project tag format."""
    import re
    import json

    if root is None:
        root = Path.cwd()

    # Check for .releaserc.json to get tagFormat
    tag_pattern = None
    releaserc_path = root / ".releaserc.json"
    if releaserc_path.exists():
        try:
            with open(releaserc_path) as f:
                config = json.load(f)
                tag_format = config.get("tagFormat", "v${version}")
                # Convert semantic-release format to regex pattern
                # e.g., "hyperlib-v${version}" -> "hyperlib-v"
                tag_pattern = tag_format.replace("${version}", "")
        except Exception:
            pass

    try:
        # If we have a tag pattern, search for tags matching that pattern
        if tag_pattern:
            result = subprocess.run(
                ["git", "tag", "-l", f"{tag_pattern}*"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                # Get the most recent tag matching the pattern
                tags = result.stdout.strip().split('\n')
                # Sort by version (simple sort, works for most cases)
                tags.sort(reverse=True)
                if tags:
                    version = tags[0]
                    # Extract semantic version
                    match = re.search(r'(\d+\.\d+\.\d+)', version)
                    if match:
                        return match.group(1)

        # Fallback: use git describe
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            # Extract semantic version using regex
            match = re.search(r'(\d+\.\d+\.\d+)', version)
            if match:
                return match.group(1)
            # Fallback: just strip 'v' prefix
            if version.startswith('v'):
                return version[1:]
            return version
    except Exception:
        pass
    return None


def get_next_version() -> Optional[str]:
    """Get next version from semantic-release --dry-run."""
    import re

    try:
        result = subprocess.run(
            ["semantic-release", "--dry-run"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "CI": "true"}
        )

        # Parse output for version information
        # Look for patterns like:
        # - "The next release version is 1.2.3"
        # - "Published release 1.2.3"
        # - "Release version 1.2.3"
        output = result.stdout + result.stderr

        # Pattern to match semantic version
        version_patterns = [
            r'next release version is (\d+\.\d+\.\d+)',
            r'Published release (\d+\.\d+\.\d+)',
            r'Release version (\d+\.\d+\.\d+)',
            r'Published release: (\d+\.\d+\.\d+)',
        ]

        for pattern in version_patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)

        # If returncode is 0, check if there's a version in the output
        if result.returncode == 0:
            # Look for any semantic version number
            version_match = re.search(r'\b(\d+\.\d+\.\d+)\b', output)
            if version_match:
                return version_match.group(1)

    except Exception:
        pass

    return None


def update_version_file(version: str, root: Path) -> None:
    """Update VERSION file, pyproject.toml, and __init__.py to match version."""
    # Always update VERSION file
    version_file = root / "VERSION"
    version_file.write_text(f"{version}\n")

    # For Python projects, also update pyproject.toml
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            # Python 3.11+ has tomllib built-in for reading
            try:
                import tomllib as tomli
            except ImportError:
                import tomli

            import tomli_w
        except ImportError:
            # tomli_w not available, skip pyproject.toml update
            pass
        else:
            try:
                with open(pyproject_path, 'rb') as f:
                    data = tomli.load(f)

                # Update project.version if it exists
                if 'project' in data and 'version' in data['project']:
                    data['project']['version'] = version

                    with open(pyproject_path, 'wb') as f:
                        tomli_w.dump(data, f)
            except Exception:
                # Failed to update pyproject.toml, but VERSION is updated
                pass

    # For Python packages, also update __init__.py __version__
    src_dir = root / "src"
    if src_dir.exists():
        for init_file in src_dir.rglob("__init__.py"):
            try:
                content = init_file.read_text()
                # Replace __version__ = "X.Y.Z" or __version__ = 'X.Y.Z'
                new_content = re.sub(
                    r'(__version__\s*=\s*["\'])[^"\']+(["\'])',
                    f'\\1{version}\\2',
                    content
                )
                if new_content != content:
                    init_file.write_text(new_content)
            except Exception:
                # Failed to update this __init__.py, continue
                continue


def check_semantic_release() -> bool:
    """Check if semantic-release is available and configured."""
    try:
        result = subprocess.run(
            ["semantic-release", "--help"],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def run_semantic_release(logger, root: Path, dry_run: bool = False) -> bool:
    """
    Run semantic-release to create a new version.

    Flow:
    1. Get next version using semantic-release version --print
    2. Update VERSION file BEFORE running semantic-release
    3. Commit VERSION file (doesn't trigger new version)
    4. Run semantic-release to create tag and release

    Returns True if a new version was created.
    """
    # Check if we're in CI or if release is explicitly requested
    is_ci = os.environ.get("CI") == "true"
    is_release_branch = False

    try:
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()
        is_release_branch = current_branch in ["main", "master"]
    except Exception:
        pass

    if not is_ci and not os.environ.get("FORCE_RELEASE"):
        logger.info("Not in CI and FORCE_RELEASE not set, skipping release")
        return False

    if not is_release_branch and not os.environ.get("FORCE_RELEASE"):
        logger.info(f"Not on release branch (current: {current_branch}), skipping release")
        return False

    # Get current version for logging
    old_version = get_current_version(root)
    logger.info(f"Current version: {old_version or 'none'}")

    if dry_run:
        logger.info("Dry run mode - would run semantic-release now")
        return True

    # Run semantic-release - it handles EVERYTHING:
    # 1. Analyzes commits to determine next version
    # 2. Updates CHANGELOG.md
    # 3. Runs prepareCmd which:
    #    - Writes VERSION file: echo '${nextRelease.version}' > VERSION
    #    - Updates pyproject.toml and __init__.py via sync script
    #    - Builds package
    # 4. Creates ONE commit with all changes: VERSION + CHANGELOG.md + pyproject.toml + __init__.py
    # 5. Creates git tag
    #
    # NO chicken-and-egg problem because semantic-release knows the version
    # before running prepareCmd, so it can update VERSION correctly.
    logger.info("Running semantic-release (handles VERSION, CHANGELOG, tag, build)")
    logger.info("See .releaserc.json for full workflow")
    result = subprocess.run(
        ["semantic-release"],
        capture_output=False,
        text=True,
        check=False,
        env={**os.environ, "CI": "true"}
    )

    if result.returncode != 0:
        if result.returncode == 2:
            logger.info("No release created by semantic-release")
            return False
        else:
            logger.error(f"semantic-release failed with code {result.returncode}")
            return False

    # Get the version that was just released
    new_version = get_current_version(root)
    logger.info(f"Release {new_version} completed successfully")

    # Push to remote if CI_PUSH is set
    if os.environ.get("CI_PUSH") == "1":
        logger.info("Pushing changes and tags to remote...")
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()

            # Push commits and tags
            subprocess.run(["git", "push", "origin", current_branch], check=True)
            subprocess.run(["git", "push", "origin", "--tags"], check=True)
            logger.info(f"✓ Pushed to origin/{current_branch} with tags")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to push: {e}")
            logger.info("You may need to push manually: git push origin main --tags")
            return False

    return True


def sync_version_file(logger, root: Path) -> bool:
    """
    Ensure VERSION file is synced with git tag.

    This runs on every CI execution to keep VERSION file up-to-date,
    even if no release is triggered.

    Returns True if VERSION was updated.
    """
    tag_version = get_current_version(root)
    if not tag_version:
        logger.info("No git tags found, skipping VERSION sync")
        return False

    version_file = root / "VERSION"
    file_version = None

    if version_file.exists():
        file_version = version_file.read_text().strip()

    if file_version == tag_version:
        logger.info(f"VERSION file already synced: {tag_version}")
        return False

    # Update VERSION file
    logger.info(f"Syncing VERSION file: {file_version} -> {tag_version}")
    update_version_file(tag_version, root)
    return True


def main() -> int:
    """Main entry point."""
    logger = get_logger("semantic-release")

    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|release|sync]", sys.argv[0])
        return 1

    action = sys.argv[1]
    root = Path(__file__).resolve().parent.parent.parent

    if action == "check":
        if not check_semantic_release():
            logger.error("semantic-release not found. Install with: npm install -g semantic-release")
            return 1

        # Check for pyproject.toml or package.json config
        has_config = False
        if (root / "pyproject.toml").exists():
            with open(root / "pyproject.toml") as f:
                if "[tool.semantic_release]" in f.read():
                    has_config = True
        elif (root / "package.json").exists():
            with open(root / "package.json") as f:
                if '"semantic-release"' in f.read():
                    has_config = True
        elif (root / ".releaserc").exists():
            has_config = True

        if not has_config:
            logger.warning("No semantic-release configuration found")
            logger.info("Add [tool.semantic_release] to pyproject.toml or create .releaserc")
        else:
            logger.info("semantic-release is configured and ready")

        # Always sync VERSION file on check
        sync_version_file(logger, root)

        return 0
    
    elif action == "install":
        # Installation handled by bootstrap
        logger.info("semantic-release installation is handled by bootstrap")
        return 0
    
    elif action == "sync":
        # Sync VERSION file with git tag (non-release mode)
        if sync_version_file(logger, root):
            logger.info("VERSION file synced successfully")
        return 0

    elif action == "release":
        if not check_semantic_release():
            logger.error("semantic-release not found")
            return 1

        # Run release process
        dry_run = "--dry-run" in sys.argv
        if run_semantic_release(logger, root, dry_run):
            logger.info("Release completed successfully")

            # Ensure VERSION file is committed
            version_file = root / "VERSION"
            if version_file.exists():
                current_version = version_file.read_text().strip()
                logger.info(f"VERSION file contains: {current_version}")

        return 0

    else:
        logger.error("Unknown action: %s", action)
        return 1


if __name__ == "__main__":
    sys.exit(main())
