#!/usr/bin/env python3
"""
Check Python version and availability.

This script verifies that Python 3.11+ is available.
Since it runs from within the venv, it validates the venv Python.
"""
import sys


def check_python() -> bool:
    """Check if Python version meets minimum requirements."""
    version_info = sys.version_info
    min_version = (3, 11)

    if version_info >= min_version:
        version_str = f"Python {version_info.major}.{version_info.minor}.{version_info.micro}"
        print(f"[OK] Python available: {version_str}")
        return True
    else:
        current = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
        required = f"{min_version[0]}.{min_version[1]}"
        print(f"[ERR] Python {current} found, but {required}+ required", file=sys.stderr)
        print(f"      Install Python {required}+ via your system package manager", file=sys.stderr)
        return False


def install_python() -> bool:
    """
    Install Python (intentionally not implemented).

    Python installation is environment-specific and should be done manually.
    If Python 3.11+ is already available, return True (nothing to install).
    """
    # Check if Python is already adequate
    if check_python():
        return True  # Already have Python 3.11+, nothing to do

    print("[INFO] Python installation must be done manually for your environment")
    print("[INFO] - Debian/Ubuntu: sudo apt install python3.11")
    print("[INFO] - Fedora: sudo dnf install python3.11")
    print("[INFO] - macOS: brew install python@3.11")
    return False


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [check|install]", file=sys.stderr)
        return 1

    action = sys.argv[1]

    if action == "check":
        return 0 if check_python() else 1
    elif action == "install":
        return 0 if install_python() else 1
    else:
        print(f"[ERR] Unknown action: {action} (expected: check|install)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
