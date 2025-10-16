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
# Handle case where loguru is not yet installed (during bootstrap)
try:
    from loguru import logger as _loguru_logger

    # Remove default handler
    _loguru_logger.remove()

    # Add console handler with RFC 3339 timestamps (plain text, no colors/emojis for CI)
    _loguru_logger.add(
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
    logger = _loguru_logger
except ImportError:
    # Loguru not installed yet (bootstrap phase)
    # Create a simple logger replacement
    class SimpleLogger:
        """Simple logger for bootstrap phase (before loguru is installed)."""
        def info(self, msg, *args): print(f"[INFO] {msg % args if args else msg}")
        def warning(self, msg, *args): print(f"[WARN] {msg % args if args else msg}", file=sys.stderr)
        def error(self, msg, *args): print(f"[ERR] {msg % args if args else msg}", file=sys.stderr)
        def debug(self, msg, *args): pass  # Skip debug in bootstrap

    logger = SimpleLogger()


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
# Build Configuration (pyproject.toml + ENV overrides)
# ============================================================================

def get_build_config(key: str, default: any = None, env_prefix: str = "HYPERLIB_CI") -> any:
    """
    Get build configuration with precedence: ENV > ci/ci.yaml > default.

    Precedence order:
    1. Environment variable (highest priority)
    2. ci/ci.yaml configuration file
    3. Default value (lowest priority)

    Args:
        key: Configuration key with dot notation (e.g., 'nuitka.enabled')
        default: Default value if not found anywhere
        env_prefix: Environment variable prefix (default: HYPERLIB_CI)

    Returns:
        Configuration value with type preservation

    Example:
        # Check if Nuitka build is enabled
        enabled = get_build_config('nuitka.enabled', False)

        # Override via environment:
        # HYPERLIB_CI_NUITKA_ENABLED=true ./ci/ci build
    """
    # 1. Check environment variable (highest priority)
    # Convert dot notation to underscores: nuitka.enabled -> NUITKA_ENABLED
    env_key = f"{env_prefix}_{key.replace('.', '_').upper()}"
    env_value = os.environ.get(env_key)

    if env_value is not None:
        # Parse boolean strings
        if env_value.lower() in ('true', '1', 'yes', 'on'):
            return True
        elif env_value.lower() in ('false', '0', 'no', 'off'):
            return False
        # Return as-is for strings/numbers
        return env_value

    # 2. Check ci/ci.yaml
    try:
        import yaml

        ci_yaml_path = get_project_root() / "ci" / "ci.yaml"
        if ci_yaml_path.exists():
            with open(ci_yaml_path, 'r') as f:
                config = yaml.safe_load(f)

            # Navigate nested keys (e.g., 'nuitka.enabled' -> config['nuitka']['enabled'])
            value = config
            for part in key.split('.'):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    value = None
                    break

            if value is not None:
                return value
    except Exception as e:
        logger.warning(f"Failed to read ci/ci.yaml: {e}")

    # 3. Return default
    return default


def get_enabled_nuitka_platforms() -> list:
    """
    Get list of enabled Nuitka build platforms from config.

    Returns list of platform strings like: ['linux-x64', 'linux-arm64', 'macos-arm64']
    Only includes platforms explicitly enabled in ci/ci.yaml or via ENV vars.

    Returns:
        List of enabled platform identifiers
    """
    platforms = []

    if get_build_config('nuitka.platforms.linux_x64', True):
        platforms.append('linux-x64')

    if get_build_config('nuitka.platforms.linux_arm64', False):
        platforms.append('linux-arm64')

    if get_build_config('nuitka.platforms.macos_arm64', False):
        platforms.append('macos-arm64')

    return platforms


# ============================================================================
# System Dependency Hints
# ============================================================================

def print_system_dependency_hint(package_name: str, command_name: Optional[str] = None) -> None:
    """
    Print platform-specific installation hints for missing system dependencies.

    This is the standard way to notify users about missing system dependencies
    across all bootstrap scripts. Bootstrap should NEVER auto-install system
    packages - only provide clear guidance.

    Args:
        package_name: Human-readable name of the package (e.g., "C compiler", "Node.js")
        command_name: Optional command to check (e.g., "gcc", "node")

    Example:
        if not shutil.which("gcc"):
            print_system_dependency_hint("C compiler (gcc)", "gcc")
    """
    import platform

    system = platform.system()
    logger.error(f"System dependency not found: {package_name}")

    if command_name:
        logger.error(f"  Missing command: {command_name}")

    logger.error("")
    logger.error("Installation instructions:")

    if system == "Linux":
        try:
            with open("/etc/os-release") as f:
                os_release = f.read().lower()

            if "fedora" in os_release or "rhel" in os_release or "centos" in os_release:
                logger.error("  Fedora/RHEL: sudo dnf install <package>")
                if package_name.lower() == "c compiler" or "gcc" in package_name.lower():
                    logger.error("  Example: sudo dnf install gcc gcc-c++ python3-devel")
            elif "debian" in os_release or "ubuntu" in os_release:
                logger.error("  Debian/Ubuntu: sudo apt-get install <package>")
                if package_name.lower() == "c compiler" or "gcc" in package_name.lower():
                    logger.error("  Example: sudo apt-get install build-essential python3-dev")
            else:
                logger.error("  Use your distribution's package manager")
        except Exception:
            logger.error("  Use your distribution's package manager (dnf, apt, etc.)")

    elif system == "Darwin":
        logger.error("  macOS: Use Homebrew or system installers")
        if package_name.lower() == "c compiler" or "gcc" in package_name.lower() or "clang" in package_name.lower():
            logger.error("  Example: xcode-select --install")
        else:
            logger.error("  Example: brew install <package>")

    elif system == "Windows":
        logger.error("  Windows: Use system installers or package managers")
        if package_name.lower() == "c compiler":
            logger.error("  Example: Visual Studio Build Tools or MinGW")
    else:
        logger.error(f"  Platform: {system} (consult platform documentation)")

    logger.error("")


def get_platform_package_manager() -> str:
    """
    Detect the platform package manager.

    Returns:
        Package manager name (e.g., 'dnf', 'apt', 'brew', 'unknown')
    """
    import platform
    import shutil

    system = platform.system()

    if system == "Linux":
        if shutil.which("dnf"):
            return "dnf"
        elif shutil.which("apt-get"):
            return "apt-get"
        elif shutil.which("yum"):
            return "yum"
        elif shutil.which("pacman"):
            return "pacman"
        else:
            return "unknown"
    elif system == "Darwin":
        return "brew" if shutil.which("brew") else "unknown"
    elif system == "Windows":
        return "choco" if shutil.which("choco") else "unknown"
    else:
        return "unknown"


# ============================================================================
# Module Initialization
# ============================================================================

# Verify this module is being imported from .venv-ci
if __name__ != "__main__":
    # Only enforce when imported (not when running directly)
    venv_type = check_venv_type()
    if venv_type != 'ci':
        log_warning(f"ci_lib.py imported from {venv_type} environment (expected 'ci')")
