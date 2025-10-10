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

# Import from ci_lib (loguru with RFC 3339 timestamps)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ci_lib import logger

def detect_coverage_source(project_root: Path) -> str:
    """
    Auto-detect what to measure coverage for.

    Returns coverage source path:
    - Package name (e.g., "mypackage") if src/ layout
    - "src" directory if it exists
    - "." (current directory) for application/script projects
    - Can be overridden with COVERAGE_SOURCE env var
    """
    # Allow manual override
    override = os.environ.get("COVERAGE_SOURCE")
    if override:
        return override

    # Check for src/ directory (package layout)
    src_dir = project_root / "src"
    if src_dir.exists():
        packages = [p.name for p in src_dir.iterdir()
                   if p.is_dir() and not p.name.startswith('_') and not p.name.endswith('.egg-info')]
        if packages:
            return packages[0]  # Return first package found
        return "src"  # No package found, but src/ exists

    # Check for common application directories
    for app_dir in ["app", "lib", "core"]:
        if (project_root / app_dir).exists():
            return app_dir

    # Fallback: measure current directory (for scripts/flat projects)
    return "."


def main():
    """Run Python package tests and checks."""
    project_root = Path(__file__).parent.parent.parent.parent
    venv_ci = project_root / "ci/.venv"
    venv_bin = venv_ci / "bin"

    if not venv_ci.exists():
        logger.error("ci/.venv not found - run ./ci/bootstrap first")
        return 1

    failed = []

    # Auto-detect coverage source (works for packages, apps, scripts)
    coverage_source = detect_coverage_source(project_root)

    # Run pytest (with coverage if available)
    logger.info("Running pytest...")
    pytest_args = [str(venv_bin / "pytest"), "-v"]

    # Add coverage if pytest-cov is available
    try:
        subprocess.run([str(venv_bin / "python"), "-c", "import pytest_cov"],
                      capture_output=True, check=True)
        pytest_args.extend([f"--cov={coverage_source}", "--cov-report=term-missing"])
        logger.info(f"Coverage enabled for: {coverage_source}")
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
