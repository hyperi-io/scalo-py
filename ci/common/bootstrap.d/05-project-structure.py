#!/usr/bin/env python3
"""
Project Structure Validation - Phase 0 (Common for ALL project types)

Validates basic project structure requirements that apply to ALL projects:
- Git repository exists
- Basic directories (.gitignore requirements)
- Configuration file (ci.yaml or ci/ci.yaml.template)

This runs for Python, Rust, Go, or any other project type.
Python-specific checks are in python/bootstrap.d/05-python-structure.py.
"""
import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent


def check_action() -> int:
    """Check if project structure is valid."""
    project_root = get_project_root()
    issues = []

    # 1. Git repository
    git_dir = project_root / ".git"
    if not git_dir.exists():
        issues.append("No .git directory - project must be a git repository")

    # 2. Gitignore file
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        issues.append("No .gitignore file - required for ci/.venv/, .venv/, etc.")
    else:
        # Check that ci/.venv is ignored
        gitignore_content = gitignore.read_text()
        if "ci/.venv" not in gitignore_content:
            issues.append(".gitignore should include 'ci/.venv/' (CI environment)")
        if ".venv" not in gitignore_content and "venv/" not in gitignore_content:
            issues.append(".gitignore should include '.venv/' (dev environment)")

    # 3. Configuration file
    ci_yaml = project_root / "ci.yaml"
    ci_yaml_template = project_root / "ci" / "ci.yaml.template"

    if not ci_yaml.exists() and not ci_yaml_template.exists():
        issues.append("No ci.yaml or ci/ci.yaml.template found")
    elif not ci_yaml.exists():
        print("[INFO] ci.yaml not found (will be created from template)")

    # 4. README (recommended but not required)
    readme = project_root / "README.md"
    if not readme.exists():
        print("[WARN] No README.md found (recommended)")

    # Report issues
    if issues:
        print("[ERR] Project structure validation failed:")
        for issue in issues:
            print(f"      - {issue}")
        return 1

    print("[OK] Project structure valid (common requirements)")
    return 0


def install_action() -> int:
    """Install/fix project structure issues."""
    project_root = get_project_root()

    # Auto-fix .gitignore if possible
    gitignore = project_root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        updated = False

        if "ci/.venv" not in content:
            print("[INFO] Adding 'ci/.venv/' to .gitignore...")
            with open(gitignore, 'a') as f:
                f.write("\n# HyperCI environments\nci/.venv/\n")
            updated = True

        if ".venv" not in content and "venv/" not in content:
            print("[INFO] Adding '.venv/' to .gitignore...")
            with open(gitignore, 'a') as f:
                if not updated:
                    f.write("\n# Development environment\n")
                f.write(".venv/\n")
            updated = True

        if updated:
            print("[OK] Updated .gitignore")
    else:
        # Create .gitignore
        print("[INFO] Creating .gitignore...")
        gitignore.write_text("""# HyperCI environments
ci/.venv/
.venv/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Distribution / packaging
dist/
dist-nuitka/
build/
*.egg-info/
.eggs/

# Testing
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Environment
.env
.keys/

# Temporary
.tmp/
*.log
""")
        print("[OK] Created .gitignore")

    print("[OK] Project structure install complete")
    return 0


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
        print(f"[ERR] Unknown action: {action}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
