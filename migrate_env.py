#!/usr/bin/env python3
"""
Migrate .env file from old JF_* variables to new ARTIFACTORY_* variables.

This script helps migrate existing .env files to use the new standardized
environment variable names that match GitHub Actions secrets.
"""

import os
import sys
from pathlib import Path
import shutil
from datetime import datetime


def migrate_env_file(env_path: Path) -> bool:
    """Migrate an .env file from JF_* to ARTIFACTORY_* variables.

    Args:
        env_path: Path to the .env file

    Returns:
        bool: True if migration was performed, False if no changes needed
    """
    if not env_path.exists():
        print(f"❌ File not found: {env_path}")
        return False

    print(f"📁 Reading {env_path}...")

    # Read the file
    with open(env_path, 'r') as f:
        lines = f.readlines()

    # Track if we made any changes
    changed = False
    new_lines = []

    # Mapping of old to new variable names
    mappings = {
        'JF_USER': 'ARTIFACTORY_USERNAME',
        'JF_PASSWORD': 'ARTIFACTORY_PASSWORD',
        'JF_TOKEN': 'ARTIFACTORY_TOKEN',
        'JF_TOKEN_USER': 'ARTIFACTORY_TOKEN_USER',
        'JF_PYPI_HOST': 'ARTIFACTORY_PYPI_HOST',
    }

    for line in lines:
        original_line = line
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue

        # Check if this line contains an old variable
        for old_var, new_var in mappings.items():
            if stripped.startswith(f"{old_var}="):
                # Extract the value
                value = stripped[len(old_var) + 1:]
                new_line = f"{new_var}={value}\n"
                new_lines.append(new_line)
                print(f"  ✏️  {old_var} → {new_var}")
                changed = True
                break
        else:
            # No mapping found, keep original line
            new_lines.append(line)

    if changed:
        # Create backup
        backup_path = env_path.with_suffix(f'.env.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        shutil.copy2(env_path, backup_path)
        print(f"  💾 Created backup: {backup_path}")

        # Write the migrated file
        with open(env_path, 'w') as f:
            f.writelines(new_lines)

        print(f"  ✅ Migration complete!")
        return True
    else:
        print(f"  ℹ️  No JF_* variables found - file already uses ARTIFACTORY_* variables")
        return False


def main():
    """Main entry point."""
    print("=" * 60)
    print("ENV FILE MIGRATION: JF_* → ARTIFACTORY_*")
    print("=" * 60)
    print()
    print("This script migrates environment variables to match GitHub Actions secrets.")
    print()

    # Find .env files
    project_root = Path.cwd()
    env_files = [
        project_root / '.env',
        project_root / '.env.local',
        project_root / '.env.development',
        project_root / '.env.production',
    ]

    # Add any .env files in subdirectories
    for subdir in ['tests/ci/test_ci']:
        subdir_env = project_root / subdir / '.env'
        if subdir_env.exists():
            env_files.append(subdir_env)

    # Filter to existing files
    existing_env_files = [f for f in env_files if f.exists()]

    if not existing_env_files:
        print("❌ No .env files found!")
        print()
        print("Searched for:")
        for f in env_files:
            print(f"  - {f}")
        return 1

    print(f"Found {len(existing_env_files)} .env file(s) to check:")
    for f in existing_env_files:
        print(f"  - {f}")
    print()

    # Migrate each file
    migrated_count = 0
    for env_file in existing_env_files:
        if migrate_env_file(env_file):
            migrated_count += 1
        print()

    # Summary
    print("=" * 60)
    if migrated_count > 0:
        print(f"✅ MIGRATION COMPLETE: Updated {migrated_count} file(s)")
        print()
        print("IMPORTANT:")
        print("  1. Review the changes to ensure they're correct")
        print("  2. Test bootstrap: ./ci/bootstrap --install")
        print("  3. Delete backup files once confirmed working")
    else:
        print("ℹ️  NO CHANGES NEEDED: All files already use ARTIFACTORY_* variables")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())