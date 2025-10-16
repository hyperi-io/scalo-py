#!/usr/bin/env python3
"""
Python Project Structure Validation - Phase 0

Validates Python-specific project structure requirements:
- pyproject.toml exists (PEP 621)
- Package structure (src/ layout or flat layout)
- Tests directory (recommended)
- Python package metadata

This ONLY runs for Python projects.
Common checks are in common/bootstrap.d/05-project-structure.py.
"""
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent


def detect_package_layout() -> tuple[str, Path | None]:
    """
    Detect Python package layout.

    Returns:
        (layout_type, package_path) where layout_type is:
        - "src-layout": src/package_name/ structure (PEP 420)
        - "flat-layout": package_name/ at root
        - "unknown": Cannot determine package structure
    """
    project_root = get_project_root()

    # Check src-layout first (preferred)
    src_dir = project_root / "src"
    if src_dir.exists() and src_dir.is_dir():
        # Find first package directory
        for item in src_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                init_file = item / "__init__.py"
                if init_file.exists():
                    return ("src-layout", item)
        # src/ exists but no package found
        return ("src-layout", None)

    # Check flat-layout (package at root)
    # Look for directories with __init__.py at root level
    for item in project_root.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Skip common non-package directories
            if item.name in ['tests', 'docs', 'ci', '.git', '.github', 'build', 'dist']:
                continue
            init_file = item / "__init__.py"
            if init_file.exists():
                return ("flat-layout", item)

    return ("unknown", None)


def check_action() -> int:
    """Check if Python project structure is valid."""
    project_root = get_project_root()
    issues = []
    warnings = []

    # 1. pyproject.toml (REQUIRED for modern Python projects)
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        issues.append("No pyproject.toml - required for Python projects (PEP 621)")
    else:
        print("[OK] pyproject.toml exists")

    # 2. Package layout detection
    layout, package_path = detect_package_layout()
    if layout == "src-layout":
        if package_path:
            print(f"[OK] Package layout: src-layout (src/{package_path.name}/)")
        else:
            warnings.append("src/ directory exists but no package found (no __init__.py)")
    elif layout == "flat-layout":
        print(f"[OK] Package layout: flat-layout ({package_path.name}/)")
    else:
        warnings.append("Cannot detect package structure (no __init__.py found)")
        warnings.append("  Expected: src/package_name/__init__.py OR package_name/__init__.py")

    # 3. Tests directory (recommended)
    tests_dir = project_root / "tests"
    if not tests_dir.exists():
        warnings.append("No tests/ directory (recommended for quality assurance)")
    else:
        print("[OK] tests/ directory exists")

    # 4. setup.py (optional - only needed for Nuitka bdist_nuitka)
    setup_py = project_root / "setup.py"
    if setup_py.exists():
        print("[OK] setup.py exists (enables Nuitka bdist_nuitka)")
    else:
        print("[INFO] No setup.py (optional - needed only for Nuitka compiled wheels)")

    # 5. VERSION file (optional - managed by semantic-release)
    version_file = project_root / "VERSION"
    if version_file.exists():
        print("[OK] VERSION file exists")
    else:
        print("[INFO] No VERSION file (optional - managed by semantic-release)")

    # Report warnings
    if warnings:
        print("[WARN] Python structure warnings:")
        for warning in warnings:
            print(f"      - {warning}")

    # Report issues
    if issues:
        print("[ERR] Python structure validation failed:")
        for issue in issues:
            print(f"      - {issue}")
        return 1

    print("[OK] Python project structure valid")
    return 0


def install_action() -> int:
    """Install/fix Python project structure issues."""
    project_root = get_project_root()

    # Check pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        print("[ERR] Cannot auto-create pyproject.toml (project-specific)")
        print("      Create it manually with: python -m build --help")
        print("      Or use: copier copy gh:hypersec-io/forge-python .")
        return 1

    # Auto-create tests/ directory if missing
    tests_dir = project_root / "tests"
    if not tests_dir.exists():
        print("[INFO] Creating tests/ directory...")
        tests_dir.mkdir(parents=True)
        (tests_dir / "__init__.py").write_text("# Test package\n")
        (tests_dir / "test_import.py").write_text("""\"\"\"Basic import test.\"\"\"


def test_import():
    \"\"\"Test that package can be imported.\"\"\"
    # TODO: Replace with your package name
    # import your_package
    pass
""")
        print("[OK] Created tests/ directory with basic structure")

    print("[OK] Python structure install complete")
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
