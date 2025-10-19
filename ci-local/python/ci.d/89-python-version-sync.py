#!/usr/bin/env python3
"""
Python Version Sync Extension (Python projects only)

Extends common version pre-sync with Python-specific version checks
for pyproject.toml and __init__.py files.
"""

import os
import sys
import subprocess
from pathlib import Path

# CRITICAL: Enforce ci-local/.venv usage
if "ci-local/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci-local/.venv")
    sys.exit(1)

# Import from ci_local_lib
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "common"))
    from ci_local_lib import logger, get_project_root, get_version_from_file
except ImportError as e:
    print(f"ERROR: ci_local_lib not found: {e}")
    sys.exit(1)


def get_version_from_pyproject(root: Path) -> str:
    """Get version from pyproject.toml (Python-specific)."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return ""

    import re
    content = pyproject.read_text()
    match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return match.group(1) if match else ""


def get_version_from_init_py(root: Path) -> str:
    """Get version from src/<package>/__init__.py (Python-specific)."""
    init_files = list(root.glob("src/*/__init__.py"))
    if not init_files:
        return ""

    import re
    content = init_files[0].read_text()
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else ""


def check_python_version_sync(root: Path) -> int:
    """Check if VERSION, pyproject.toml, and __init__.py are in sync."""
    versions = {
        "VERSION": get_version_from_file(root),
        "pyproject.toml": get_version_from_pyproject(root),
        "__init__.py": get_version_from_init_py(root)
    }

    # Remove empty values
    versions = {k: v for k, v in versions.items() if v}

    if not versions.get("VERSION"):
        logger.error("VERSION file is empty or corrupted")
        return 1

    # Check if all are the same
    if len(set(versions.values())) > 1:
        logger.error("Version mismatch across Python files:")
        for source, version in versions.items():
            logger.error(f"  {source}: {version}")
        return 1

    logger.info(f"✓ Python versions synced: {versions['VERSION']}")
    return 0


def delegate_to_common_pre_sync(root: Path) -> int:
    """Delegate to common version pre-sync script."""
    common_script = root / "ci-local" / "common" / "ci.d" / "89-version-pre-sync.py"

    if not common_script.exists():
        logger.warning("Common version pre-sync script not found")
        return check_python_version_sync(root)

    result = subprocess.run([sys.executable, str(common_script), "release"], cwd=root)
    return result.returncode


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|release]", sys.argv[0])
        return 1

    action = sys.argv[1]
    root = get_project_root()

    if action == "check":
        return check_python_version_sync(root)
    elif action == "install":
        logger.info("Python version sync requires no installation")
        return 0
    elif action == "release":
        return delegate_to_common_pre_sync(root)
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
