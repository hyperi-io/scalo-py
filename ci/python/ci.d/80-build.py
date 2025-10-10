#!/usr/bin/env python3
"""
Build Package - Create wheel and sdist distributions.

Actions:
- check: Verify build dependencies are available
- install: Install build dependencies
- build: Build package distributions
- publish: Build and publish to JFrog Artifactory (respects JFROG_PUBLISH env)
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
        [str(venv_python), "-m", "pip", "install", "build", "twine"],
        cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        logger.error("Failed to install build dependencies")
        return 1

    logger.info("✓ Build dependencies installed")
    return 0


def build_action(logger) -> int:
    """Build package distributions."""
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
    logger.info("Building package...")
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
    else:
        logger.error("No dist/ directory created")
        return 1

    return 0


def should_publish_to_jfrog(logger) -> bool:
    """
    Determine if we should publish to JFrog Artifactory.

    Decision logic:
    1. If JFROG_PUBLISH=false, don't publish
    2. If JFROG_PUBLISH=true, publish (requires credentials)
    3. If JFROG_PUBLISH not set, auto-detect from credentials

    Returns True if should publish, False otherwise.
    """
    jfrog_publish = os.environ.get("JFROG_PUBLISH", "").lower()

    # Explicit disable
    if jfrog_publish in ("false", "0", "no", "off"):
        logger.info("JFROG_PUBLISH=false: Skipping JFrog publishing")
        return False

    # Explicit enable (requires credentials)
    if jfrog_publish in ("true", "1", "yes", "on"):
        logger.info("JFROG_PUBLISH=true: Will publish to JFrog")
        return True

    # Auto-detect from credentials
    has_token = bool(os.environ.get("JF_TOKEN"))
    has_userpass = bool(os.environ.get("JF_USER") and os.environ.get("JF_PASSWORD"))

    if has_token or has_userpass:
        logger.info("JFROG_PUBLISH not set, but credentials found: Will publish to JFrog")
        return True
    else:
        logger.info("JFROG_PUBLISH not set and no credentials found: Skipping JFrog publishing")
        return False


def publish_action(logger) -> int:
    """
    Build and publish package to JFrog Artifactory.

    Respects JFROG_PUBLISH environment variable:
    - JFROG_PUBLISH=false: Skip publishing
    - JFROG_PUBLISH=true: Force publishing (requires credentials)
    - JFROG_PUBLISH unset: Auto-detect from credentials
    """
    # Check if we should publish
    if not should_publish_to_jfrog(logger):
        logger.info("✓ Skipping JFrog publishing (use JFROG_PUBLISH=true to enable)")
        return 0

    # Verify credentials
    has_token = bool(os.environ.get("JF_TOKEN"))
    has_userpass = bool(os.environ.get("JF_USER") and os.environ.get("JF_PASSWORD"))

    if not (has_token or has_userpass):
        logger.error("JFrog credentials not found!")
        logger.error("Set one of:")
        logger.error("  - JF_TOKEN (preferred)")
        logger.error("  - JF_USER + JF_PASSWORD")
        return 1

    # Build first
    logger.info("Building package before publishing...")
    if build_action(logger) != 0:
        logger.error("Build failed, cannot publish")
        return 1

    # Publish to JFrog using twine
    venv_python = PROJECT_ROOT / "ci/.venv" / "bin" / "python"
    jfrog_url = "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local"

    # Build twine command
    cmd = [
        str(venv_python), "-m", "twine", "upload",
        "--repository-url", jfrog_url,
        "dist/*"
    ]

    # Add credentials
    if has_token:
        jf_token_user = os.environ.get("JF_TOKEN_USER", "artifactory@hypersec.io")
        jf_token = os.environ.get("JF_TOKEN")
        cmd.extend(["-u", jf_token_user, "-p", jf_token])
        logger.info(f"Publishing to JFrog with token auth (user: {jf_token_user})...")
    else:
        jf_user = os.environ.get("JF_USER")
        jf_password = os.environ.get("JF_PASSWORD")
        cmd.extend(["-u", jf_user, "-p", jf_password])
        logger.info(f"Publishing to JFrog with username/password (user: {jf_user})...")

    # Execute publish
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        logger.error("Failed to publish to JFrog Artifactory")
        return 1

    logger.info("✓ Successfully published to JFrog Artifactory")
    return 0


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install|build|publish|release]", sys.argv[0])
        return 1

    action = sys.argv[1]

    if action == "check":
        return check_action(logger)
    elif action == "install":
        return install_action(logger)
    elif action == "build":
        return build_action(logger)
    elif action == "publish":
        return publish_action(logger)
    elif action == "release":
        # For release, build if dist/ is empty
        return build_action(logger)
    else:
        # Unknown action - skip silently (other scripts may handle it)
        return 0


if __name__ == "__main__":
    sys.exit(main())
