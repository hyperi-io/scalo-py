#!/usr/bin/env python3
"""
Check for uv package manager.

This script verifies that uv is available in .venv (preferred) or system PATH.
uv is a fast Python package installer (optional but recommended).
"""
import shutil
import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory."""
    # This script is in ci/python/bootstrap.d/, so go up 3 levels
    return Path(__file__).resolve().parent.parent.parent.parent


def check_uv() -> bool:
    """Check if uv is available in .venv or system PATH."""
    project_root = get_project_root()
    venv_uv = project_root / ".venv" / "bin" / "uv"

    # Check .venv first (preferred)
    if venv_uv.exists():
        try:
            result = subprocess.run(
                [str(venv_uv), "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.strip()
            print(f"[OK] uv found in .venv: {version}")
            return True
        except subprocess.CalledProcessError:
            print("[ERR] uv found in .venv but --version failed", file=sys.stderr)
            return False

    # Fallback to system PATH
    uv_path = shutil.which("uv")
    if uv_path:
        try:
            result = subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.strip()
            print(f"[OK] uv found (system): {version}")
            return True
        except subprocess.CalledProcessError:
            print("[ERR] uv found but --version failed", file=sys.stderr)
            return False

    print("[ERR] uv not found in .venv or system PATH", file=sys.stderr)
    print("      Install in .venv: pip install uv", file=sys.stderr)
    print("      OR system-wide: curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
    return False


def install_uv() -> bool:
    """
    Install uv into .venv if not already available.

    Returns True if uv is available (either already installed or successfully installed).
    """
    project_root = get_project_root()
    venv_uv = project_root / ".venv" / "bin" / "uv"

    # Check if already available
    if venv_uv.exists() or shutil.which("uv"):
        return True  # Already available

    # Try to install into .venv
    venv_python = project_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        print("[INFO] .venv not found - uv installation skipped")
        print("[INFO] Create .venv first: python -m venv .venv")
        return False

    print("[INFO] Installing uv into .venv...")
    try:
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "uv"],
            check=True,
            capture_output=True
        )
        print("[OK] uv installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERR] Failed to install uv: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [check|install]", file=sys.stderr)
        return 1

    action = sys.argv[1]

    if action == "check":
        return 0 if check_uv() else 1
    elif action == "install":
        return 0 if install_uv() else 1
    else:
        print(f"[ERR] Unknown action: {action} (expected: check|install)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
