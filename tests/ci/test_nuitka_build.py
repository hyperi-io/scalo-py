"""
Test Nuitka build profile integration.

This test validates that the Nuitka build system works correctly:
1. Bootstrap checks for Nuitka requirements
2. Build script compiles code with Nuitka
3. Output artifacts are created in correct location
4. Encryption keys are generated and stored properly
5. No publishing occurs (local CI only builds, GitHub Actions publishes)

IMPORTANT: These tests use ci/.venv (NOT .venv)
- CI tests should use ci/.venv because they test CI functionality
- ci/.venv is created by: ./ci/bootstrap --install
- Tests will be skipped if ci/.venv doesn't exist

Run lightweight tests (bootstrap checks only):
    pytest tests/ci/test_nuitka_build.py::TestNuitkaBootstrap -v

Run full tests (requires Nuitka Commercial installed):
    TEST_NUITKA=1 pytest tests/ci/test_nuitka_build.py -v
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# Get project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def project_root():
    """Provide project root path."""
    return PROJECT_ROOT


@pytest.fixture(scope="module")
def ci_venv_python():
    """Get ci/.venv Python interpreter path."""
    venv_python = PROJECT_ROOT / "ci" / ".venv" / "bin" / "python"
    if not venv_python.exists():
        pytest.skip("ci/.venv not found. Run: ./ci/bootstrap --install")
    return venv_python


@pytest.fixture(scope="module")
def clean_nuitka_artifacts():
    """Clean Nuitka build artifacts before and after test."""
    # Clean before
    dist_nuitka = PROJECT_ROOT / "dist-nuitka"
    keys_dir = PROJECT_ROOT / ".keys"

    if dist_nuitka.exists():
        shutil.rmtree(dist_nuitka)
    # Don't delete .keys directory, just leave it for manual inspection

    yield

    # Clean after (optional - comment out to inspect artifacts)
    # if dist_nuitka.exists():
    #     shutil.rmtree(dist_nuitka)


@pytest.mark.skipif(
    not os.environ.get("TEST_NUITKA"),
    reason="Nuitka tests require TEST_NUITKA=1 env var (slow and requires Nuitka Commercial)"
)
class TestNuitkaBuild:
    """Test Nuitka build profile integration."""

    def test_bootstrap_checks_nuitka_requirements(self, ci_venv_python, project_root):
        """Test that bootstrap checks for Nuitka requirements when BUILD_PROFILE=nuitka."""
        # Run bootstrap check with BUILD_PROFILE=nuitka
        env = os.environ.copy()
        env["BUILD_PROFILE"] = "nuitka"

        result = subprocess.run(
            [str(project_root / "ci" / "bootstrap")],
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root
        )

        # Should succeed (bootstrap should always succeed, even if dependencies missing)
        assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"

        # Check that Nuitka checks ran
        output = result.stdout + result.stderr
        assert "25-check-nuitka.py" in output or "Nuitka" in output


    def test_nuitka_build_with_recommended_protection(
        self,
        ci_venv_python,
        project_root,
        clean_nuitka_artifacts
    ):
        """Test Nuitka build with recommended protection profile."""
        # Set environment for Nuitka build
        env = os.environ.copy()
        env["BUILD_PROFILE"] = "nuitka"
        env["NUITKA_PROTECTION"] = "recommended"

        # Run build
        result = subprocess.run(
            [str(ci_venv_python), str(project_root / "ci" / "run"), "build"],
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root,
            timeout=600  # Nuitka can take a while
        )

        output = result.stdout + result.stderr
        print("\n=== Nuitka Build Output ===")
        print(output)
        print("=== End Output ===\n")

        # Check build succeeded
        assert result.returncode == 0, f"Nuitka build failed: {output}"

        # Check output directory exists
        dist_nuitka = project_root / "dist-nuitka"
        assert dist_nuitka.exists(), "dist-nuitka/ directory not created"

        # Check for compiled binaries (may be .bin on Linux, .exe on Windows)
        binaries = list(dist_nuitka.rglob("*.bin")) + list(dist_nuitka.rglob("*.exe"))
        assert len(binaries) > 0, "No compiled binaries found in dist-nuitka/"

        # Check for encryption key (recommended protection includes traceback encryption)
        keys_dir = project_root / ".keys"
        assert keys_dir.exists(), ".keys/ directory not created"

        key_files = list(keys_dir.glob("*.key"))
        assert len(key_files) > 0, "No encryption key files found in .keys/"

        # Verify key README exists
        key_readme = keys_dir / "README.md"
        assert key_readme.exists(), ".keys/README.md not created"


    def test_nuitka_build_with_no_protection(
        self,
        ci_venv_python,
        project_root,
        clean_nuitka_artifacts
    ):
        """Test Nuitka build with no protection (fastest build)."""
        # Set environment for Nuitka build
        env = os.environ.copy()
        env["BUILD_PROFILE"] = "nuitka"
        env["NUITKA_PROTECTION"] = "none"

        # Run build
        result = subprocess.run(
            [str(ci_venv_python), str(project_root / "ci" / "run"), "build"],
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root,
            timeout=600
        )

        output = result.stdout + result.stderr
        print("\n=== Nuitka Build Output (No Protection) ===")
        print(output)
        print("=== End Output ===\n")

        # Check build succeeded
        assert result.returncode == 0, f"Nuitka build failed: {output}"

        # Check output directory exists
        dist_nuitka = project_root / "dist-nuitka"
        assert dist_nuitka.exists(), "dist-nuitka/ directory not created"

        # Check for compiled binaries
        binaries = list(dist_nuitka.rglob("*.bin")) + list(dist_nuitka.rglob("*.exe"))
        assert len(binaries) > 0, "No compiled binaries found in dist-nuitka/"


    def test_standard_build_still_works(self, ci_venv_python, project_root):
        """Test that standard Python package build still works (BUILD_PROFILE=package)."""
        # Clean dist/ directory
        dist_dir = project_root / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)

        # Set environment for standard build
        env = os.environ.copy()
        env["BUILD_PROFILE"] = "package"  # Explicit standard build

        # Run build
        result = subprocess.run(
            [str(ci_venv_python), str(project_root / "ci" / "run"), "build"],
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root,
            timeout=120
        )

        output = result.stdout + result.stderr
        print("\n=== Standard Build Output ===")
        print(output)
        print("=== End Output ===\n")

        # Check build succeeded
        assert result.returncode == 0, f"Standard build failed: {output}"

        # Check output directory exists
        assert dist_dir.exists(), "dist/ directory not created"

        # Check for wheel and sdist
        wheels = list(dist_dir.glob("*.whl"))
        sdists = list(dist_dir.glob("*.tar.gz"))

        assert len(wheels) > 0, "No wheel files found in dist/"
        assert len(sdists) > 0, "No sdist files found in dist/"

        # Ensure Nuitka artifacts were NOT created
        dist_nuitka = project_root / "dist-nuitka"
        assert not dist_nuitka.exists() or len(list(dist_nuitka.iterdir())) == 0, \
            "Nuitka artifacts created during standard build!"


@pytest.mark.integration
class TestNuitkaBootstrap:
    """Test Nuitka bootstrap checks (faster tests, no actual build)."""

    def test_bootstrap_skips_nuitka_when_not_enabled(self, project_root):
        """Test that bootstrap skips Nuitka checks when BUILD_PROFILE != nuitka."""
        # Run bootstrap without BUILD_PROFILE=nuitka
        env = os.environ.copy()
        if "BUILD_PROFILE" in env:
            del env["BUILD_PROFILE"]  # Ensure it's not set

        result = subprocess.run(
            [str(project_root / "ci" / "bootstrap")],
            capture_output=True,
            text=True,
            env=env,
            cwd=project_root
        )

        output = result.stdout + result.stderr

        # Should succeed
        assert result.returncode == 0

        # Should skip Nuitka checks
        assert "SKIP" in output and "nuitka" in output.lower(), \
            "Bootstrap should skip Nuitka checks when BUILD_PROFILE != nuitka"


    def test_nuitka_check_script_exists(self, project_root):
        """Test that Nuitka bootstrap check script exists."""
        nuitka_check = project_root / "ci" / "python" / "bootstrap.d" / "25-check-nuitka.py"
        assert nuitka_check.exists(), "25-check-nuitka.py not found"
        assert nuitka_check.stat().st_mode & 0o111, "25-check-nuitka.py not executable"


    def test_nuitka_build_script_exists(self, project_root):
        """Test that Nuitka build script exists."""
        nuitka_build = project_root / "ci" / "python" / "ci.d" / "85-build-nuitka.py"
        assert nuitka_build.exists(), "85-build-nuitka.py not found"
        assert nuitka_build.stat().st_mode & 0o111, "85-build-nuitka.py not executable"
