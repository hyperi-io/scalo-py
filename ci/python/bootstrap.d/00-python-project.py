#!/usr/bin/env python3
"""
Python Project Environment Bootstrap - Phase 0

This script sets up the project development environment (.venv):
1. Checks Python version meets project requirements (from ci/ci.yaml, default 3.11+)
2. Creates .venv if needed
3. Installs uv package manager into .venv
4. Installs project dependencies from /pyproject.toml using uv

This is for local development and testing ONLY (not CI).

Minimum Python version: Read from ci/ci.yaml (python.min_version, default: 3.11)
"""
import os
import subprocess
import sys
from pathlib import Path

# No imports from ci_lib yet - we're setting up the environment!

def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent

def get_min_python_version() -> tuple:
    """
    Get minimum Python version from ci/ci.yaml.

    Returns: (major, minor) tuple, defaults to (3, 11)
    """
    try:
        import yaml
        ci_yaml = get_project_root() / "ci" / "ci.yaml"
        if ci_yaml.exists():
            with open(ci_yaml) as f:
                config = yaml.safe_load(f)
                if config and 'python' in config and 'min_version' in config['python']:
                    version_str = str(config['python']['min_version'])
                    parts = version_str.split('.')
                    return (int(parts[0]), int(parts[1]))
    except:
        pass
    return (3, 11)  # Default

def check_python_version() -> bool:
    """Check if Python version meets project requirements."""
    min_version = get_min_python_version()
    version_info = sys.version_info
    current = (version_info.major, version_info.minor)

    if current >= min_version:
        version_str = f"Python {version_info.major}.{version_info.minor}.{version_info.micro}"
        print(f"[OK] {version_str} (>= {min_version[0]}.{min_version[1]} required for project)")
        return True
    else:
        current_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
        required_str = f"{min_version[0]}.{min_version[1]}"
        print(f"[ERR] Python {current_str} found, but {required_str}+ required", file=sys.stderr)
        print(f"      Project requires Python {required_str}+ (from ci/ci.yaml)", file=sys.stderr)
        return False

def check_action() -> int:
    """Check if project environment is set up."""
    project_root = get_project_root()
    project_venv = project_root / ".venv"
    project_python = project_venv / "bin" / "python"
    project_uv = project_venv / "bin" / "uv"

    # Check Python version
    if not check_python_version():
        return 1

    # Check if .venv exists
    if not project_venv.exists():
        print("[INFO] .venv not found (optional for CI, required for development)")
        print("       Create with: python -m venv .venv")
        return 0  # Not an error - .venv is optional

    # Check if uv is installed
    if not project_uv.exists():
        print("[INFO] uv not found in .venv")
        print("       Install with: .venv/bin/pip install uv")
        return 0  # Not an error - uv is optional

    print("[OK] Project environment ready (.venv with uv)")
    return 0

def install_action() -> int:
    """Set up project development environment (.venv)."""
    project_root = get_project_root()
    project_venv = project_root / ".venv"
    project_python = project_venv / "bin" / "python"
    project_uv = project_venv / "bin" / "uv"
    project_pyproject = project_root / "pyproject.toml"

    # Check Python version
    if not check_python_version():
        min_version = get_min_python_version()
        print(f"[ERR] Python {min_version[0]}.{min_version[1]}+ required")
        print("      Install via your system package manager")
        return 1

    # Create .venv if needed
    if not project_venv.exists():
        print("[INFO] Creating .venv for development...")
        subprocess.check_call([sys.executable, "-m", "venv", str(project_venv)])
        print("[OK] .venv created")
    else:
        print("[INFO] .venv already exists")

    # Install uv into .venv
    if not project_uv.exists():
        print("[INFO] Installing uv into .venv...")
        try:
            subprocess.check_call(
                [str(project_python), "-m", "pip", "install", "uv"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT
            )
            print("[OK] uv installed in .venv")
        except subprocess.CalledProcessError as e:
            print(f"[ERR] Failed to install uv: {e}", file=sys.stderr)
            return 1
    else:
        print("[INFO] uv already installed in .venv")

    # Install project dependencies from /pyproject.toml using uv
    if project_pyproject.exists():
        print("[INFO] Installing project dependencies from pyproject.toml...")
        try:
            subprocess.check_call(
                [
                    str(project_uv), "pip", "install",
                    "--python", str(project_python),
                    "-e", str(project_root),  # Install in editable mode
                ],
                cwd=project_root,
                stdout=subprocess.DEVNULL
            )
            print("[OK] Project dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"[WARN] Failed to install from pyproject.toml: {e}", file=sys.stderr)
            print("[INFO] Continuing anyway (dependencies may already be installed)")
    else:
        print("[WARN] pyproject.toml not found - skipping project dependencies")

    print("✓ Project environment setup complete")
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
