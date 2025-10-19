"""
CI Local Library Extensions

Project-specific extensions to ci_lib (which is in the read-only ci/ submodule).
These functions are used by ci-local/ scripts.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Import base ci_lib
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ci" / "common"))
    from ci_lib import logger
except ImportError:
    class SimpleLogger:
        def info(self, msg, *args): print(f"INFO: {msg % args if args else msg}")
        def warning(self, msg, *args): print(f"WARNING: {msg % args if args else msg}")
        def error(self, msg, *args): print(f"ERROR: {msg % args if args else msg}")
    logger = SimpleLogger()


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parent.parent.parent


def get_version_from_file(root: Optional[Path] = None) -> str:
    """Get current version from VERSION file (with validation)."""
    if root is None:
        root = get_project_root()

    version_file = root / "VERSION"
    if not version_file.exists():
        return ""

    version = version_file.read_text().strip()

    # Check for template corruption
    if "{version}" in version or not version:
        return ""

    return version


def is_valid_version(version: str) -> bool:
    """Check if a version string is valid semver format."""
    return bool(re.match(r'^\d+\.\d+\.\d+', version))


def get_next_semantic_version(root: Optional[Path] = None) -> str:
    """Get next version from semantic-release dry-run."""
    if root is None:
        root = get_project_root()

    try:
        result = subprocess.run(
            [sys.executable, "-m", "semantic_release", "version", "--print"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )

        if result.returncode != 0:
            return ""

        next_version = result.stdout.strip()

        if not is_valid_version(next_version):
            logger.warning(f"Invalid version from semantic-release: {next_version}")
            return ""

        return next_version

    except subprocess.TimeoutExpired:
        logger.error("semantic-release version --print timed out")
        return ""
    except Exception as e:
        logger.error(f"Failed to get next version: {e}")
        return ""


def check_semantic_release_available() -> bool:
    """Check if semantic-release is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "semantic_release", "--version"],
            capture_output=True,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False
