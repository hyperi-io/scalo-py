#!/usr/bin/env python3
"""
Python CI Environment Bootstrap - Phase 0

This script sets up the CI environment (ci/.venv):
1. Checks Python version is sufficient for CI tools (3.9+ recommended)
2. Creates ci/.venv if needed
3. Installs uv package manager into ci/.venv
4. Installs CI tools from ci/pyproject.toml using uv

This runs BEFORE other bootstrap scripts and sets up the foundation.

Minimum Python version: 3.9 (sufficient for CI tools like loguru, pytest, ruff, etc.)
"""
import os
import subprocess
import sys
from pathlib import Path

# No imports from ci_lib here - we're setting up the environment that ci_lib needs!

def get_ci_dir() -> Path:
    """Get CI directory (ci/)."""
    return Path(__file__).resolve().parent.parent.parent  # ci/common/bootstrap.d/ -> ci/

def get_project_root() -> Path:
    """Get project root directory."""
    return get_ci_dir().parent

def check_python_version(min_version: tuple = (3, 9)) -> bool:
    """Check if Python version meets minimum requirements for CI tools."""
    version_info = sys.version_info
    current = (version_info.major, version_info.minor)

    if current >= min_version:
        version_str = f"Python {version_info.major}.{version_info.minor}.{version_info.micro}"
        print(f"[OK] {version_str} (>= {min_version[0]}.{min_version[1]} required for CI)")
        return True
    else:
        current_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
        required_str = f"{min_version[0]}.{min_version[1]}"
        print(f"[ERR] Python {current_str} found, but {required_str}+ required for CI tools", file=sys.stderr)
        print(f"      CI tools (loguru, pytest, uv) need Python {required_str}+", file=sys.stderr)
        return False

def check_action() -> int:
    """Check if CI environment is set up."""
    ci_dir = get_ci_dir()
    ci_venv = ci_dir / ".venv"
    ci_python = ci_venv / "bin" / "python"
    ci_uv = ci_venv / "bin" / "uv"

    # Check Python version
    if not check_python_version(min_version=(3, 9)):
        return 1

    # Check if ci/.venv exists
    if not ci_venv.exists():
        print("[ERR] ci/.venv not found")
        print("      Run: ./ci/bootstrap --install")
        return 1

    # Check if uv is installed
    if not ci_uv.exists():
        print("[ERR] uv not found in ci/.venv")
        print("      Run: ./ci/bootstrap --install")
        return 1

    print("[OK] CI environment ready (ci/.venv with uv)")
    return 0

def install_action() -> int:
    """Set up CI environment (ci/.venv)."""
    ci_dir = get_ci_dir()
    project_root = get_project_root()
    ci_venv = ci_dir / ".venv"
    ci_python = ci_venv / "bin" / "python"
    ci_uv = ci_venv / "bin" / "uv"
    ci_pyproject = ci_dir / "pyproject.toml"

    # Check Python version
    if not check_python_version(min_version=(3, 9)):
        print("[ERR] Python version insufficient for CI tools")
        print("      Install Python 3.9+ via your system package manager")
        return 1

    # Create ci/.venv if needed (should already exist from bootstrap.py Phase 0)
    if not ci_venv.exists():
        print("[INFO] Creating ci/.venv...")
        subprocess.check_call([sys.executable, "-m", "venv", str(ci_venv)])
        print("[OK] ci/.venv created")
    else:
        print("[INFO] ci/.venv already exists")

    # Install uv into ci/.venv
    if not ci_uv.exists():
        print("[INFO] Installing uv into ci/.venv...")
        try:
            subprocess.check_call(
                [str(ci_python), "-m", "pip", "install", "uv"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            print("[OK] uv installed in ci/.venv")
        except subprocess.CalledProcessError as e:
            print(f"[ERR] Failed to install uv: {e}", file=sys.stderr)
            return 1
    else:
        print("[INFO] uv already installed in ci/.venv")

    # Install CI tools from ci/pyproject.toml using uv
    if ci_pyproject.exists():
        print("[INFO] Installing CI tools from ci/pyproject.toml...")
        try:
            subprocess.check_call(
                [
                    str(ci_uv), "pip", "install",
                    "--python", str(ci_python),
                    "-e", str(ci_dir),  # Install ci/pyproject.toml dependencies
                ],
                cwd=ci_dir,
                stdout=subprocess.DEVNULL
            )
            print("[OK] CI tools installed from ci/pyproject.toml")
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Failed to install from ci/pyproject.toml: {e}", file=sys.stderr)
            print("[INFO] Continuing anyway (tools may already be installed)")
    else:
        print("[INFO] ci/pyproject.toml not found - skipping CI tools install")

    print("✓ CI environment setup complete")
    return 0

def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [check|install]", file=sys.stderr)
        return 1

    action = sys.argv[1]

    if action == "check":
        return check_action()
    elif action == "install":
        return install_action()
    else:
        print(f"[ERR] Unknown action: {action}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
