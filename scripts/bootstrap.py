#!/usr/bin/env python3
"""Bootstrap entrypoint - installs hyperlib from JFrog before importing it.

Usage:
- `scripts/bootstrap` (default): Check-only mode, verify tools are present
- `scripts/bootstrap --install`: Enable installation of missing tools

CRITICAL SAFEGUARDS:
- This script MUST run in a virtual environment (.venv-ci)
- System Python is ONLY used for initial venv creation
- All pip installations MUST target .venv-ci
- NO operations should use system Python after venv creation

Three-phase bootstrap process:
1. Phase 0: Create .venv-ci if needed (system Python)
2. Phase 1: Install hyperlib from JFrog (venv Python)
3. Phase 2: Import hyperlib and run bootstrap.d scripts (venv Python)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent


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
    """Create .venv-ci if it doesn't exist. Returns True if created."""
    if venv_dir.exists():
        return False

    print(f"[INFO] Creating {venv_dir}...")
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    return True


def get_jfrog_index_url() -> str:
    """Get JFrog PyPI index URL with credentials from environment.

    Precedence: JF_TOKEN (with JF_TOKEN_USER) > JF_USER/JF_PASSWORD
    """
    base_url = "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"

    # Check for token first (preferred)
    jf_token = os.environ.get("JF_TOKEN", "")
    if jf_token:
        from urllib.parse import quote
        # Token auth requires specific username (artifactory@hypersec.io)
        jf_token_user = os.environ.get("JF_TOKEN_USER", "artifactory@hypersec.io")
        user_enc = quote(jf_token_user, safe='')
        token_enc = quote(jf_token, safe='')
        return f"https://{user_enc}:{token_enc}@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"

    # Fallback to username/password
    jf_user = os.environ.get("JF_USER", "")
    jf_password = os.environ.get("JF_PASSWORD", "")

    if jf_user and jf_password:
        # URL-encode credentials
        from urllib.parse import quote
        user_enc = quote(jf_user, safe='')
        pass_enc = quote(jf_password, safe='')
        return f"https://{user_enc}:{pass_enc}@hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"

    return base_url


def install_hyperlib(venv_python: Path) -> None:
    """Install hyperlib from JFrog Artifactory into .venv-ci."""
    try:
        # Check if hyperlib is already installed
        result = subprocess.run(
            [str(venv_python), "-c", "import hyperlib; print(hyperlib.__version__)"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"[INFO] hyperlib {version} already installed")
            return
    except Exception:
        pass

    print("[INFO] Installing hyperlib from JFrog Artifactory...")

    jfrog_url = get_jfrog_index_url()

    # Install hyperlib with fallback to PyPI if JFrog unavailable
    try:
        subprocess.check_call(
            [str(venv_python), "-m", "pip", "install", "hyperlib",
             "--extra-index-url", jfrog_url,
             "--quiet"],
            stderr=subprocess.STDOUT
        )
        print("[OK] hyperlib installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Failed to install hyperlib from JFrog: {e}")
        print("[INFO] Hyperlib may not be published yet - check JFrog credentials")
        sys.exit(1)


def reexec_in_venv(venv_python: Path) -> None:
    """Re-exec this script using the venv Python."""
    os.environ["HSF_IN_CI_VENV"] = "1"
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

    # Phase 0: Ensure .venv-ci exists
    venv_name = os.environ.get("HSF_CI_VENV", ".venv-ci")
    venv_dir = PROJECT_ROOT / venv_name
    venv_python = venv_dir / "bin" / "python"

    # If not in venv yet, create it and re-exec
    if not os.environ.get("HSF_IN_CI_VENV"):
        create_venv_if_needed(venv_dir)

        # Phase 1: Install hyperlib from JFrog
        install_hyperlib(venv_python)

        # Re-exec in venv
        reexec_in_venv(venv_python)
        # Should never reach here
        return 1

    # Phase 2: Now we're in venv with hyperlib installed
    # Verify hyperlib is available
    try:
        import hyperlib  # type: ignore
        print(f"[OK] hyperlib {hyperlib.__version__} is available")
    except ImportError as e:
        print(f"[ERR] Failed to import hyperlib: {e}")
        print("[INFO] Hyperlib should have been installed in Phase 1")
        return 1

    print("[INFO] Running bootstrap in .venv-ci")

    # Run bootstrap.d scripts
    boot_dir = PROJECT_ROOT / "scripts" / "bootstrap.d"
    if not boot_dir.exists():
        print("[INFO] No bootstrap.d directory found")
        return 0

    scripts = sorted([p for p in boot_dir.iterdir()
                     if p.is_file() and (p.suffix in ['.sh', '.py'])])

    if not scripts:
        print(f"[INFO] No bootstrap steps found at {boot_dir}")
        return 0

    install = os.environ.get("BOOTSTRAP_INSTALL", "0") == "1"

    for path in scripts:
        base = path.name
        if base.endswith(".disabled"):
            print(f"[INFO] Skipping disabled {base}")
            continue

        print(f"[INFO] Bootstrap check: {base}")
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
            print(f"[INFO] Bootstrap install: {base}")
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
