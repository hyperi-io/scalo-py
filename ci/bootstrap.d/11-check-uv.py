#!/usr/bin/env python3
"""
Check for uv package manager.

This script verifies that uv is available on the system.
uv is a fast Python package installer (optional but recommended).
"""
import shutil
import subprocess
import sys


def check_uv() -> bool:
    """Check if uv is available."""
    uv_path = shutil.which("uv")
    if uv_path:
        # Get uv version
        try:
            result = subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.strip()
            print(f"[OK] uv found: {version}")
            return True
        except subprocess.CalledProcessError:
            print("[ERR] uv found but --version failed", file=sys.stderr)
            return False
    else:
        print("[ERR] uv not found in PATH", file=sys.stderr)
        print("      Install: curl -LsSf https://astral.sh/uv/install.sh | sh", file=sys.stderr)
        return False


def install_uv() -> bool:
    """
    Install uv (intentionally not implemented).

    uv installation is best done manually via the official installer.
    """
    print("[INFO] uv installation must be done manually")
    print("[INFO] Run: curl -LsSf https://astral.sh/uv/install.sh | sh")
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
