#!/usr/bin/env python3
"""
Build Package with Nuitka - Compile Python to standalone executable.

This script compiles Python code using Nuitka Commercial with code protection.
It only runs when BUILD_PROFILE=nuitka is set.

Protection Profiles (NUITKA_PROTECTION):
- none: Basic compilation only (no protection)
- minimal: Standalone mode only
- data-hiding: Encrypt string constants and names
- traceback: Encrypt stdout/stderr and tracebacks
- recommended (default): Full protection stack

Actions:
- check: Verify Nuitka and compiler are available
- build: Compile with Nuitka using selected protection profile
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# CRITICAL: Enforce ci/.venv usage (FAIL HARD if not in ci/.venv)
if "ci/.venv" not in sys.prefix:
    print("ERROR: This script must run in ci/.venv")
    print(f"Current Python: {sys.executable}")
    print("Expected: ci/.venv/bin/python")
    print("Run via: ./ci/run build")
    sys.exit(1)

# Get project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Import from ci_lib (loguru with RFC 3339 timestamps)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ci_lib import logger, get_build_config
import platform


def is_nuitka_build_enabled() -> bool:
    """Check if Nuitka build is enabled via ci/ci.yaml or BUILD_PROFILE env var."""
    # Check ci/ci.yaml first
    enabled = get_build_config('nuitka.enabled', False)

    # Fallback: Check BUILD_PROFILE env var (backward compatibility)
    if not enabled:
        build_profile = os.environ.get("BUILD_PROFILE", "package").lower()
        enabled = (build_profile == "nuitka")

    return enabled


def detect_nuitka_type() -> str:
    """
    Detect which type of Nuitka is installed.

    Returns:
        "commercial" - Nuitka Commercial (from HyperSec JFrog)
        "opensource" - Open-source Nuitka (from public PyPI)
        "unknown" - Cannot determine or not installed
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

        # Check for commercial indicator
        if "Commercial: None" in version_output:
            return "opensource"
        elif "Commercial:" in version_output and "Commercial: None" not in version_output:
            return "commercial"
        else:
            return "unknown"

    except Exception:
        return "unknown"


def get_protection_profile() -> str:
    """Get the Nuitka protection profile from environment or config."""
    # ENV variable takes precedence, then ci/ci.yaml, then default
    env_value = os.environ.get("NUITKA_PROTECTION")
    if env_value:
        return env_value.lower()
    return get_build_config('nuitka.protection_level', 'recommended').lower()


def auto_detect_build_type() -> str:
    """
    Auto-detect if this is a library package or standalone application.

    Detection logic:
    1. Check pyproject.toml for [project.scripts] - indicates APPLICATION
    2. Check for src/ directory structure - indicates LIBRARY PACKAGE
    3. If ci/ci.yaml explicitly sets build_type, use that (override)

    Returns:
        "package" - Library package → build compiled wheels (.whl)
        "app" - Standalone application → build executable binary (.bin/.exe)
    """
    # 1. Check for explicit override in ci/ci.yaml
    yaml_build_type = get_build_config('nuitka.build_type', None)
    if yaml_build_type:
        logger.debug(f"Using explicit build_type from ci.yaml: {yaml_build_type}")
        return yaml_build_type.lower()

    # 2. Auto-detect from project structure
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    if not pyproject_path.exists():
        logger.warning("No pyproject.toml found - defaulting to 'package'")
        return "package"

    import tomllib
    with open(pyproject_path, 'rb') as f:
        config = tomllib.load(f)

    # Check for entry points (indicates APPLICATION)
    if 'project' in config:
        if 'scripts' in config['project'] or 'gui-scripts' in config['project']:
            logger.debug("Detected entry points → build_type: app")
            return "app"

    # Check for src/ structure (indicates LIBRARY PACKAGE)
    src_dir = PROJECT_ROOT / "src"
    if src_dir.exists() and src_dir.is_dir():
        logger.debug("Detected src/ structure → build_type: package")
        return "package"

    # Default: If unsure, assume package (safer default)
    logger.warning("Could not auto-detect build type - defaulting to 'package'")
    return "package"


def get_architecture() -> str:
    """
    Detect CPU architecture.

    Returns:
        Architecture string: 'x64', 'arm64', or machine type
    """
    machine = platform.machine().lower()
    if machine in ['x86_64', 'amd64']:
        return 'x64'
    elif machine in ['aarch64', 'arm64']:
        return 'arm64'
    else:
        return machine  # Return as-is for other architectures


def get_platform_name() -> str:
    """
    Detect operating system platform.

    Returns:
        Platform string: 'linux', 'darwin', 'windows'
    """
    return platform.system().lower()


def print_macos_cost_warning():
    """Print bold warning about macOS GitHub Actions costs."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("=" * 80)
    logger.info("⚠️  " + "WARNING: macOS BUILD ENABLED".center(70) + "  ⚠️")
    logger.info("=" * 80)
    logger.info("")
    logger.info("  EACH macOS BUILD COSTS AT LEAST $2.00 IN GITHUB ACTIONS CREDITS")
    logger.info("  (20x more expensive than Linux x64)")
    logger.info("")
    logger.info("  Estimated cost for this build:")
    logger.info("    - 7 minutes × $0.16/min = $1.12 - $2.00")
    logger.info("")
    logger.info("  Monthly cost (10 releases): ~$20")
    logger.info("  Monthly cost (50 releases): ~$100")
    logger.info("")
    logger.info("  To disable macOS builds:")
    logger.info("    Set nuitka_build_macos_arm64 = false in pyproject.toml")
    logger.info("")
    logger.info("=" * 80)
    logger.info("=" * 80)
    logger.info("")


def print_security_banner(message: str, char: str = "="):
    """Print a prominent security banner."""
    width = 80
    border = char * width
    logger.info("")
    logger.info(border)
    logger.info(border)
    for line in message.split('\n'):
        padding = (width - len(line) - 2) // 2
        logger.info(f"{char}{' ' * padding}{line}{' ' * (width - len(line) - padding - 2)}{char}")
    logger.info(border)
    logger.info(border)
    logger.info("")


def setup_keys_directory() -> Path:
    """
    Set up the .keys/ directory for storing encryption keys.

    Returns the path to the keys directory.
    """
    keys_dir = PROJECT_ROOT / ".keys"
    keys_dir.mkdir(exist_ok=True)

    # Create README in keys directory
    readme_path = keys_dir / "README.md"
    readme_content = """# Nuitka Encryption Keys

This directory contains encryption keys for Nuitka-compiled binaries.

## SECURITY WARNING

**CRITICAL: These keys are required to decrypt logs and tracebacks from compiled executables!**

- **DO NOT COMMIT** these keys to version control (.gitignore excludes this directory)
- **DO NOT DISTRIBUTE** keys with compiled binaries
- **BACK UP** keys securely in a password manager or key vault
- **ROTATE** keys periodically by rebuilding with new keys

## Key Files

Each Nuitka build with traceback encryption generates a unique `.key` file:

```
hyperlib-<version>-<timestamp>.key
```

## Using Keys

To decrypt encrypted logs from a Nuitka binary:

```bash
python -m nuitka.tools.commercial.decrypt \\
    --key=.keys/hyperlib-1.6.0-20250115T120000.key \\
    encrypted-output.txt
```

## Key Management Best Practices

1. **Secure Storage**: Store keys in a secure location (e.g., AWS Secrets Manager, HashiCorp Vault)
2. **Access Control**: Limit access to keys to authorized personnel only
3. **Key Rotation**: Generate new keys for each major release
4. **Backup**: Keep encrypted backups of keys in multiple secure locations
5. **Auditing**: Log all key access and usage

## Generated by

This directory is automatically created by: `ci/python/ci.d/85-build-nuitka.py`
"""
    readme_path.write_text(readme_content)

    return keys_dir


def generate_key_filename() -> str:
    """Generate a unique key filename based on version and timestamp."""
    # Get version from pyproject.toml
    version = "unknown"
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        import re
        content = pyproject_path.read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            version = match.group(1)

    # Get timestamp in ISO 8601 format
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    return f"hyperlib-{version}-{timestamp}.key"


def get_nuitka_command(protection: str, output_dir: Path, keys_dir: Path, key_filename: str) -> tuple:
    """
    Build Nuitka command based on protection profile.

    Args:
        protection: Protection profile name
        output_dir: Output directory for compiled binary
        keys_dir: Directory to store encryption keys
        key_filename: Filename for encryption key

    Returns:
        Tuple of (command arguments list, main module path)
    """
    # Find main entry point (application.py or __init__.py)
    main_module = PROJECT_ROOT / "src" / "hyperlib" / "__init__.py"
    if not main_module.exists():
        raise FileNotFoundError(f"Main module not found: {main_module}")

    # Base command
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        f"--output-dir={output_dir}",  # Nuitka requires = format
    ]

    # Add protection features based on profile
    if protection == "opensource":
        # Best options for open-source Nuitka (no commercial plugins)
        logger.info("Protection: opensource profile (best OSS options)")
        logger.info("  - Standalone mode (single directory distribution)")
        logger.info("  - Follow all imports (includes all dependencies)")
        logger.info("  - Remove assertions (performance optimization)")
        logger.info("  - No commercial plugins available")
        cmd.extend([
            "--follow-imports",     # Include all dependencies
            "--python-flag=no_asserts",  # Remove assertions for performance
            "--python-flag=-O",     # Optimize Python bytecode
        ])

    elif protection in ["data-hiding", "recommended"]:
        cmd.extend([
            "--enable-plugin=data-hiding",
        ])
        logger.info("Protection: data-hiding plugin enabled (encrypts strings and names)")

    if protection in ["traceback", "recommended"]:
        cmd.extend([
            "--enable-plugin=traceback-encryption",
            "--encrypt-stdout",
            "--encrypt-stderr",
            f"--force-stdout-spec={output_dir}/stdout-encrypted.txt",
            f"--force-stderr-spec={output_dir}/stderr-encrypted.txt",
        ])
        logger.info("Protection: traceback-encryption plugin enabled (encrypts output)")

    if protection == "recommended":
        cmd.extend([
            "--python-flag=isolated",
        ])
        logger.info("Protection: Python isolation enabled (prevents external code loading)")

    # Additional optimization flags
    cmd.extend([
        "--remove-output",       # Clean build directory after success
        "--assume-yes-for-downloads",  # Auto-download dependencies
        "--onefile",             # Create single executable
    ])

    # Add main module
    cmd.append(str(main_module))

    return cmd, main_module


def move_key_file(output_dir: Path, keys_dir: Path, key_filename: str) -> bool:
    """
    Find and move Nuitka-generated key file to .keys/ directory.

    Args:
        output_dir: Nuitka output directory
        keys_dir: Target keys directory
        key_filename: Target key filename

    Returns:
        True if key was found and moved, False otherwise
    """
    # Nuitka generates .key files in output directory
    # Find all .key files
    key_files = list(output_dir.rglob("*.key"))

    if not key_files:
        logger.warning("No key file generated by Nuitka (traceback encryption may not be enabled)")
        return False

    if len(key_files) > 1:
        logger.warning(f"Multiple key files found: {len(key_files)}")
        logger.warning("Using first key file")

    source_key = key_files[0]
    target_key = keys_dir / key_filename

    # Move key file
    shutil.move(str(source_key), str(target_key))
    logger.info(f"Moved key file: {source_key.name} -> {target_key}")

    return True


def check_action(logger) -> int:
    """Check if Nuitka build dependencies are available."""
    # Skip if Nuitka build is not enabled
    if not is_nuitka_build_enabled():
        return 0  # Skip silently

    # Check Nuitka availability (bootstrap should have installed it)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            check=False
        )
        if result.returncode != 0:
            logger.error("Nuitka not available")
            logger.error("Run: ./ci/bootstrap --install")
            return 1
    except Exception as e:
        logger.error(f"Failed to check Nuitka: {e}")
        return 1

    logger.info("✓ Nuitka build dependencies available")
    return 0


def build_package_mode(logger, nuitka_type: str, protection: str) -> int:
    """
    Build compiled wheel using setup.py bdist_nuitka.

    This creates a wheel (.whl) with compiled .so files in dist/.
    """
    logger.info("")
    logger.info("="*60)
    logger.info("BUILDING COMPILED WHEEL (package mode)")
    logger.info("="*60)

    # Clean dist directory
    dist_dir = PROJECT_ROOT / "dist"
    if dist_dir.exists():
        logger.info("Cleaning dist/ directory...")
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    # Determine platform and architecture
    plat = get_platform_name()
    arch = get_architecture()
    logger.info(f"Target: {plat}-{arch}")

    # Build command using setup.py bdist_nuitka
    cmd = [sys.executable, "setup.py", "bdist_nuitka"]

    logger.info("")
    logger.info("Running: " + " ".join(cmd))
    logger.info("Note: Protection configured in setup.py (data-hiding plugin)")
    logger.info("")

    # Run build
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        logger.error("Compiled wheel build failed")
        return 1

    # List built files
    wheels = list(dist_dir.glob("*.whl"))
    if wheels:
        logger.info("")
        logger.info(f"✓ Built {len(wheels)} compiled wheel(s):")
        for wheel in wheels:
            size_mb = wheel.stat().st_size / (1024 * 1024)
            logger.info(f"  - {wheel.name} ({size_mb:.2f} MB)")
    else:
        logger.error("No wheels found in dist/")
        return 1

    logger.info("")
    logger.info("="*60)
    logger.info("COMPILED WHEEL BUILD COMPLETE")
    logger.info("="*60)
    logger.info(f"Output: dist/")
    logger.info(f"Type: Compiled wheel with .so modules")
    logger.info("="*60)

    return 0


def build_app_mode(logger, nuitka_type: str, protection: str) -> int:
    """
    Build standalone binary using Nuitka.

    This creates a .bin/.exe file in dist-nuitka/.
    """
    logger.info("")
    logger.info("="*60)
    logger.info("BUILDING STANDALONE BINARY (app mode)")
    logger.info("="*60)

    # Detect platform and architecture
    plat = get_platform_name()
    arch = get_architecture()
    logger.info(f"Platform: {plat}")
    logger.info(f"Architecture: {arch}")
    logger.info(f"Building for: {plat}-{arch}")
    logger.info(f"Protection: {protection}")

    # Show cost warning for macOS (EXPENSIVE!)
    if plat == 'darwin':
        print_macos_cost_warning()

    # Set up keys directory
    keys_dir = setup_keys_directory()
    logger.info(f"Keys directory: {keys_dir}")

    # Generate key filename
    key_filename = generate_key_filename()
    logger.info(f"Key filename: {key_filename}")

    # Create output directory
    output_dir = PROJECT_ROOT / "dist-nuitka"
    if output_dir.exists():
        logger.info("Cleaning dist-nuitka/ directory...")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Build Nuitka command
    try:
        cmd, main_module = get_nuitka_command(protection, output_dir, keys_dir, key_filename)
    except Exception as e:
        logger.error(f"Failed to build Nuitka command: {e}")
        return 1

    # Show build command (sanitized)
    logger.info("Nuitka command:")
    logger.info(" ".join(cmd))

    # Run Nuitka compilation
    logger.info("")
    logger.info("Starting Nuitka compilation (this may take several minutes)...")
    logger.info("")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode != 0:
        logger.error("Nuitka compilation failed")
        return 1

    # Handle key file if traceback encryption was used
    key_created = False
    if protection in ["traceback", "recommended"]:
        if move_key_file(output_dir, keys_dir, key_filename):
            key_created = True
            key_path = keys_dir / key_filename

            # Print prominent security warning
            print_security_banner(
                f"""
CRITICAL: ENCRYPTION KEY GENERATED

A new encryption key has been created for this build:

  {key_path.relative_to(PROJECT_ROOT)}

THIS KEY IS REQUIRED TO DECRYPT LOGS AND TRACEBACKS!

Security Checklist:
  [ ] Key is backed up securely (password manager, key vault)
  [ ] Key is NOT committed to git (already in .gitignore)
  [ ] Access to key is restricted to authorized personnel
  [ ] Key location is documented for operations team

To decrypt logs:
  python -m nuitka.tools.commercial.decrypt \\
    --key={key_path.relative_to(PROJECT_ROOT)} \\
    encrypted-output.txt
""",
                char="#"
            )

    # Rename binary with architecture-specific name
    built_files = list(output_dir.rglob("*.bin")) + list(output_dir.rglob("*.exe"))
    if built_files:
        # Rename first binary to arch-specific name
        original_binary = built_files[0]

        # Determine extension
        extension = '.exe' if plat == 'windows' else '.bin'

        # Create arch-specific filename
        arch_specific_name = f"hyperlib-{plat}-{arch}{extension}"
        arch_specific_path = output_dir / arch_specific_name

        # Rename
        original_binary.rename(arch_specific_path)
        logger.info(f"✓ Built Nuitka binary:")

        file_size = arch_specific_path.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"  - {arch_specific_name} ({file_size:.2f} MB)")

        # Update built_files list
        built_files = [arch_specific_path]
    else:
        logger.warning("No binaries found in output directory")
        logger.info(f"Check output directory: {output_dir}")

    logger.info("")
    logger.info("="*60)
    logger.info("NUITKA BUILD COMPLETE")
    logger.info("="*60)
    logger.info(f"Platform:         {plat}-{arch}")
    logger.info(f"Output directory: {output_dir.relative_to(PROJECT_ROOT)}")
    if key_created:
        logger.info(f"Encryption key:   {keys_dir.relative_to(PROJECT_ROOT)}/{key_filename}")
    logger.info("="*60)

    return 0


def build_action(logger) -> int:
    """
    Build package with Nuitka compilation.

    Auto-detects build type:
    - "package" → Compiled wheel (.whl with .so) for libraries
    - "app" → Standalone binary (.bin/.exe) for applications
    """
    # Skip if Nuitka build is not enabled
    if not is_nuitka_build_enabled():
        return 0  # Skip silently (regular build will handle it)

    logger.info("="*60)
    logger.info("NUITKA BUILD PROFILE ACTIVE")
    logger.info("="*60)

    # Auto-detect build type
    build_type = auto_detect_build_type()
    logger.info(f"Build type: {build_type} (auto-detected)")

    # Detect Nuitka type
    nuitka_type = detect_nuitka_type()
    logger.info(f"Nuitka type: {nuitka_type}")

    if nuitka_type == "opensource":
        logger.warning("="*60)
        logger.warning("[WARN] Using OPEN-SOURCE Nuitka")
        logger.warning("       Limited protection features available")
        logger.warning("       Commercial features NOT available:")
        logger.warning("         - data-hiding plugin (string encryption)")
        logger.warning("         - traceback-encryption plugin")
        logger.warning("="*60)
    elif nuitka_type == "commercial":
        logger.info("[OK] Using Nuitka Commercial - Full protection available")
    else:
        logger.warning("[WARN] Cannot determine Nuitka type - assuming basic features")

    # Get protection profile
    protection = get_protection_profile()
    logger.info(f"Protection profile: {protection}")

    # Auto-select 'opensource' profile if OSS Nuitka is detected
    if nuitka_type == "opensource" and protection not in ["none", "minimal", "opensource"]:
        logger.warning(f"[WARN] Protection profile '{protection}' not supported by OSS Nuitka")
        logger.warning("       Auto-selecting 'opensource' profile")
        protection = "opensource"

    # Validate protection profile
    valid_profiles = ["none", "minimal", "data-hiding", "traceback", "recommended", "opensource"]
    if protection not in valid_profiles:
        logger.error(f"Invalid NUITKA_PROTECTION: {protection}")
        logger.error(f"Valid options: {', '.join(valid_profiles)}")
        return 1

    # Warn if trying to use Commercial features with OSS
    if nuitka_type == "opensource" and protection in ["data-hiding", "traceback", "recommended"]:
        logger.error(f"[ERR] Protection profile '{protection}' requires Nuitka Commercial")
        logger.error("      Open-source Nuitka does not support commercial plugins")
        logger.error("      Use one of: none, minimal, opensource")
        return 1

    # Route to appropriate build function
    if build_type == "package":
        return build_package_mode(logger, nuitka_type, protection)
    elif build_type == "app":
        return build_app_mode(logger, nuitka_type, protection)
    else:
        logger.error(f"Unknown build type: {build_type}")
        return 1


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        return 0  # Skip silently if no action specified

    action = sys.argv[1]

    if action == "check":
        return check_action(logger)
    elif action == "build":
        return build_action(logger)
    else:
        # Unknown action - skip silently (other scripts may handle it)
        return 0


if __name__ == "__main__":
    sys.exit(main())
