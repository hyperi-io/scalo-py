#!/usr/bin/env python3
"""
Nuitka Bootstrap - Install nuitka-commercial from JFrog or nuitka (OSS) as fallback.

This script handles Nuitka installation with smart source detection:
1. If JFrog configured and working → Install nuitka-commercial (Commercial)
2. If JFrog NOT configured → Install nuitka (OSS) with WARNING

Package names:
- nuitka-commercial: Commercial version from JFrog (imports as 'nuitka')
- nuitka: Open-source version from public PyPI (imports as 'nuitka')

Bootstrap Policy:
- JFrog available → MUST install nuitka-commercial
- JFrog unavailable → Allow nuitka (OSS) with warnings
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Import from ci_lib (loguru with RFC 3339 timestamps)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ci_lib import logger, print_system_dependency_hint


def is_nuitka_build_enabled() -> bool:
    """Check if Nuitka build is enabled via ci/ci.yaml or BUILD_PROFILE env var."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ci_lib import get_build_config

    # Check ci/ci.yaml first
    enabled = get_build_config('nuitka.enabled', False)

    # Fallback: Check BUILD_PROFILE env var (backward compatibility)
    if not enabled:
        build_profile = os.environ.get("BUILD_PROFILE", "package").lower()
        enabled = (build_profile == "nuitka")

    return enabled


def check_c_compiler() -> bool:
    """Check if a suitable C compiler is available for the current platform."""
    system = platform.system()

    if system == "Linux":
        gcc_path = shutil.which("gcc")
        clang_path = shutil.which("clang")

        if gcc_path:
            try:
                result = subprocess.run(["gcc", "--version"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    logger.info(f"[OK] C compiler found: {version_line}")
                    return True
            except Exception:
                pass

        if clang_path:
            try:
                result = subprocess.run(["clang", "--version"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    logger.info(f"[OK] C compiler found: {version_line}")
                    return True
            except Exception:
                pass

        logger.error("[ERR] No C compiler found (gcc or clang required)")
        print_system_dependency_hint("C compiler", "gcc")
        return False

    elif system == "Darwin":
        clang_path = shutil.which("clang")
        if clang_path:
            try:
                result = subprocess.run(["clang", "--version"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    version_line = result.stdout.split('\n')[0]
                    logger.info(f"[OK] C compiler found: {version_line}")
                    return True
            except Exception:
                pass

        logger.error("[ERR] No C compiler found (Xcode Command Line Tools required)")
        print_system_dependency_hint("C compiler (Xcode Command Line Tools)", "clang")
        return False

    elif system == "Windows":
        cl_path = shutil.which("cl")  # MSVC
        gcc_path = shutil.which("gcc")  # MinGW

        if cl_path:
            logger.info("[OK] C compiler found: MSVC (cl.exe)")
            return True

        if gcc_path:
            logger.info("[OK] C compiler found: MinGW (gcc.exe)")
            return True

        logger.error("[ERR] No C compiler found (MSVC or MinGW required)")
        print_system_dependency_hint("C compiler (MSVC or MinGW)", "cl or gcc")
        return False

    else:
        logger.warning(f"[WARN] Unknown platform: {system}")
        logger.warning("       C compiler check skipped")
        return True


def detect_nuitka_type() -> str:
    """
    Detect which type of Nuitka is installed.

    Returns:
        "commercial" - Nuitka Commercial
        "opensource" - Open-source Nuitka
        "unknown" - Cannot determine
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            return "unknown"

        version_output = result.stdout

        if "Commercial: None" in version_output:
            return "opensource"
        elif "Commercial:" in version_output and "Commercial: None" not in version_output:
            return "commercial"
        else:
            return "unknown"

    except Exception:
        return "unknown"


def check_nuitka_installed() -> bool:
    """Check if Nuitka is installed and importable."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode == 0:
            version_line = result.stdout.strip()
            logger.info(f"[OK] Nuitka installed: {version_line}")
            return True
        else:
            logger.error("[ERR] Nuitka not installed in ci/.venv")
            return False
    except Exception as e:
        logger.error(f"[ERR] Failed to check Nuitka: {e}")
        return False


def test_jfrog_availability() -> bool:
    """Test if JFrog credentials are configured and working."""
    # Use only ARTIFACTORY_* environment variables (matching GitHub secrets)
    username = os.environ.get("ARTIFACTORY_USERNAME")
    password = os.environ.get("ARTIFACTORY_PASSWORD")
    token = os.environ.get("ARTIFACTORY_TOKEN")
    token_user = os.environ.get("ARTIFACTORY_TOKEN_USER", "artifactory@hypersec.io")

    has_userpass = bool(username and password)
    has_token = bool(token)

    if not (has_token or has_userpass):
        logger.info("[INFO] No JFrog credentials found")
        return False

    # Test connectivity
    import urllib.parse
    jf_host = os.environ.get("ARTIFACTORY_PYPI_HOST",
                             "hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple")

    if has_token:
        user_encoded = urllib.parse.quote(token_user, safe='')
        token_encoded = urllib.parse.quote(token, safe='')
        jfrog_url = f"https://{user_encoded}:{token_encoded}@{jf_host}"
    else:
        user_encoded = urllib.parse.quote(username, safe='')
        password_encoded = urllib.parse.quote(password, safe='')
        jfrog_url = f"https://{user_encoded}:{password_encoded}@{jf_host}"

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", "nuitka-commercial",
             "--index-url", jfrog_url],
            capture_output=True,
            text=True,
            check=False,
            timeout=10
        )

        if result.returncode == 0:
            logger.info("[OK] JFrog Artifactory is accessible and working")
            return True
        else:
            logger.warning("[WARN] JFrog credentials present but access failed")
            return False

    except subprocess.TimeoutExpired:
        logger.warning("[WARN] JFrog access timed out")
        return False
    except Exception as e:
        logger.warning(f"[WARN] Failed to test JFrog: {e}")
        return False


def check_action() -> int:
    """Check if Nuitka is available."""
    if not is_nuitka_build_enabled():
        logger.info("[SKIP] Nuitka not enabled in ci/ci.yaml")
        return 0

    logger.info("Nuitka build enabled - checking requirements...")

    checks_passed = True

    # Check C compiler
    if not check_c_compiler():
        checks_passed = False

    # Check Nuitka installed
    if not check_nuitka_installed():
        logger.error("[ERR] Nuitka not installed")
        logger.error("      Run: ./ci/bootstrap --install")
        checks_passed = False
    else:
        # Check type
        nuitka_type = detect_nuitka_type()
        if nuitka_type == "commercial":
            logger.info("[OK] Nuitka Commercial installed")
        elif nuitka_type == "opensource":
            logger.warning("[WARN] Open-source Nuitka installed (limited features)")
        else:
            logger.warning("[WARN] Cannot determine Nuitka type")

    if checks_passed:
        logger.info("✓ Nuitka requirements satisfied")
        return 0
    else:
        logger.error("✗ Nuitka requirements not met")
        return 1


def install_action() -> int:
    """Install Nuitka (nuitka-commercial from JFrog or nuitka OSS as fallback)."""
    if not is_nuitka_build_enabled():
        logger.info("[SKIP] Nuitka not enabled in ci/ci.yaml")
        return 0

    logger.info("Nuitka build enabled - installing requirements...")

    # Check C compiler
    if not check_c_compiler():
        logger.error("[ERR] C compiler required for Nuitka")
        logger.error("      Install gcc/clang via system package manager")
        return 1

    # Test JFrog availability
    jfrog_available = test_jfrog_availability()

    # CASE 1: JFrog available → Install nuitka-commercial
    if jfrog_available:
        logger.info("[POLICY] JFrog available: Installing nuitka-commercial")

        # Check if nuitka-commercial already installed
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "nuitka-commercial"],
            capture_output=True,
            check=False
        )

        if result.returncode == 0:
            logger.info("[OK] nuitka-commercial already installed")
            if check_nuitka_installed() and detect_nuitka_type() == "commercial":
                logger.info("✓ Nuitka Commercial verified")
                return 0

        # Uninstall OSS nuitka if present
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "nuitka"],
            capture_output=True,
            check=False
        )
        if result.returncode == 0:
            logger.warning("[WARN] OSS 'nuitka' package found - uninstalling")
            subprocess.run([sys.executable, "-m", "pip", "uninstall", "nuitka", "-y"], stdout=subprocess.DEVNULL)
            logger.info("[OK] OSS nuitka uninstalled")

        # Install nuitka-commercial (pip.conf has JFrog as PRIMARY)
        logger.info("Installing nuitka-commercial from JFrog...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "nuitka-commercial"],
            check=False
        )

        if result.returncode == 0:
            logger.info("[OK] nuitka-commercial installed")

            if check_nuitka_installed() and detect_nuitka_type() == "commercial":
                logger.info("✓ Nuitka Commercial installation complete")
                return 0
            else:
                logger.error("[ERR] nuitka-commercial installed but not working correctly")
                return 1
        else:
            logger.error("[ERR] Failed to install nuitka-commercial from JFrog")
            logger.error("      Check if nuitka-commercial package exists in JFrog")
            return 1

    # CASE 2: JFrog NOT available → Install OSS nuitka with WARNING
    else:
        logger.warning("=" * 70)
        logger.warning("[WARN] JFrog NOT available: Installing OSS nuitka")
        logger.warning("       Limited features - no commercial plugins")
        logger.warning("=" * 70)

        # Check if already installed
        if check_nuitka_installed():
            nuitka_type = detect_nuitka_type()
            if nuitka_type == "commercial":
                logger.info("[OK] Nuitka Commercial already installed (keeping it)")
                return 0
            elif nuitka_type == "opensource":
                logger.info("[OK] OSS nuitka already installed")
                logger.warning("[WARN] Using OSS version (limited features)")
                return 0

        # Install OSS from public PyPI
        logger.info("Installing nuitka (OSS) from public PyPI...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "nuitka"],
            check=False
        )

        if result.returncode == 0:
            logger.info("[OK] OSS nuitka installed")
            logger.warning("[WARN] Using OSS version (limited features)")
            return 0
        else:
            logger.error("[ERR] Failed to install nuitka from public PyPI")
            return 1


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
        logger.error(f"Unknown action: {action}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
