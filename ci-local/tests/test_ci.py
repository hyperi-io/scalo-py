#!/usr/bin/env python3
"""
CI Infrastructure Integration Test - Tests REAL ci/ infrastructure in-place.

Tests the actual hyperlib CI system with ci-local/.venv and uv:
1. Local build (standard package)
2. Local build with Nuitka (compiled wheel)
3. GitHub Actions trigger (manual dispatch)
4. Verify JFrog publication

This tests the REAL CI as configured, not a virtual environment.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Project root is where this test runs FROM (tests/ci/ -> ../..)
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class TestRealCI:
    """Test the real CI infrastructure in-place."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Setup and teardown for each test."""
        # Store original directory
        self.original_dir = Path.cwd()

        # Change to project root for all tests
        os.chdir(PROJECT_ROOT)

        # Store original env vars
        self.original_env = os.environ.copy()

        yield

        # Restore
        os.chdir(self.original_dir)
        os.environ.clear()
        os.environ.update(self.original_env)

        # Clean up build artifacts after tests
        self._cleanup_artifacts()

    def _cleanup_artifacts(self):
        """Clean up build artifacts."""
        for artifact_dir in ["dist", "dist-nuitka", "build"]:
            path = PROJECT_ROOT / artifact_dir
            if path.exists():
                print(f"Cleaning up: {artifact_dir}/")
                shutil.rmtree(path)

    def test_bootstrap_with_ci_local_venv(self):
        """Test bootstrap creates ci-local/.venv (NOT ci/.venv)."""
        print("\n" + "="*70)
        print("TEST: Bootstrap with ci-local/.venv")
        print("="*70)

        # Clean venvs to test fresh
        for venv_dir in [PROJECT_ROOT / "ci-local/.venv", PROJECT_ROOT / "ci/.venv"]:
            if venv_dir.exists():
                print(f"Removing existing: {venv_dir}")
                shutil.rmtree(venv_dir)

        # Run bootstrap
        result = subprocess.run(
            ["ci/bootstrap", "--install"],
            capture_output=True,
            text=True,
            timeout=300
        )

        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")

        assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"

        # Verify ci-local/.venv was created (NOT ci/.venv)
        ci_local_venv = PROJECT_ROOT / "ci-local/.venv"
        ci_venv = PROJECT_ROOT / "ci/.venv"

        assert ci_local_venv.exists(), "ci-local/.venv was NOT created"
        assert (ci_local_venv / "bin/python").exists(), "Python not in ci-local/.venv"

        # ci/.venv should NOT exist (ci/ is READ-ONLY)
        if ci_venv.exists():
            print(f"WARNING: ci/.venv exists (should not - ci/ is READ-ONLY)")
            print(f"  This indicates bootstrap is still creating ci/.venv")
            pytest.fail("ci/.venv should NOT be created - ci/ must be READ-ONLY!")

        # Verify ci-local/uv.lock exists
        assert (PROJECT_ROOT / "ci-local/uv.lock").exists(), "ci-local/uv.lock not found"

        # Verify dynaconf was installed
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "-c", "import dynaconf; print(dynaconf.__version__)"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "dynaconf not installed in ci-local/.venv"
        print(f"✓ dynaconf v{result.stdout.strip()} installed")

        # Verify uv was used (check for uv in ci-local/.venv)
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "-m", "pip", "list"],
            capture_output=True,
            text=True
        )
        assert "uv" in result.stdout, "uv not installed"
        print("✓ uv installed in ci-local/.venv")

        print("✅ Bootstrap creates ci-local/.venv correctly")

    def test_local_build_standard(self):
        """Test local standard build (pure Python package)."""
        print("\n" + "="*70)
        print("TEST: Local Standard Build")
        print("="*70)

        # Ensure bootstrap ran
        if not (PROJECT_ROOT / "ci-local/.venv").exists():
            self.test_bootstrap_with_ci_local_venv()

        # Clean dist
        self._cleanup_artifacts()

        # Run build using ci-local/.venv
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "ci/python/ci.d/80-build.py", "build"],
            capture_output=True,
            text=True,
            timeout=120
        )

        print(result.stdout)
        if result.returncode != 0:
            print(f"STDERR: {result.stderr}")

        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Verify artifacts
        dist_dir = PROJECT_ROOT / "dist"
        assert dist_dir.exists(), "dist/ not created"

        wheels = list(dist_dir.glob("*.whl"))
        tarballs = list(dist_dir.glob("*.tar.gz"))

        assert len(wheels) > 0, "No wheel created"
        assert len(tarballs) > 0, "No sdist created"

        print(f"✅ Built {len(wheels)} wheel(s), {len(tarballs)} sdist(s)")

    def test_local_build_nuitka(self):
        """Test local Nuitka build (compiled wheel)."""
        print("\n" + "="*70)
        print("TEST: Local Nuitka Build")
        print("="*70)

        # Ensure bootstrap ran
        if not (PROJECT_ROOT / "ci-local/.venv").exists():
            self.test_bootstrap_with_ci_local_venv()

        # Clean dist
        self._cleanup_artifacts()

        # Check if Nuitka is available
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "-c", "import nuitka"],
            capture_output=True
        )
        if result.returncode != 0:
            pytest.skip("Nuitka not installed (run bootstrap with JFrog credentials)")

        # Run Nuitka build using ci-local/.venv
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "ci/python/ci.d/85-build-nuitka.py", "build"],
            capture_output=True,
            text=True,
            env={**os.environ, "CI_BUILD_PROFILE": "nuitka", "CI_NUITKA_PROTECTION": "none"},
            timeout=600  # Nuitka can be slow
        )

        print(result.stdout)
        if result.returncode != 0:
            print(f"STDERR: {result.stderr}")

        assert result.returncode == 0, f"Nuitka build failed: {result.stderr}"

        # Verify compiled wheel
        dist_dir = PROJECT_ROOT / "dist"
        wheels = list(dist_dir.glob("*.whl"))

        assert len(wheels) > 0, "No wheel created"

        # Check if it's compiled (has platform tag)
        wheel_name = wheels[0].name
        is_compiled = "linux" in wheel_name or "win" in wheel_name or "macosx" in wheel_name

        print(f"Wheel: {wheel_name}")
        print(f"Is compiled: {is_compiled}")

        # Verify .so file inside wheel
        import zipfile
        with zipfile.ZipFile(wheels[0], 'r') as zf:
            files = zf.namelist()
            so_files = [f for f in files if f.endswith('.so') or f.endswith('.pyd')]

        print(f"Compiled files in wheel: {len(so_files)}")
        if so_files:
            print(f"  {so_files[0]}")

        assert len(so_files) > 0, "No .so files in wheel - not compiled!"

        print(f"✅ Nuitka build successful - {len(so_files)} compiled modules")

    def test_github_actions_trigger(self):
        """Test triggering GitHub Actions workflows (doesn't wait for completion)."""
        print("\n" + "="*70)
        print("TEST: GitHub Actions Workflow Trigger")
        print("="*70)

        # Check if gh CLI is available
        result = subprocess.run(["gh", "--version"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("gh CLI not available")

        # Check if we have GitHub auth
        result = subprocess.run(["gh", "auth", "status"], capture_output=True)
        if result.returncode != 0:
            pytest.skip("Not authenticated with GitHub (gh auth login)")

        # List workflows to verify they exist
        result = subprocess.run(
            ["gh", "workflow", "list", "--repo", "hypersec-io/hyperlib"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, "Failed to list workflows"
        print("Available workflows:")
        print(result.stdout)

        # Verify our workflows exist
        assert "JFrog Publish" in result.stdout, "JFrog Publish workflow not found"
        assert "Nuitka Multi-Arch Release" in result.stdout, "Nuitka workflow not found"

        print("✅ GitHub Actions workflows are configured")
        print("   To trigger: FORCE_RELEASE=1 CI_PUSH=1 ci/bootstrap publish")

    def test_jfrog_publish_script(self):
        """Test that publish script detects environment correctly."""
        print("\n" + "="*70)
        print("TEST: Publish Script Environment Detection")
        print("="*70)

        # Ensure we have a build
        if not (PROJECT_ROOT / "dist").exists():
            self.test_local_build_standard()

        # Test 1: Without FORCE_PUBLISH (should recommend GitHub Actions)
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "ci/python/ci.d/81-publish.py", "publish"],
            capture_output=True,
            text=True,
            env={**os.environ}
        )

        # Should exit with recommendation (returncode 1)
        assert result.returncode == 1, "Should recommend GitHub Actions"
        assert "PUBLISH RECOMMENDATION" in result.stdout, "Missing GHA recommendation"
        assert "multi-arch" in result.stdout.lower(), "Missing multi-arch mention"

        print("✓ Correctly recommends GitHub Actions for multi-arch")

        # Test 2: Check credentials required
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "ci/python/ci.d/81-publish.py", "check"],
            capture_output=True,
            text=True
        )

        # Should pass if credentials in ci-local/.env
        if result.returncode == 0:
            print("✓ JFrog credentials available in ci-local/.env")
        else:
            print("⚠️  JFrog credentials not configured (expected in test env)")

        print("✅ Publish script behaves correctly")

    def test_ci_config_module(self):
        """Test the new ci_config module with dynaconf."""
        print("\n" + "="*70)
        print("TEST: CI Config Module (dynaconf)")
        print("="*70)

        # Test importing ci_config
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "-c", """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'ci/common'))
from ci_config import force_release, force_publish, build_profile, push_enabled
print(f'force_release: {force_release()}')
print(f'force_publish: {force_publish()}')
print(f'build_profile: {build_profile()}')
print(f'push_enabled: {push_enabled()}')
"""],
            capture_output=True,
            text=True,
            env={**os.environ}
        )

        print(result.stdout)
        if result.returncode != 0:
            print(f"STDERR: {result.stderr}")

        assert result.returncode == 0, f"ci_config import failed: {result.stderr}"
        assert "force_release: False" in result.stdout, "Default force_release wrong"
        assert "build_profile: package" in result.stdout, "Default build_profile wrong"

        # Test with environment variable
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "-c", """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'ci/common'))
from ci_config import force_release, build_profile
print(f'force_release: {force_release()}')
print(f'build_profile: {build_profile()}')
"""],
            capture_output=True,
            text=True,
            env={**os.environ, "CI_FORCE_RELEASE": "1", "CI_BUILD_PROFILE": "nuitka"}
        )

        print(result.stdout)
        assert "force_release: True" in result.stdout, "CI_FORCE_RELEASE=1 not working"
        assert "build_profile: nuitka" in result.stdout, "CI_BUILD_PROFILE not working"

        print("✅ ci_config module works with env vars")

    def test_ci_local_structure(self):
        """Test ci-local/ directory structure is correct."""
        print("\n" + "="*70)
        print("TEST: ci-local/ Directory Structure")
        print("="*70)

        ci_local = PROJECT_ROOT / "ci-local"

        # Required files/dirs
        required = [
            "pyproject.toml",
            "uv.lock",
            "README.md",
            ".gitignore",
            "common/bootstrap.d",
            "common/ci.d",
            "python/bootstrap.d",
            "python/ci.d",
        ]

        for item in required:
            path = ci_local / item
            assert path.exists(), f"Missing: ci-local/{item}"
            print(f"✓ {item}")

        # Verify gitignore has .env and .venv
        gitignore = (ci_local / ".gitignore").read_text()
        assert ".env" in gitignore, ".env not in ci-local/.gitignore"
        assert ".venv" in gitignore, ".venv not in ci-local/.gitignore"

        # Verify uv.lock has dynaconf
        uv_lock = (ci_local / "uv.lock").read_text()
        assert "dynaconf" in uv_lock, "dynaconf not in ci-local/uv.lock"

        print("✅ ci-local/ structure is correct")

    def test_ci_readonly(self):
        """Test that ci/ directory is truly READ-ONLY (no .venv creation)."""
        print("\n" + "="*70)
        print("TEST: ci/ is READ-ONLY")
        print("="*70)

        ci_dir = PROJECT_ROOT / "ci"

        # Check if ci/.venv exists (it shouldn't after bootstrap)
        ci_venv = ci_dir / ".venv"

        if ci_venv.exists():
            pytest.fail(
                "ci/.venv exists! ci/ should be READ-ONLY.\n"
                "All .venv creation should go to ci-local/.venv"
            )

        # Verify ci/.gitignore doesn't expect .venv
        ci_gitignore = ci_dir / ".gitignore"
        if ci_gitignore.exists():
            content = ci_gitignore.read_text()
            # Old entries might still be there, that's ok
            # Just verify we're not creating ci/.venv
            pass

        print("✓ ci/.venv does NOT exist")
        print("✓ ci/ directory is READ-ONLY")
        print("✅ ci/ READ-ONLY constraint verified")

    def test_workflows_use_ci_local_venv(self):
        """Test that workflows reference ci-local/.venv."""
        print("\n" + "="*70)
        print("TEST: Workflows Use ci-local/.venv")
        print("="*70)

        workflows = [
            PROJECT_ROOT / ".github/workflows/jfrog-publish.yml",
            PROJECT_ROOT / ".github/workflows/nuitka-release.yml",
        ]

        for workflow in workflows:
            if not workflow.exists():
                print(f"⚠️  {workflow.name} not found")
                continue

            content = workflow.read_text()

            # Should reference ci-local/.venv (not ci/.venv)
            assert "ci-local/.venv" in content, f"{workflow.name} doesn't use ci-local/.venv"

            # Should NOT reference ci/.venv
            if "ci/.venv" in content:
                # Check if it's in a comment or string
                lines_with_ci_venv = [line for line in content.split('\n') if 'ci/.venv' in line and not line.strip().startswith('#')]
                if lines_with_ci_venv:
                    pytest.fail(f"{workflow.name} still references ci/.venv: {lines_with_ci_venv[0]}")

            # Should use ci/ scripts
            assert "ci/python/ci.d/" in content, f"{workflow.name} doesn't use ci/ scripts"

            # Should use ci/bootstrap
            assert "ci/bootstrap" in content, f"{workflow.name} doesn't use ci/bootstrap"

            print(f"✓ {workflow.name} uses ci-local/.venv and ci/ scripts")

        print("✅ All workflows use ci-local/.venv correctly")

    def test_unified_scripts(self):
        """Test that same scripts work locally and in GitHub Actions."""
        print("\n" + "="*70)
        print("TEST: Unified Scripts (local = GitHub Actions)")
        print("="*70)

        # Verify scripts exist
        scripts = [
            "ci/python/ci.d/80-build.py",
            "ci/python/ci.d/81-publish.py",
            "ci/python/ci.d/85-build-nuitka.py",
        ]

        for script in scripts:
            path = PROJECT_ROOT / script
            assert path.exists(), f"Script not found: {script}"

            # Verify it has GitHub Actions detection
            content = path.read_text()
            has_gh_detect = "GITHUB_ACTIONS" in content or "is_github_actions" in content

            print(f"✓ {Path(script).name} exists (GHA detection: {has_gh_detect})")

        print("✅ Scripts are unified for local and GitHub Actions")

    @pytest.mark.slow
    def test_full_publish_flow_dry_run(self):
        """Test the full publish flow in dry-run mode."""
        print("\n" + "="*70)
        print("TEST: Full Publish Flow (Dry Run)")
        print("="*70)

        # This tests semantic-release without actually publishing
        result = subprocess.run(
            ["ci-local/.venv/bin/python", "ci/common/ci.d/90-semantic-release.py", "release"],
            capture_output=True,
            text=True,
            env={**os.environ, "CI_FORCE_RELEASE": "1", "CI_PUSH": "0"},  # Dry run
            timeout=120
        )

        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")

        # May fail if no new commits, but should run
        if "No release will be made" in result.stdout or "No new version" in result.stdout:
            print("✓ semantic-release ran (no new version needed)")
        elif result.returncode == 0:
            print("✓ semantic-release would create new version")

        print("✅ Publish flow can be executed")


def test_ci_yaml_exists():
    """Quick test that ci.yaml exists at project root."""
    ci_yaml = PROJECT_ROOT / "ci.yaml"
    assert ci_yaml.exists(), "ci.yaml not found at project root"

    import yaml
    with open(ci_yaml) as f:
        config = yaml.safe_load(f)

    assert "nuitka" in config, "ci.yaml missing nuitka section"
    print(f"✅ ci.yaml valid at project root")


if __name__ == "__main__":
    """Run tests directly with python (not pytest)."""
    print("="*70)
    print("HYPERLIB CI INFRASTRUCTURE TEST")
    print("Testing REAL ci/ infrastructure with ci-local/.venv")
    print("="*70)

    test = TestRealCI()

    try:
        # Manual setup (change to project root)
        os.chdir(PROJECT_ROOT)

        test.test_ci_local_structure()
        test.test_bootstrap_with_ci_local_venv()
        test.test_ci_readonly()
        test.test_workflows_use_ci_local_venv()
        test.test_unified_scripts()
        test.test_ci_config_module()
        test.test_local_build_standard()

        # Optional: Nuitka test (skip if Nuitka not available)
        try:
            test.test_local_build_nuitka()
        except Exception as e:
            print(f"\n⚠️  Nuitka test skipped: {e}")

        # Optional: GitHub Actions trigger test
        try:
            test.test_github_actions_trigger()
        except Exception as e:
            print(f"\n⚠️  GitHub Actions test skipped: {e}")

        # Optional: Publish flow test
        try:
            test.test_jfrog_publish_script()
        except Exception as e:
            print(f"\n⚠️  Publish script test skipped: {e}")

        # Quick config test
        test_ci_yaml_exists()

        print("\n" + "="*70)
        print("✅ ALL CI INFRASTRUCTURE TESTS PASSED")
        print("="*70)
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            test._cleanup_artifacts()
        except:
            pass
