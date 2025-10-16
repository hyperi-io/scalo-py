#!/usr/bin/env python3
"""
Check for git system dependency.

This script verifies that git is available on the system.
Git is required for version control operations in CI.
"""
import shutil
import subprocess
import sys


def check_git() -> bool:
    """Check if git is available."""
    git_path = shutil.which("git")
    if git_path:
        # Get git version
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.strip()
            print(f"[OK] git found: {version}")
            return True
        except subprocess.CalledProcessError:
            print("[ERR] git found but --version failed", file=sys.stderr)
            return False
    else:
        print("[ERR] git not found in PATH", file=sys.stderr)
        return False


def install_git() -> bool:
    """
    Install git (intentionally not implemented).

    Git installation is environment-specific and should be done manually.
    If git is already available, return True (nothing to install).
    """
    # Check if git is already available
    if shutil.which("git"):
        return True  # Already installed, nothing to do

    print("[INFO] Git installation must be done manually for your environment")
    print("[INFO] - Debian/Ubuntu: sudo apt install git")
    print("[INFO] - Fedora: sudo dnf install git")
    print("[INFO] - macOS: brew install git")
    return False


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [check|install]", file=sys.stderr)
        return 1

    action = sys.argv[1]

    if action == "check":
        return 0 if check_git() else 1
    elif action == "install":
        return 0 if install_git() else 1
    else:
        print(f"[ERR] Unknown action: {action} (expected: check|install)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
