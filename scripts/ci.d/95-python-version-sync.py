#!/usr/bin/env python3
"""
Python Version Synchronization

Ensures VERSION file matches the version from git tags and Python package files.
This runs AFTER semantic-release to ensure consistency.

This script is Python-specific and handles:
- pyproject.toml version
- __init__.py __version__
- VERSION file
"""

import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

# CRITICAL: Enforce .venv-ci usage (FAIL HARD if not in .venv-ci)
if ".venv-ci" not in sys.prefix:
    print("ERROR: This script must run in .venv-ci")
    print(f"Current Python: {sys.executable}")
    print("Expected: .venv-ci/bin/python")
    print("Run via: ./scripts/ci check")
    sys.exit(1)

# Add parent dir to path for hyperlib
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hyperlib import get_logger  # type: ignore

try:
    import tomli
except ImportError:
    import tomllib as tomli

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore


def get_git_version() -> Optional[str]:
    """Get current version from git tags."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            # Remove 'v' prefix if present
            if version.startswith('v'):
                version = version[1:]
            return version
    except Exception:
        pass
    return None


def get_pyproject_version(root: Path) -> Optional[str]:
    """Get version from pyproject.toml."""
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    
    try:
        with open(pyproject_path, "rb") as f:
            data = tomli.load(f)
        
        # Check project.version
        if "project" in data and "version" in data["project"]:
            return data["project"]["version"]
        
        # Check tool.poetry.version (if using Poetry)
        if "tool" in data and "poetry" in data["tool"] and "version" in data["tool"]["poetry"]:
            return data["tool"]["poetry"]["version"]
    except Exception:
        pass
    
    return None


def get_init_version(root: Path) -> Optional[str]:
    """Get __version__ from Python package __init__.py."""
    # Try to find package directory
    src_dir = root / "src"
    if not src_dir.exists():
        src_dir = root
    
    # Look for __init__.py files
    for init_file in src_dir.rglob("__init__.py"):
        try:
            content = init_file.read_text()
            # Look for __version__ = "X.Y.Z" or __version__ = 'X.Y.Z'
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        except Exception:
            continue
    
    return None


def get_version_file_content(root: Path) -> Optional[str]:
    """Get content of VERSION file."""
    version_file = root / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return None


def update_version_file(root: Path, version: str) -> bool:
    """Update VERSION file with the given version."""
    version_file = root / "VERSION"
    try:
        version_file.write_text(f"{version}\n")
        return True
    except Exception as e:
        return False


def update_pyproject_version(root: Path, version: str) -> bool:
    """Update version in pyproject.toml."""
    if not tomli_w:
        return False
    
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return False
    
    try:
        # Read existing content
        with open(pyproject_path, "rb") as f:
            data = tomli.load(f)
        
        # Update version
        if "project" in data:
            data["project"]["version"] = version
        
        if "tool" in data and "poetry" in data["tool"]:
            data["tool"]["poetry"]["version"] = version
        
        # Write back
        with open(pyproject_path, "wb") as f:
            tomli_w.dump(data, f)
        
        return True
    except Exception:
        return False


def update_init_version(root: Path, version: str) -> bool:
    """Update __version__ in __init__.py files."""
    updated = False
    
    # Try to find package directory
    src_dir = root / "src"
    if not src_dir.exists():
        src_dir = root
    
    # Update all __init__.py files with __version__
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
                updated = True
        except Exception:
            continue
    
    return updated


def check_action(logger, root: Path) -> int:
    """Check if all versions are in sync."""
    git_version = get_git_version()
    pyproject_version = get_pyproject_version(root)
    init_version = get_init_version(root)
    version_file = get_version_file_content(root)
    
    logger.info("Version check:")
    logger.info(f"  Git tag:        {git_version or 'none'}")
    logger.info(f"  pyproject.toml: {pyproject_version or 'none'}")
    logger.info(f"  __init__.py:    {init_version or 'none'}")
    logger.info(f"  VERSION file:   {version_file or 'none'}")
    
    # Git version is source of truth
    if not git_version:
        logger.warning("No git tags found. Run semantic-release or tag manually.")
        return 0  # Don't fail CI for new projects
    
    all_match = True
    
    if pyproject_version and pyproject_version != git_version:
        logger.error(f"pyproject.toml version ({pyproject_version}) doesn't match git ({git_version})")
        all_match = False
    
    if init_version and init_version != git_version:
        logger.error(f"__init__.py version ({init_version}) doesn't match git ({git_version})")
        all_match = False
    
    if version_file and version_file != git_version:
        logger.error(f"VERSION file ({version_file}) doesn't match git ({git_version})")
        all_match = False
    
    if not version_file:
        logger.error("VERSION file is missing")
        all_match = False
    
    if all_match:
        logger.info("✓ All versions are in sync")
        return 0
    else:
        logger.error("✗ Version mismatch detected. Run with 'sync' to fix.")
        return 1


def sync_action(logger, root: Path) -> int:
    """Synchronize all versions to match git tag."""
    git_version = get_git_version()
    
    if not git_version:
        logger.error("No git tags found. Cannot sync without a version.")
        logger.info("Create an initial tag: git tag v0.1.0")
        return 1
    
    logger.info(f"Syncing all versions to: {git_version}")
    
    # Update VERSION file (required)
    if update_version_file(root, git_version):
        logger.info("✓ Updated VERSION file")
    else:
        logger.error("✗ Failed to update VERSION file")
        return 1
    
    # Update pyproject.toml (if exists)
    if (root / "pyproject.toml").exists():
        if update_pyproject_version(root, git_version):
            logger.info("✓ Updated pyproject.toml")
        else:
            logger.warning("⚠ Could not update pyproject.toml (tomli_w not available)")
    
    # Update __init__.py (if found)
    if update_init_version(root, git_version):
        logger.info("✓ Updated __init__.py files")
    
    # Stage changes for commit if in git repo
    try:
        subprocess.run(["git", "add", "VERSION"], check=False)
        subprocess.run(["git", "add", "pyproject.toml"], check=False)
        subprocess.run(["git", "add", "-u", "src/"], check=False)  # Update tracked files in src/
        logger.info("✓ Staged version changes for commit")
    except Exception:
        pass
    
    return 0


def sync_to_version(logger, root: Path, version: str) -> int:
    """
    Synchronize all version files to a specific version.

    Used by semantic-release to update VERSION, pyproject.toml, and __init__.py
    to the version it calculated from commits.

    Args:
        logger: Logger instance
        root: Project root path
        version: Version string (e.g., '1.6.1')

    Returns:
        0 on success, 1 on failure
    """
    logger.info(f"Syncing all versions to: {version}")

    # Update pyproject.toml (if exists)
    if (root / "pyproject.toml").exists():
        if update_pyproject_version(root, version):
            logger.info("✓ Updated pyproject.toml")
        else:
            logger.warning("⚠ Could not update pyproject.toml (tomli_w not available)")

    # Update __init__.py (if found)
    if update_init_version(root, version):
        logger.info("✓ Updated __init__.py files")

    return 0


def main() -> int:
    """Main entry point."""
    logger = get_logger("python-version-sync")

    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|sync|sync <version>]", sys.argv[0])
        return 1

    action = sys.argv[1]
    root = Path(__file__).resolve().parent.parent.parent

    if action == "check":
        return check_action(logger, root)

    elif action == "install":
        # No installation needed
        logger.info("No installation required for version sync")
        return 0

    elif action == "sync":
        # If version provided as argument, use it (for semantic-release)
        if len(sys.argv) >= 3:
            version = sys.argv[2]
            return sync_to_version(logger, root, version)
        else:
            # Otherwise sync to git tag version (for manual use)
            return sync_action(logger, root)

    else:
        logger.error("Unknown action: %s", action)
        return 1


if __name__ == "__main__":
    sys.exit(main())
