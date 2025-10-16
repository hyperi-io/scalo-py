#!/usr/bin/env python3
"""
Build Package - Create wheel and sdist distributions.

Actions:
- check: Verify build dependencies are available
- install: Install build dependencies
- build: Build package distributions to dist/

IMPORTANT: This script ONLY builds local artifacts.
Publishing to JFrog is handled EXCLUSIVELY by GitHub Actions.
See: .github/workflows/jfrog-publish.yml
"""

import subprocess
import sys
from pathlib import Path

# CRITICAL: Enforce ci/.venv usage (FAIL HARD if not in ci/.venv)
if "ci/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci/.venv")
    print(f"Current Python: {sys.executable}")
    print("Expected: ci/.venv/bin/python")
    print("Run via: ./ci/ci build")
    sys.exit(1)

# Get project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Import from ci_lib (loguru with RFC 3339 timestamps)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ci_lib import logger


def check_action(logger) -> int:
    """Check if build dependencies are available."""
    venv_python = PROJECT_ROOT / "ci/.venv" / "bin" / "python"
    if not venv_python.exists():
        logger.error("ci/.venv not found. Run: ./ci/bootstrap --install")
        return 1

    # Check if build module is available
    result = subprocess.run(
        [str(venv_python), "-c", "import build"],
        capture_output=True
    )
    if result.returncode != 0:
        logger.error("build module not available")
        logger.info("Install with: ci/.venv/bin/pip install build")
        return 1

    logger.info("✓ Build dependencies available")
    return 0


def install_action(logger) -> int:
    """Install build dependencies."""
    venv_python = PROJECT_ROOT / "ci/.venv" / "bin" / "python"
    if not venv_python.exists():
        logger.error("ci/.venv not found. Run: ./ci/bootstrap --install")
        return 1

    logger.info("Installing build dependencies...")
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "build"],
        cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        logger.error("Failed to install build dependencies")
        return 1

    logger.info("✓ Build dependencies installed")
    return 0


def build_action(logger) -> int:
    """Build package distributions to dist/."""
    import shutil

    venv_python = PROJECT_ROOT / "ci/.venv" / "bin" / "python"
    if not venv_python.exists():
        logger.error("ci/.venv not found. Run: ./ci/bootstrap --install")
        return 1

    # Clean dist directory
    dist_dir = PROJECT_ROOT / "dist"
    if dist_dir.exists():
        logger.info("Cleaning dist/ directory...")
        shutil.rmtree(dist_dir)

    # Build package
    logger.info("Building package to dist/...")
    result = subprocess.run(
        [str(venv_python), "-m", "build"],
        cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        logger.error("Build failed")
        return 1

    # List built files
    if dist_dir.exists():
        files = list(dist_dir.iterdir())
        logger.info(f"✓ Built {len(files)} distributions:")
        for file in sorted(files):
            logger.info(f"  - {file.name}")
        logger.info("")
        logger.info("Note: Publishing to JFrog happens via GitHub Actions")
        logger.info("      Push version tag to trigger: git push origin v<version>")
    else:
        logger.error("No dist/ directory created")
        return 1

    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|build|release]", sys.argv[0])
        return 1

    action = sys.argv[1]

    if action == "check":
        return check_action(logger)
    elif action == "install":
        return install_action(logger)
    elif action == "build":
        return build_action(logger)
    elif action == "release":
        # For release, build if dist/ is empty
        return build_action(logger)
    else:
        # Unknown action - skip silently (other scripts may handle it)
        return 0


if __name__ == "__main__":
    sys.exit(main())
