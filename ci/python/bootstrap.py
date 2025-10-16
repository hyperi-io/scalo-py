#!/usr/bin/env python3
"""Bootstrap entrypoint - creates venvs and runs bootstrap checks.

Usage:
- `ci/bootstrap` (default): Check-only mode, verify tools are present
- `ci/bootstrap --install`: Enable installation of missing tools

CRITICAL SAFEGUARDS:
- This script MUST run in a virtual environment (ci/.venv)
- System Python is ONLY used for initial venv creation
- All pip installations MUST target ci/.venv
- NO operations should use system Python after venv creation

Two-phase bootstrap process:
1. Phase 0: Create ci/.venv and .venv if needed (system Python)
2. Phase 1: Run ci/bootstrap.d scripts to install tools (venv Python)

CI Environment:
- ci/.venv: Self-contained CI tools (pytest, ruff, black, mypy, etc.)
- .venv: Development environment with uv enforced
- NO project-specific dependencies in ci/.venv (completely portable)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent  # ci/python/
CI_DIR = THIS_DIR.parent  # ci/
PROJECT_ROOT = CI_DIR.parent  # project root


def load_dotenv_minimal() -> None:
    """Minimal .env loader without external dependencies."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Simple variable expansion for ${VAR}
                if "${" in value:
                    import re
                    for match in re.findall(r'\$\{([^}]+)\}', value):
                        value = value.replace(f"${{{match}}}", os.environ.get(match, ""))
                os.environ.setdefault(key, value)


def is_in_venv() -> bool:
    """Check if we're running inside a virtual environment."""
    return (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )


def create_venv_if_needed(venv_dir: Path) -> bool:
    """Create venv if it doesn't exist. Returns True if created."""
    if venv_dir.exists():
        return False

    print(f"[INFO] Creating {venv_dir}...")
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    return True


def ensure_dev_venv(project_root: Path) -> None:
    """
    Ensure .venv exists for development (safe, non-destructive).

    Creates .venv if missing, installs uv, and enforces uv-only usage.
    This ensures developers and AI agents have a consistent dev environment.

    CRITICAL: .venv MUST use uv (not pip directly) for package management.
    """
    dev_venv = project_root / ".venv"

    # Create .venv if it doesn't exist
    if not dev_venv.exists():
        print("[INFO] Creating .venv for development...")
        subprocess.check_call([sys.executable, "-m", "venv", str(dev_venv)])
        print("[OK] .venv created")
    else:
        print("[INFO] .venv already exists")

    # Install uv into .venv if not present
    dev_python = dev_venv / "bin" / "python"
    uv_bin = dev_venv / "bin" / "uv"

    if not uv_bin.exists():
        print("[INFO] Installing uv into .venv...")
        try:
            subprocess.check_call(
                [str(dev_python), "-m", "pip", "install", "uv", "--quiet"],
                stderr=subprocess.DEVNULL
            )
            print("[OK] uv installed in .venv")
        except subprocess.CalledProcessError:
            print("[WARN] Failed to install uv in .venv (optional)")
            return
    else:
        print("[INFO] uv already available in .venv")

    # Add UV enforcement markers and wrappers
    add_uv_enforcement(dev_venv)


def add_uv_enforcement(venv_path: Path) -> None:
    """
    Add UV enforcement to .venv (marker file, activation patch, pip wrapper).

    This ensures .venv ONLY uses uv for package management, not pip directly.
    """
    # 1. Create marker file
    marker = venv_path / ".USE_UV_ONLY"
    if not marker.exists():
        marker.write_text(
            "This venv uses uv for package management.\n"
            "DO NOT use pip directly!\n"
            "\n"
            "Instead of: pip install <package>\n"
            "Use:        uv pip install <package>\n"
            "\n"
            "Created by: ci/python/bootstrap.py\n"
        )

    # 2. Patch activation script to set UV_ONLY env var
    activate_script = venv_path / "bin" / "activate"
    if activate_script.exists():
        content = activate_script.read_text()
        if "UV_ONLY" not in content:
            # Add UV_ONLY environment variable
            uv_patch = '\n# UV enforcement (added by bootstrap)\nexport UV_ONLY=1\nexport UV_PYTHON_INSTALL_DIR="$VIRTUAL_ENV"\n'
            # Insert before deactivate function
            if 'deactivate ()' in content:
                content = content.replace('deactivate ()', f'{uv_patch}\ndeactivate ()')
                activate_script.write_text(content)

    # 3. Create pip wrapper that enforces uv usage
    pip_wrapper = venv_path / "bin" / "pip-direct"
    original_pip = venv_path / "bin" / "pip.bak"
    pip_bin = venv_path / "bin" / "pip"

    # Backup original pip if not already backed up
    if pip_bin.exists() and not original_pip.exists():
        import shutil
        shutil.copy2(pip_bin, original_pip)

        # Replace pip with enforcement wrapper
        pip_wrapper_content = '''#!/bin/bash
# pip enforcement wrapper - redirects to uv
echo "ERROR: Direct pip usage not allowed in .venv" >&2
echo "This project enforces uv for package management." >&2
echo "" >&2
echo "Instead of: pip install <package>" >&2
echo "Use:        uv pip install <package>" >&2
echo "" >&2
echo "Or use uvx for one-off tools:" >&2
echo "  uvx <command>" >&2
echo "" >&2
echo "To force pip anyway: .venv/bin/pip.bak \"$@\"" >&2
exit 1
'''
        pip_bin.write_text(pip_wrapper_content)
        pip_bin.chmod(0o755)

    print("[OK] UV enforcement added to .venv")


def get_jfrog_index_url() -> str:
    """Get JFrog PyPI index URL with credentials from environment.

    Precedence: ARTIFACTORY_TOKEN (with ARTIFACTORY_TOKEN_USER) > ARTIFACTORY_USERNAME/ARTIFACTORY_PASSWORD

    Configuration via environment variables:
    - JFROG_URL: Full JFrog PyPI URL (optional, has default)
    - Default: https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple
    """
    base_url = os.environ.get(
        "JFROG_URL",
        "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"
    )

    # Check for token first (preferred)
    jf_token = os.environ.get("ARTIFACTORY_TOKEN", "")
    if jf_token:
        from urllib.parse import quote
        # Token auth requires specific username (artifactory@hypersec.io)
        jf_token_user = os.environ.get("ARTIFACTORY_TOKEN_USER", "artifactory@hypersec.io")
        user_enc = quote(jf_token_user, safe='')
        token_enc = quote(jf_token, safe='')
        return f"https://{user_enc}:{token_enc}@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"

    # Fallback to username/password
    jf_user = os.environ.get("ARTIFACTORY_USERNAME", "")
    jf_password = os.environ.get("ARTIFACTORY_PASSWORD", "")

    if jf_user and jf_password:
        # URL-encode credentials
        from urllib.parse import quote
        user_enc = quote(jf_user, safe='')
        pass_enc = quote(jf_password, safe='')
        return f"https://{user_enc}:{pass_enc}@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"

    return base_url


def install_project_package(venv_python: Path, package_name: str) -> bool:
    """
    Install project package from JFrog Artifactory into ci/.venv (optional).

    Args:
        venv_python: Path to ci/.venv Python interpreter
        package_name: Name of package to install (from BOOTSTRAP_PACKAGE env var)

    Returns:
        True if package is available, False otherwise.

    This is OPTIONAL - projects don't need a JFrog package to use this CI.
    Set BOOTSTRAP_PACKAGE env var to enable (e.g., BOOTSTRAP_PACKAGE=mylib).
    """
    if not package_name:
        print("[INFO] No BOOTSTRAP_PACKAGE specified, skipping package installation")
        return False

    try:
        # Check if package is already installed
        result = subprocess.run(
            [str(venv_python), "-c", f"import {package_name}; print({package_name}.__version__)"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"[INFO] {package_name} {version} already installed")
            return True
    except Exception:
        pass

    # Check if JFrog credentials are available
    jfrog_url = get_jfrog_index_url()
    if "://" not in jfrog_url or "@" not in jfrog_url:
        # No credentials available
        print(f"[INFO] Skipping {package_name} installation (no JFrog credentials)")
        print("[INFO] This is OK - JFrog packages are optional")
        return False

    print(f"[INFO] Installing {package_name} from JFrog Artifactory...")

    # Try to install package
    try:
        subprocess.check_call(
            [str(venv_python), "-m", "pip", "install", package_name,
             "--extra-index-url", jfrog_url,
             "--quiet"],
            stderr=subprocess.STDOUT
        )
        print(f"[OK] {package_name} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Failed to install {package_name}: {e}")
        print(f"[INFO] Continuing without {package_name} (optional dependency)")
        return False


def reexec_in_venv(venv_python: Path) -> None:
    """Re-exec this script using the venv Python."""
    os.environ["IN_CI_VENV"] = "1"
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def main() -> int:
    """Bootstrap entrypoint."""
    parser = argparse.ArgumentParser(description="Bootstrap development environment")
    parser.add_argument("--install", action="store_true",
                       help="Install missing tools (default: check-only)")
    args = parser.parse_args()

    # Load .env file early
    load_dotenv_minimal()

    # Set environment variable based on CLI flag
    if args.install:
        os.environ["BOOTSTRAP_INSTALL"] = "1"
    else:
        os.environ.setdefault("BOOTSTRAP_INSTALL", "0")

    # Phase 0: Ensure ci/.venv exists
    venv_dir = CI_DIR / ".venv"
    venv_python = venv_dir / "bin" / "python"

    # If not in venv yet, create it and re-exec
    if not os.environ.get("IN_CI_VENV"):
        # Create ci/.venv for CI/automation
        create_venv_if_needed(venv_dir)

        # Also ensure .venv exists for development (safe, non-destructive)
        ensure_dev_venv(PROJECT_ROOT)

        # Phase 1: CI tools will be installed by bootstrap.d scripts
        # No project-specific packages installed here - CI is self-contained

        # Re-exec in venv
        reexec_in_venv(venv_python)
        # Should never reach here
        return 1

    # Phase 2: Now we're in ci/.venv (self-contained, no project dependencies)
    print("[INFO] Running in ci/.venv (self-contained CI environment)")

    # Collect bootstrap.d scripts from common/ and language-specific directories
    bootstrap_dirs = [
        (CI_DIR / "common" / "bootstrap.d", "common"),
        (CI_DIR / "python" / "bootstrap.d", "python"),
    ]

    all_scripts = []
    for boot_dir, label in bootstrap_dirs:
        if boot_dir.exists():
            scripts = sorted([p for p in boot_dir.iterdir()
                            if p.is_file() and (p.suffix in ['.sh', '.py'])])
            for script in scripts:
                all_scripts.append((script, label))

    if not all_scripts:
        print("[INFO] No bootstrap steps found")
        return 0

    install = os.environ.get("BOOTSTRAP_INSTALL", "0") == "1"

    for path, label in all_scripts:
        base = path.name
        if base.endswith(".disabled"):
            print(f"[INFO] Skipping disabled {base}")
            continue

        print(f"[INFO] Bootstrap check [{label}]: {base}")
        try:
            if base.endswith(".sh"):
                subprocess.check_call(["bash", str(path), "check"])
            elif base.endswith(".py"):
                subprocess.check_call([str(venv_python), str(path), "check"])
        except subprocess.CalledProcessError as e:
            if not install:
                print(f"[WARN] Check failed for {base} (use --install to fix)")
                continue

        if install:
            print(f"[INFO] Bootstrap install [{label}]: {base}")
            try:
                if base.endswith(".sh"):
                    subprocess.check_call(["bash", str(path), "install"])
                elif base.endswith(".py"):
                    subprocess.check_call([str(venv_python), str(path), "install"])
            except subprocess.CalledProcessError as e:
                print(f"[ERR] Install failed for {base}: {e}")
                return 1

    print("[OK] Bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
