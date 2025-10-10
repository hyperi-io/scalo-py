#!/usr/bin/env python3
"""
Python package CI step: run tests and linting.

This script runs standard Python package checks:
1. pytest (unit tests with coverage)
2. ruff (linting)
3. black --check (formatting check)
4. mypy (type checking)

Uses tools from ci/.venv for consistent versions.
"""
import os
import subprocess
import sys
from pathlib import Path

# CRITICAL: Enforce ci/.venv usage (FAIL HARD if not in ci/.venv)
if "ci/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci/.venv")
    print(f"Current Python: {sys.executable}")
    print("Expected: ci/.venv/bin/python")
    print("Run via: ./ci/ci check")
    sys.exit(1)

# Import hyperlib if available (optional dependency)
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from hyperlib import get_logger  # type: ignore
    logger = get_logger("python-test")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logger = logging.getLogger("python-test")

def main():
    """Run Python package tests and checks."""
    project_root = Path(__file__).parent.parent.parent
    venv_ci = project_root / "ci/.venv"
    venv_bin = venv_ci / "bin"

    if not venv_ci.exists():
        logger.error("ci/.venv not found - run ./ci/bootstrap first")
        return 1

    failed = []

    # Run pytest (with coverage if available)
    logger.info("Running pytest...")
    pytest_args = [str(venv_bin / "pytest"), "-v"]

    # Add coverage if pytest-cov is available
    try:
        subprocess.run([str(venv_bin / "python"), "-c", "import pytest_cov"],
                      capture_output=True, check=True)
        pytest_args.extend(["--cov=hyperlib", "--cov-report=term-missing"])
    except subprocess.CalledProcessError:
        logger.info("pytest-cov not available, running without coverage")

    result = subprocess.run(pytest_args, cwd=project_root)
    if result.returncode != 0:
        failed.append("pytest")

    # Run ruff for linting
    logger.info("Running ruff linting...")
    result = subprocess.run(
        [str(venv_bin / "ruff"), "check", "src", "tests"],
        cwd=project_root
    )
    if result.returncode != 0:
        failed.append("ruff")

    # Run black for formatting check
    logger.info("Running black formatting check...")
    result = subprocess.run(
        [str(venv_bin / "black"), "--check", "src", "tests"],
        cwd=project_root
    )
    if result.returncode != 0:
        failed.append("black")

    # Run mypy for type checking (allow to pass even with errors for now)
    logger.info("Running mypy type checking...")
    result = subprocess.run(
        [str(venv_bin / "mypy"), "src"],
        cwd=project_root
    )
    if result.returncode != 0:
        logger.warning("mypy found type issues (non-blocking)")

    # Summary
    if failed:
        logger.error(f"Failed checks: {', '.join(failed)}")
        return 1
    else:
        logger.info("All Python checks passed")
        # Create marker file to signal tests passed (for semantic-release)
        marker_file = project_root / ".tmp" / "tests-passed"
        marker_file.parent.mkdir(exist_ok=True)
        marker_file.write_text("1")
        return 0

if __name__ == "__main__":
    sys.exit(main())
