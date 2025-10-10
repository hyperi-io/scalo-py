#!/usr/bin/env python3
"""
Shared CI/Bootstrap Utilities Library

This module provides common functions for all CI and bootstrap scripts.
MUST be imported from ci/.venv Python only.

Usage:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "python"))
    from ci_lib import get_logger, enforce_venv_ci, get_project_root, run_command

    logger = get_logger(__name__)

Subprocess Usage Policy:
=======================
This library uses subprocess for external tool invocations where appropriate.
We intentionally use subprocess rather than Python wrappers in these cases:

1. **git** - Standard CLI tool, available everywhere
   - Libraries like GitPython wrap subprocess internally anyway
   - Direct subprocess is more transparent and debuggable
   - Consolidated via helpers: get_current_branch(), get_git_root(), get_latest_tag()

2. **Build tools** (python -m build, twine) - Use Python modules directly
   - These are true Python libraries, no subprocess needed
   - Already using: python -m build, python -m twine

3. **System commands** - Use subprocess when needed
   - Examples: bash scripts during bootstrap
   - Better than trying to reimplement shell logic in Python

Philosophy: Use native Python where it makes sense (build, twine, requests),
use subprocess for external tools that are standard parts of the environment (git).
"""
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any


# ============================================================================
# Virtual Environment Protection
# ============================================================================

def enforce_venv_ci(script_name: Optional[str] = None) -> None:
    """
    Enforce ci/.venv usage - FAIL HARD if not in correct venv.

    This is Layer 3 of the venv protection strategy.
    Call this at the TOP of every CI/bootstrap script.

    Args:
        script_name: Name of the calling script (for error messages)

    Raises:
        SystemExit: If not running in ci/.venv
    """
    script_name = script_name or Path(sys.argv[0]).name

    # Check 1: Python prefix contains ci/.venv
    if "ci/.venv" not in sys.prefix and "ci" not in sys.prefix:
        print(f"ERROR: {script_name} must run in ci/.venv", file=sys.stderr)
        print(f"Current Python: {sys.executable}", file=sys.stderr)
        print(f"Current prefix: {sys.prefix}", file=sys.stderr)
        print("Expected: ci/.venv/bin/python", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run via: ./ci/run <action>", file=sys.stderr)
        sys.exit(1)

    # Check 2: Environment variable verification (Layer 2)
    venv_purpose = os.environ.get("VENV_PURPOSE")
    if venv_purpose and venv_purpose != "ci":
        print(f"WARNING: VENV_PURPOSE={venv_purpose} (expected 'ci')", file=sys.stderr)
        print("This may indicate wrong virtual environment", file=sys.stderr)

    # Check 3: Marker file verification (Layer 1)
    venv_ci_marker = Path(sys.prefix) / ".THIS_IS_CI_VENV"
    if not venv_ci_marker.exists():
        print(f"WARNING: .THIS_IS_CI_VENV marker not found in {sys.prefix}", file=sys.stderr)
        print("Run: ./ci/bootstrap --install to recreate ci/.venv", file=sys.stderr)


def check_venv_type() -> str:
    """
    Determine which venv is active (if any).

    Returns:
        'ci' if ci/.venv, 'dev' if .venv, 'system' if no venv, 'unknown' otherwise
    """
    if not (hasattr(sys, 'real_prefix') or
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
        return 'system'

    if 'ci/.venv' in sys.prefix or ('ci' in sys.prefix and '.venv' in sys.prefix):
        return 'ci'
    elif '.venv' in sys.prefix and 'ci' not in sys.prefix:
        return 'dev'
    else:
        return 'unknown'


def create_venv_markers(venv_path: Path, venv_type: str) -> None:
    """
    Create marker files in venv to identify its purpose.

    Args:
        venv_path: Path to virtual environment
        venv_type: 'ci' or 'dev'
    """
    if venv_type == 'ci':
        marker = venv_path / ".THIS_IS_CI_VENV"
        marker.write_text(
            "This is the CI/automation virtual environment (ci/.venv)\n"
            "DO NOT use for development!\n"
            "Created by: ./ci/bootstrap\n"
        )
    elif venv_type == 'dev':
        marker = venv_path / ".THIS_IS_DEV_VENV"
        marker.write_text(
            "This is the development virtual environment (.venv)\n"
            "DO NOT use for CI/automation!\n"
            "Created manually for local development\n"
        )


def patch_venv_activation(venv_path: Path, venv_type: str) -> None:
    """
    Add environment variables to venv activation scripts.

    Args:
        venv_path: Path to virtual environment
        venv_type: 'ci' or 'dev'
    """
    activate_script = venv_path / "bin" / "activate"

    if not activate_script.exists():
        return

    # Check if already patched
    content = activate_script.read_text()
    if "VENV_PURPOSE" in content:
        return  # Already patched

    # Add environment variables before deactivate function
    env_vars = f"""
# Virtual environment identification (added by ci_lib.py)
export VENV_PURPOSE="{venv_type}"
export VENV_TYPE="{'automation' if venv_type == 'ci' else 'development'}"
"""

    # Insert after the initial PS1 setup
    lines = content.split('\n')
    insert_pos = None
    for i, line in enumerate(lines):
        if 'PS1=' in line or 'deactivate ()' in line:
            insert_pos = i
            break

    if insert_pos:
        lines.insert(insert_pos, env_vars)
        activate_script.write_text('\n'.join(lines))


# ============================================================================
# Path Utilities
# ============================================================================

def get_project_root() -> Path:
    """
    Get the project root directory.

    Walks up from current file until finding .git directory.

    Returns:
        Path to project root
    """
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # Fallback: assume ci/ is one level below root
    return Path(__file__).resolve().parent.parent


def get_venv_ci_python() -> Path:
    """
    Get path to ci/.venv Python interpreter.

    Returns:
        Path to ci/.venv/bin/python

    Raises:
        FileNotFoundError: If ci/.venv not found
    """
    venv_python = get_project_root() / "ci" / ".venv" / "bin" / "python"
    if not venv_python.exists():
        raise FileNotFoundError(
            "ci/.venv not found!\n"
            "Run: ./ci/bootstrap --install"
        )
    return venv_python


# ============================================================================
# Command Execution
# ============================================================================

def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a command with consistent error handling.

    Args:
        cmd: Command and arguments as list
        cwd: Working directory (defaults to project root)
        env: Environment variables (merged with os.environ)
        check: Raise exception on non-zero exit
        capture_output: Capture stdout/stderr

    Returns:
        CompletedProcess result
    """
    if cwd is None:
        cwd = get_project_root()

    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    else:
        full_env = None

    return subprocess.run(
        cmd,
        cwd=cwd,
        env=full_env,
        check=check,
        capture_output=capture_output,
        text=True if capture_output else False,
    )


# ============================================================================
# Logging Utilities (Loguru with RFC 3339 timestamps)
# ============================================================================

# Configure module-level logger with RFC 3339 timestamps (plain text for CI)
from loguru import logger

# Remove default handler
logger.remove()

# Add console handler with RFC 3339 timestamps (plain text, no colors/emojis for CI)
logger.add(
    sys.stderr,
    format=(
        "{time:YYYY-MM-DDTHH:mm:ss.SSSZZ} | "
        "{level: <8} | "
        "{name}:{function}:{line} - "
        "{message}"
    ),
    colorize=False,
    level="INFO",
)


def get_logger(name: Optional[str] = None):
    """
    Get logger instance (returns module-level logger).

    Kept for backward compatibility. Just use 'from ci_lib import logger' instead.

    Args:
        name: Logger name (ignored, for compatibility)

    Returns:
        Loguru logger instance
    """
    return logger


def log_info(message: str) -> None:
    """Print info message to stdout."""
    print(f"[INFO] {message}")


def log_warning(message: str) -> None:
    """Print warning message to stderr."""
    print(f"[WARN] {message}", file=sys.stderr)


def log_error(message: str) -> None:
    """Print error message to stderr."""
    print(f"[ERROR] {message}", file=sys.stderr)


def log_success(message: str) -> None:
    """Print success message to stdout."""
    print(f"[OK] {message}")


# ============================================================================
# Git Utilities (via subprocess - git is standard tool)
# ============================================================================
# NOTE: We use subprocess for git operations rather than GitPython because:
# - git is a standard tool available everywhere
# - GitPython wraps subprocess internally anyway
# - Direct subprocess is more transparent and debuggable
# - Fewer dependencies, simpler CI environment
# ============================================================================

def get_current_branch() -> str:
    """
    Get current git branch name.

    Returns:
        Branch name (e.g., 'main')

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = run_command(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def get_git_root() -> Path:
    """
    Get git repository root.

    Returns:
        Path to git root

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = run_command(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=True,
    )
    return Path(result.stdout.strip())


def get_latest_tag() -> Optional[str]:
    """
    Get latest git tag.

    Returns:
        Latest tag or None if no tags exist
    """
    result = run_command(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


# ============================================================================
# Version Management
# ============================================================================

def read_version_file() -> str:
    """
    Read VERSION file from project root.

    Returns:
        Version string (e.g., '1.6.0')
    """
    version_file = get_project_root() / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "0.0.0"


def write_version_file(version: str) -> None:
    """
    Write version to VERSION file.

    Args:
        version: Version string (e.g., '1.6.0')
    """
    version_file = get_project_root() / "VERSION"
    version_file.write_text(f"{version}\n")


# ============================================================================
# Module Initialization
# ============================================================================

# Verify this module is being imported from .venv-ci
if __name__ != "__main__":
    # Only enforce when imported (not when running directly)
    venv_type = check_venv_type()
    if venv_type != 'ci':
        log_warning(f"ci_lib.py imported from {venv_type} environment (expected 'ci')")
