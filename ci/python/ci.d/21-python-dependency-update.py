#!/usr/bin/env python3
"""
Python dependency update CI step: scan dependencies and update minimum versions in pyproject.toml

This script uses vermin and dependency analysis to:
1. Scan all Python source files to determine the minimum Python version required
2. Scan dependency packages to check their minimum Python requirements
3. Analyze imported modules to determine minimum package versions needed
4. Update pyproject.toml with the highest minimum versions found
5. Update Python version classifiers accordingly
"""
import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# Import hyperlib (in generated projects it's at ci/hyperlib)
THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
from hyperlib import get_logger  # type: ignore


def run_vermin_scan(target_dir: Path, venv_prefix: str) -> Optional[Tuple[int, int]]:
    """Run vermin to scan source files and return (major, minor) version."""
    logger = get_logger("dependency-update")
    vermin_cmd = f"{venv_prefix}vermin"
    
    try:
        # Scan source files for minimum Python version
        result = subprocess.run(
            [vermin_cmd, "--target=3.8-", str(target_dir)],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Parse vermin output to extract minimum version
        for line in result.stdout.splitlines():
            if "Minimum required versions:" in line:
                # Look for pattern like "3.11"
                match = re.search(r'(\d+)\.(\d+)', line)
                if match:
                    major, minor = int(match.group(1)), int(match.group(2))
                    logger.info("Vermin detected minimum Python version: %d.%d", major, minor)
                    return (major, minor)
        
        logger.warning("Could not parse vermin output for minimum version")
        return None
    except Exception as e:
        logger.error("Failed to run vermin: %s", e)
        return None


def analyze_imports_in_source(src_dir: Path) -> Set[str]:
    """Analyze Python source files to extract imported module names."""
    logger = get_logger("dependency-update")
    imports = set()
    
    try:
        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            # Extract top-level module (e.g., "requests" from "requests.auth")
                            top_module = alias.name.split('.')[0]
                            imports.add(top_module)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            top_module = node.module.split('.')[0]
                            imports.add(top_module)
            except Exception as e:
                logger.warning("Could not parse %s: %s", py_file, e)
                continue
    except Exception as e:
        logger.error("Failed to analyze imports: %s", e)
    
    # Filter out stdlib modules (rough heuristic)
    stdlib_modules = {
        'os', 'sys', 'json', 'datetime', 'pathlib', 'subprocess', 'logging', 
        'argparse', 'tempfile', 'shutil', 'typing', 'dataclasses', 'functools',
        'itertools', 'collections', 'contextlib', 're', 'ast', 'inspect'
    }
    
    third_party = imports - stdlib_modules
    logger.info("Found imported third-party modules: %s", sorted(third_party))
    return third_party


def get_package_versions_and_requirements(venv_prefix: str, imported_modules: Set[str]) -> Tuple[Dict[str, str], Optional[Tuple[int, int]]]:
    """Get installed package versions and find minimum Python requirement."""
    logger = get_logger("dependency-update")
    pip_cmd = f"{venv_prefix}pip"
    package_versions = {}
    max_python_req = (3, 8)
    
    try:
        # Get list of installed packages with versions
        result = subprocess.run(
            [pip_cmd, "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=True
        )
        
        installed_packages = {}
        for line in result.stdout.splitlines():
            if "==" in line:
                name, version = line.split("==", 1)
                installed_packages[name.lower()] = version
        
        # For each imported module, try to find corresponding package
        for module in imported_modules:
            # Try direct name match first
            pkg_name = None
            if module.lower() in installed_packages:
                pkg_name = module.lower()
            else:
                # Try common mappings (module name != package name)
                mappings = {
                    'yaml': 'pyyaml',
                    'dotenv': 'python-dotenv',
                    'PIL': 'pillow',
                    'cv2': 'opencv-python',
                    'sklearn': 'scikit-learn',
                    'bs4': 'beautifulsoup4',
                }
                if module in mappings and mappings[module].lower() in installed_packages:
                    pkg_name = mappings[module].lower()
            
            if pkg_name:
                version = installed_packages[pkg_name]
                package_versions[module] = f"{pkg_name}>={version}"
                logger.info("Module %s maps to package %s>=%s", module, pkg_name, version)
                
                # Check this package's Python requirement
                try:
                    meta_result = subprocess.run(
                        [pip_cmd, "show", pkg_name],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    for meta_line in meta_result.stdout.splitlines():
                        if meta_line.startswith("Requires-Python:"):
                            req_python = meta_line.split(":", 1)[1].strip()
                            match = re.search(r'>=\s*(\d+)\.(\d+)', req_python)
                            if match:
                                dep_major, dep_minor = int(match.group(1)), int(match.group(2))
                                if (dep_major, dep_minor) > max_python_req:
                                    max_python_req = (dep_major, dep_minor)
                            break
                except Exception:
                    continue
            else:
                logger.warning("Could not find package for imported module: %s", module)
        
        python_req = max_python_req if max_python_req > (3, 8) else None
        return package_versions, python_req
        
    except Exception as e:
        logger.error("Failed to analyze package versions: %s", e)
        return {}, None


def get_dependency_min_python(venv_prefix: str) -> Optional[Tuple[int, int]]:
    """Check dependencies for their minimum Python requirements."""
    logger = get_logger("dependency-update")
    pip_cmd = f"{venv_prefix}pip"
    
    try:
        # Get list of installed packages
        result = subprocess.run(
            [pip_cmd, "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=True
        )
        
        max_major, max_minor = 3, 8  # Start with Python 3.8 as baseline
        
        for line in result.stdout.splitlines():
            if "==" not in line:
                continue
            pkg_name = line.split("==")[0]
            
            try:
                # Get package metadata
                meta_result = subprocess.run(
                    [pip_cmd, "show", pkg_name],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # Look for Requires-Python field
                for meta_line in meta_result.stdout.splitlines():
                    if meta_line.startswith("Requires-Python:"):
                        req_python = meta_line.split(":", 1)[1].strip()
                        # Parse >=3.11 or similar
                        match = re.search(r'>=\s*(\d+)\.(\d+)', req_python)
                        if match:
                            dep_major, dep_minor = int(match.group(1)), int(match.group(2))
                            if (dep_major, dep_minor) > (max_major, max_minor):
                                max_major, max_minor = dep_major, dep_minor
                                logger.info("Package %s requires Python %d.%d", pkg_name, dep_major, dep_minor)
                        break
            except Exception:
                continue  # Skip packages we can't inspect
        
        if (max_major, max_minor) > (3, 8):
            logger.info("Dependencies require minimum Python: %d.%d", max_major, max_minor)
            return (max_major, max_minor)
        return None
    except Exception as e:
        logger.error("Failed to check dependency requirements: %s", e)
        return None


def update_pyproject_dependencies(pyproject_path: Path, package_versions: Dict[str, str]) -> bool:
    """Update dependencies list in pyproject.toml with minimum versions."""
    logger = get_logger("dependency-update")
    
    if not pyproject_path.exists() or not package_versions:
        return False
    
    try:
        content = pyproject_path.read_text(encoding="utf-8")
        original_content = content
        
        # Find dependencies section and update versions
        lines = content.splitlines()
        new_lines = []
        in_dependencies = False
        
        for line in lines:
            if 'dependencies = [' in line:
                in_dependencies = True
                new_lines.append(line)
            elif in_dependencies and line.strip() == ']':
                in_dependencies = False
                new_lines.append(line)
            elif in_dependencies and '"' in line:
                # This is a dependency line, try to update it
                match = re.search(r'"([^">=<]+)', line)
                if match:
                    pkg_name = match.group(1)
                    # Check if we have a version update for this package
                    for module, version_spec in package_versions.items():
                        if pkg_name.lower() in version_spec.lower():
                            # Extract just the version spec part
                            new_spec = version_spec.split('>=')[1] if '>=' in version_spec else version_spec
                            # Update the line
                            updated_line = re.sub(
                                r'"([^">=<]+)([^"]*)"',
                                f'"{pkg_name}>={new_spec}"',
                                line
                            )
                            new_lines.append(updated_line)
                            logger.info("Updated dependency: %s", updated_line.strip())
                            break
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        new_content = "\n".join(new_lines)
        if new_content != original_content:
            pyproject_path.write_text(new_content, encoding="utf-8")
            logger.info("Updated pyproject.toml dependencies")
            return True
        return False
    except Exception as e:
        logger.error("Failed to update dependencies: %s", e)
        return False


def update_pyproject_toml(pyproject_path: Path, min_version: Tuple[int, int]) -> bool:
    """Update pyproject.toml with new minimum Python version."""
    logger = get_logger("dependency-update")
    major, minor = min_version
    version_str = f"{major}.{minor}"
    
    if not pyproject_path.exists():
        logger.warning("pyproject.toml not found at %s", pyproject_path)
        return False
    
    try:
        content = pyproject_path.read_text(encoding="utf-8")
        original_content = content
        
        # Update requires-python
        content = re.sub(
            r'requires-python\s*=\s*">=\d+\.\d+"',
            f'requires-python = ">={version_str}"',
            content
        )
        
        # Update Python version classifiers
        # Remove old 3.x classifiers and add current ones
        lines = content.splitlines()
        new_lines = []
        in_classifiers = False
        
        for line in lines:
            if 'classifiers = [' in line:
                in_classifiers = True
                new_lines.append(line)
            elif in_classifiers and line.strip() == ']':
                in_classifiers = False
                new_lines.append(line)
            elif in_classifiers and '"Programming Language :: Python :: 3.' in line:
                # Skip old Python 3.x classifiers; we'll add new ones
                continue
            elif in_classifiers and '"Programming Language :: Python :: 3"' in line:
                # Add the general Python 3 classifier and specific versions
                new_lines.append(line)
                new_lines.append(f'    "Programming Language :: Python :: {version_str}",')
                # Add next version if reasonable
                if minor < 13:  # Don't go beyond reasonable future versions
                    new_lines.append(f'    "Programming Language :: Python :: {major}.{minor + 1}",')
            else:
                new_lines.append(line)
        
        new_content = "\n".join(new_lines)
        
        if new_content != original_content:
            pyproject_path.write_text(new_content, encoding="utf-8")
            logger.info("Updated pyproject.toml with minimum Python %s", version_str)
            return True
        else:
            logger.info("pyproject.toml already up to date")
            return False
    except Exception as e:
        logger.error("Failed to update pyproject.toml: %s", e)
        return False


def main() -> int:
    logger = get_logger("dependency-update")
    root_dir = Path.cwd()
    
    # Assume ci/.venv has been created by core bootstrap
    venv_ci = root_dir / "ci/.venv"
    if not venv_ci.exists():
        logger.error("ci/.venv missing. Core CI should run bootstrap with installs first.")
        return 1
    
    venv_prefix = str(venv_ci / "bin") + "/"
    
    # Find source directory
    src_dirs = [d for d in ["src", "lib", "."] if (root_dir / d).exists()]
    if not src_dirs:
        logger.warning("No source directory found; skipping vermin scan")
        return 0
    
    scan_dir = root_dir / src_dirs[0]
    logger.info("Scanning %s for minimum versions", scan_dir)
    
    # Analyze imports to find third-party dependencies
    imported_modules = analyze_imports_in_source(scan_dir)
    
    # Get package versions and Python requirements from actual usage
    package_versions, deps_python_min = get_package_versions_and_requirements(venv_prefix, imported_modules)
    
    # Get minimum version from source analysis
    source_min = run_vermin_scan(scan_dir, venv_prefix)
    
    # Get minimum version from all dependencies (broader check)
    all_deps_min = get_dependency_min_python(venv_prefix)
    
    # Determine the highest minimum Python version needed
    candidates = [v for v in [source_min, deps_python_min, all_deps_min] if v is not None]
    if candidates:
        final_min = max(candidates)
        logger.info("Final minimum Python version: %d.%d", *final_min)
        
        # Update pyproject.toml Python version
        pyproject_path = root_dir / "pyproject.toml"
        if update_pyproject_toml(pyproject_path, final_min):
            logger.info("pyproject.toml Python version updated")
    else:
        logger.info("No minimum Python version requirements detected")
    
    # Update package dependencies
    pyproject_path = root_dir / "pyproject.toml"
    if package_versions and update_pyproject_dependencies(pyproject_path, package_versions):
        logger.info("pyproject.toml package dependencies updated")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
