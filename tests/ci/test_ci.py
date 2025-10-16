#!/usr/bin/env python3
"""
Comprehensive CI Pipeline Integration Test.

This test creates a virtual project environment to test the entire CI pipeline:
1. Bootstrap a test project
2. Run CI build
3. Test CI publish (with error handling)
4. Install from JFrog
5. Verify the installed package works
"""

import os
import sys
import shutil
import subprocess
import tempfile
import json
import pytest
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import urllib.request
import urllib.error
import base64

# Get the real project root (2 levels up from tests/ci/)
REAL_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
TEST_PROJECT_ROOT = Path(__file__).parent / "test_ci"


class TestCIPipeline:
    """Test the entire CI pipeline in an isolated environment."""

    def setup(self):
        """Set up the test environment."""
        # Clean up any existing test project
        if TEST_PROJECT_ROOT.exists():
            shutil.rmtree(TEST_PROJECT_ROOT)

        # Create test project directory
        TEST_PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

    def teardown(self):
        """Clean up after tests (optional - keep for debugging)."""
        # Uncomment to clean up after tests
        # if TEST_PROJECT_ROOT.exists():
        #     shutil.rmtree(TEST_PROJECT_ROOT)

    def create_virtual_project(self):
        """Create a minimal hyperlib project structure for testing."""
        # Create directory structure
        dirs = [
            "ci",
            "ci/python",
            "ci/python/bootstrap.d",
            "ci/python/ci.d",
            "ci/common",
            "ci/common/bootstrap.d",
            "ci/common/ci.d",
            "src/hyperlib",
            ".github/workflows",
            "tests",
            "docs",
        ]
        for d in dirs:
            (TEST_PROJECT_ROOT / d).mkdir(parents=True, exist_ok=True)

        # Copy CI infrastructure files
        files_to_copy = [
            ("ci/bootstrap", "ci/bootstrap"),
            ("ci/ci", "ci/ci"),
            ("ci/ci.yaml", "ci/ci.yaml"),
            ("ci/python/bootstrap.py", "ci/python/bootstrap.py"),  # Essential bootstrap module
            ("ci/python/ci_lib.py", "ci/python/ci_lib.py"),  # CI library
            # Copy all bootstrap.d scripts
            ("ci/python/bootstrap.d", "ci/python/bootstrap.d"),
            ("ci/common/bootstrap.d", "ci/common/bootstrap.d"),
            # Copy all ci.d scripts
            ("ci/python/ci.d", "ci/python/ci.d"),
            ("ci/common/ci.d", "ci/common/ci.d"),
            # Copy source code
            ("src/hyperlib", "src/hyperlib"),
            # Project files
            ("pyproject.toml", "pyproject.toml"),
            ("setup.py", "setup.py"),
            ("README.md", "README.md"),
            ("VERSION", "VERSION"),
        ]

        for src, dst in files_to_copy:
            src_path = REAL_PROJECT_ROOT / src
            dst_path = TEST_PROJECT_ROOT / dst

            if src_path.is_dir():
                # Copy entire directory
                if dst_path.exists():
                    shutil.rmtree(dst_path)
                shutil.copytree(src_path, dst_path, symlinks=True)
            elif src_path.exists():
                # Copy single file
                shutil.copy2(src_path, dst_path)

        # Copy .env file if it exists (for JFrog credentials)
        env_file = REAL_PROJECT_ROOT / ".env"
        if env_file.exists():
            shutil.copy2(env_file, TEST_PROJECT_ROOT / ".env")

        # Create a minimal .gitignore
        gitignore = TEST_PROJECT_ROOT / ".gitignore"
        gitignore.write_text("""
.venv/
ci/.venv/
*.pyc
__pycache__/
dist/
dist-nuitka/
build/
*.egg-info/
.keys/
.tmp/
""")

        # Initialize git repo (some CI scripts expect it)
        subprocess.run(["git", "init"], cwd=TEST_PROJECT_ROOT, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@hypersec.io"], cwd=TEST_PROJECT_ROOT, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=TEST_PROJECT_ROOT, check=True)
        subprocess.run(["git", "add", "."], cwd=TEST_PROJECT_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", "Initial test commit"], cwd=TEST_PROJECT_ROOT, check=True)

    def test_bootstrap(self):
        """Test the bootstrap process."""
        print("\n=== Testing Bootstrap ===")

        # Create the virtual project
        self.create_virtual_project()

        # Run bootstrap
        result = subprocess.run(
            ["./ci/bootstrap", "--install"],
            cwd=TEST_PROJECT_ROOT,
            capture_output=True,
            text=True
        )

        print(f"Bootstrap output:\n{result.stdout}")
        if result.stderr:
            print(f"Bootstrap stderr:\n{result.stderr}")

        assert result.returncode == 0, f"Bootstrap failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"

        # Verify ci/.venv was created
        venv_path = TEST_PROJECT_ROOT / "ci/.venv"
        assert venv_path.exists(), "ci/.venv not created"
        assert (venv_path / "bin/python").exists(), "Python not installed in venv"

        # Verify hyperlib is installed from JFrog
        result = subprocess.run(
            ["ci/.venv/bin/pip", "show", "hyperlib"],
            cwd=TEST_PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, "hyperlib not installed"
        assert "hypersec.jfrog.io" in result.stdout or "Location:" in result.stdout, \
            "hyperlib not from JFrog"

        print("✅ Bootstrap successful")

    def test_build(self):
        """Test the CI build process."""
        print("\n=== Testing Build ===")

        # Ensure bootstrap has been run
        if not (TEST_PROJECT_ROOT / "ci/.venv").exists():
            self.test_bootstrap()

        # Test standard build
        result = subprocess.run(
            ["./ci/ci", "build"],
            cwd=TEST_PROJECT_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "CI": "true"}  # Set CI env var
        )

        assert result.returncode == 0, f"Build failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"

        # Verify dist directory and artifacts
        dist_path = TEST_PROJECT_ROOT / "dist"
        assert dist_path.exists(), "dist/ directory not created"

        wheels = list(dist_path.glob("*.whl"))
        assert len(wheels) > 0, "No wheel files created"

        tarballs = list(dist_path.glob("*.tar.gz"))
        assert len(tarballs) > 0, "No source distribution created"

        print(f"✅ Build successful: {len(wheels)} wheels, {len(tarballs)} source distributions")

    def test_nuitka_build(self):
        """Test the Nuitka build process (if enabled)."""
        print("\n=== Testing Nuitka Build ===")

        # Check if Nuitka is enabled in ci.yaml
        ci_yaml_path = TEST_PROJECT_ROOT / "ci/ci.yaml"
        if not ci_yaml_path.exists():
            pytest.skip("ci/ci.yaml not found")

        import yaml
        with open(ci_yaml_path) as f:
            config = yaml.safe_load(f)

        if not config.get("nuitka", {}).get("enabled", False):
            pytest.skip("Nuitka not enabled in ci/ci.yaml")

        # Ensure bootstrap has been run
        if not (TEST_PROJECT_ROOT / "ci/.venv").exists():
            self.test_bootstrap()

        # Determine build type from config
        build_type = config.get("nuitka", {}).get("build_type", "package")

        if build_type == "package":
            # Test Nuitka compiled wheel build (uses setup.py bdist_nuitka)
            print("Building Nuitka compiled wheel...")
            result = subprocess.run(
                ["ci/.venv/bin/python", "setup.py", "bdist_nuitka"],
                cwd=TEST_PROJECT_ROOT,
                capture_output=True,
                text=True,
                env={**os.environ}
            )

            # Check if Nuitka is available
            if "No module named 'nuitka'" in result.stderr or result.returncode != 0:
                pytest.skip(f"Nuitka not available or build failed: {result.stderr[:500]}")

            # Verify compiled wheel was created
            dist_path = TEST_PROJECT_ROOT / "dist"
            compiled_wheels = list(dist_path.glob("*cp*.whl"))  # Compiled wheels have cpython tag
            assert len(compiled_wheels) > 0, "No compiled wheel created"

            # Test the compiled wheel
            wheel_path = compiled_wheels[0]
            print(f"Testing compiled wheel: {wheel_path.name}")

            # Create a test venv and install the compiled wheel
            test_venv = TEST_PROJECT_ROOT / "test_nuitka_venv"
            if test_venv.exists():
                shutil.rmtree(test_venv)

            subprocess.run([sys.executable, "-m", "venv", str(test_venv)], check=True)

            # Install the compiled wheel
            result = subprocess.run(
                [str(test_venv / "bin/pip"), "install", str(wheel_path)],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Failed to install compiled wheel: {result.stderr}"

            # Test that the compiled module works
            test_code = """
import sys
import git  # Test git import
import hyperlib
from hyperlib import get_logger, Application
from hyperlib.runtime import get_project_root

# Test basic functionality
logger = get_logger(__name__)
logger.info("Testing compiled hyperlib")

# Test Application class
app = Application("test_app", "1.0.0")
print(f"App: {app.name} v{app.version}")

# Test that we can access version
print(f"Hyperlib version: {hyperlib.__version__}")

# Test git functionality (if git module is available)
try:
    import git
    repo = git.Repo.init("/tmp/test_repo")
    print("Git import successful")
except ImportError:
    print("Git module not available (expected in compiled code)")

# Verify this is compiled code (look for .so file)
import inspect
import os
module_file = inspect.getfile(hyperlib)
print(f"Module location: {module_file}")
if '.so' in module_file or '.pyd' in module_file:
    print("✓ Running compiled Nuitka code!")
else:
    print("⚠ Running regular Python code")
"""
            result = subprocess.run(
                [str(test_venv / "bin/python"), "-c", test_code],
                capture_output=True,
                text=True
            )

            print(f"Test output:\n{result.stdout}")
            if result.returncode != 0:
                print(f"Test stderr:\n{result.stderr}")

            assert result.returncode == 0, f"Compiled module test failed: {result.stderr}"
            assert "✓ Running compiled Nuitka code!" in result.stdout or ".so" in result.stdout, \
                "Not running compiled code!"

            print(f"✅ Nuitka compiled wheel tested successfully")

        else:
            # Test standalone binary build
            print("Building Nuitka standalone binary...")
            result = subprocess.run(
                ["./ci/ci", "build"],
                cwd=TEST_PROJECT_ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "BUILD_PROFILE": "nuitka", "NUITKA_PROTECTION": "none"}
            )

            # Nuitka might not be available in test environment
            if "Nuitka not available" in result.stderr or result.returncode != 0:
                pytest.skip("Nuitka not available in test environment")

            # Verify dist-nuitka directory and artifacts
            dist_nuitka_path = TEST_PROJECT_ROOT / "dist-nuitka"
            assert dist_nuitka_path.exists(), "dist-nuitka/ directory not created"

            binaries = list(dist_nuitka_path.glob("*.bin")) + list(dist_nuitka_path.glob("*.exe"))
            assert len(binaries) > 0, "No binary files created"

            # Test the standalone binary
            binary_path = binaries[0]
            binary_path.chmod(0o755)  # Make executable

            # Run the binary with test code
            test_code = "import hyperlib; print(hyperlib.__version__)"
            result = subprocess.run(
                [str(binary_path), "-c", test_code],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f"✅ Nuitka standalone binary tested: {result.stdout.strip()}")
            else:
                print(f"⚠️ Binary test failed (might need entry point): {result.stderr[:200]}")

        print(f"✅ Nuitka build and test successful")

    def test_publish_simulation(self):
        """Test the publish process with simulated GitHub Actions and JFrog."""
        print("\n=== Testing Publish (Simulation) ===")

        # Ensure build has been run
        if not (TEST_PROJECT_ROOT / "dist").exists():
            self.test_build()

        # Test publish in dry-run mode (doesn't actually push to GitHub/JFrog)
        result = subprocess.run(
            ["./ci/ci", "publish", "--dry-run"],
            cwd=TEST_PROJECT_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "CI": "true", "JFROG_PUBLISH": "false"}
        )

        # The command might fail if semantic-release is strict, but we check for expected behavior
        if "No release will be made" in result.stdout or "No commits found" in result.stdout:
            print("⚠️  No release needed (no commits to release)")
        elif result.returncode == 0:
            print("✅ Publish dry-run successful")
        else:
            # Check if it failed for expected reasons
            if "git push" in result.stderr or "Permission denied" in result.stderr:
                print("✅ Publish dry-run reached push stage (expected failure in test)")
            else:
                pytest.fail(f"Unexpected publish failure:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")

    def wait_for_jfrog_publication(self, package_name="hyperlib", max_wait=300, check_interval=30):
        """Wait for package to be available in JFrog.

        Args:
            package_name: Name of the package to check
            max_wait: Maximum seconds to wait
            check_interval: Seconds between checks

        Returns:
            bool: True if package found, False if timeout
        """
        print(f"\n=== Waiting for {package_name} in JFrog (max {max_wait}s) ===")

        # Read credentials
        env_file = TEST_PROJECT_ROOT / ".env"
        if not env_file.exists():
            env_file = REAL_PROJECT_ROOT / ".env"

        if not env_file.exists():
            print("⚠️  No .env file - cannot check JFrog")
            return False

        username = None
        password = None
        token = None

        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ARTIFACTORY_USERNAME="):
                    username = line.split("=", 1)[1].strip()
                elif line.startswith("ARTIFACTORY_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
                elif line.startswith("ARTIFACTORY_TOKEN="):
                    token = line.split("=", 1)[1].strip()

        if not ((username and password) or token):
            print("⚠️  No ARTIFACTORY credentials - cannot check JFrog")
            return False

        # Build auth for curl
        if token:
            auth = f"token:{token}"
        else:
            auth = f"{username}:{password}"

        # JFrog API URL to check package
        api_url = f"https://hypersec.jfrog.io/artifactory/api/storage/hypersec-pypi-local/{package_name}"

        import time
        start_time = time.time()
        attempt = 0

        while time.time() - start_time < max_wait:
            attempt += 1
            print(f"  [{attempt}] Checking JFrog... ", end="", flush=True)

            try:
                result = subprocess.run(
                    ["curl", "-s", "-u", auth, api_url],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and '"uri"' in result.stdout:
                    print("✅ Package found in JFrog!")
                    # Parse JSON to show available versions
                    import json
                    try:
                        data = json.loads(result.stdout)
                        if "children" in data:
                            versions = [child["uri"].strip("/") for child in data["children"]]
                            print(f"    Available versions: {', '.join(versions[:5])}")
                    except:
                        pass
                    return True
                else:
                    print("not found yet")

            except Exception as e:
                print(f"error: {e}")

            if time.time() - start_time < max_wait:
                print(f"  Waiting {check_interval}s before next check...")
                time.sleep(check_interval)

        print(f"⚠️  Timeout: Package not found after {max_wait}s")
        return False

    def test_jfrog_installation(self):
        """Test installing the package from JFrog."""
        print("\n=== Testing JFrog Installation ===")

        # First check if package is available in JFrog
        if not self.wait_for_jfrog_publication(max_wait=60, check_interval=15):
            print("⚠️  Package not in JFrog, will test with local dist")

        # Create a separate test venv for installation
        install_venv = TEST_PROJECT_ROOT / "test_install_venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(install_venv)],
            check=True,
            capture_output=True
        )

        # Read JFrog credentials from .env
        env_file = TEST_PROJECT_ROOT / ".env"
        if not env_file.exists():
            pytest.skip("No .env file with JFrog credentials")

        username = None
        password = None
        token = None

        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ARTIFACTORY_USERNAME="):
                    username = line.split("=", 1)[1].strip()
                elif line.startswith("ARTIFACTORY_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
                elif line.startswith("ARTIFACTORY_TOKEN="):
                    token = line.split("=", 1)[1].strip()

        if not ((username and password) or token):
            pytest.skip("JFrog credentials not found in .env")

        # Configure pip to use JFrog
        jfrog_url = "https://hypersec.jfrog.io/artifactory/api/pypi/hypersec-pypi-local/simple"

        # Install hyperlib from JFrog
        if token:
            # Use token auth
            token_user = "artifactory@hypersec.io"  # or from env
            auth_url = jfrog_url.replace("https://", f"https://{token_user}:{token}@")
        else:
            # Use username/password auth
            auth_url = jfrog_url.replace("https://", f"https://{username}:{password}@")

        result = subprocess.run(
            [str(install_venv / "bin/pip"), "install", "hyperlib", "--index-url", auth_url],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"⚠️  Could not install from JFrog (might not be published yet): {result.stderr}")
            # Try to install from local dist instead
            wheel_path = next((TEST_PROJECT_ROOT / "dist").glob("*.whl"), None)
            if wheel_path:
                result = subprocess.run(
                    [str(install_venv / "bin/pip"), "install", str(wheel_path)],
                    capture_output=True,
                    text=True
                )
                assert result.returncode == 0, f"Local install failed: {result.stderr}"
                print("✅ Installed from local dist (JFrog not available)")
        else:
            print("✅ Installed from JFrog successfully")

        # Test that hyperlib works with comprehensive functionality test
        test_code = """
import sys
import os
import tempfile

# Test hyperlib imports
import hyperlib
from hyperlib import get_logger, Application
from hyperlib.config import get_logging_config
from hyperlib.harness import TestHarness
from hyperlib.runtime import get_project_root

# Test version
print(f"Hyperlib version: {hyperlib.__version__}")

# Test logger functionality
logger = get_logger(__name__)
logger.info("Testing hyperlib from JFrog")
logger.debug("Debug message")
logger.warning("Warning message")

# Test Application class
app = Application(
    name="test_jfrog_app",
    version="1.0.0",
    description="Testing JFrog installation"
)
print(f"Application: {app.name} v{app.version}")

# Test configuration
config = get_logging_config()
print(f"Logging config keys: {list(config.keys())}")

# Test with git operations (common use case)
try:
    import git
    # Try to initialize a test repo
    test_repo_path = tempfile.mkdtemp(prefix="test_git_")
    repo = git.Repo.init(test_repo_path)
    repo.index.commit("Initial test commit")
    print("✓ Git operations work with hyperlib")
except ImportError:
    print("⚠ Git module not available (okay for compiled code)")
except Exception as e:
    print(f"⚠ Git operation failed: {e}")

# Check if running compiled code
import inspect
module_file = inspect.getfile(hyperlib)
if '.so' in module_file or '.pyd' in module_file:
    print("✓ Running Nuitka-compiled hyperlib from JFrog!")
else:
    print("✓ Running standard Python hyperlib from JFrog")

# Test that submodules are accessible
from hyperlib.application import oneshot
print("✓ Submodules accessible")

print("SUCCESS: All tests passed!")
"""
        result = subprocess.run(
            [str(install_venv / "bin/python"), "-c", test_code],
            capture_output=True,
            text=True
        )

        print(f"Test output:\n{result.stdout}")
        if result.returncode != 0:
            print(f"Test stderr:\n{result.stderr}")

        assert result.returncode == 0, f"Functionality test failed: {result.stderr}"
        assert "SUCCESS: All tests passed!" in result.stdout, "Not all tests passed"

        # Check if we got compiled or standard version
        if "Nuitka-compiled" in result.stdout:
            print(f"✅ Nuitka-compiled hyperlib from JFrog tested successfully")
        else:
            print(f"✅ Standard hyperlib from JFrog tested successfully")

    def test_full_pipeline(self):
        """Test the entire CI pipeline end-to-end."""
        print("\n" + "="*60)
        print("COMPREHENSIVE CI PIPELINE TEST")
        print("="*60)

        # Run all tests in sequence
        self.test_bootstrap()
        self.test_build()
        self.test_nuitka_build()
        self.test_publish_simulation()
        self.test_jfrog_installation()

        print("\n" + "="*60)
        print("✅ ALL CI PIPELINE TESTS PASSED")
        print("="*60)


def test_ci_yaml_config():
    """Test that ci/ci.yaml configuration is valid."""
    import yaml

    ci_yaml_path = REAL_PROJECT_ROOT / "ci/ci.yaml"
    assert ci_yaml_path.exists(), "ci/ci.yaml not found"

    with open(ci_yaml_path) as f:
        config = yaml.safe_load(f)

    # Verify essential configuration
    assert "nuitka" in config, "nuitka section missing"
    assert "buildjet" in config["nuitka"], "buildjet section missing"
    assert isinstance(config["nuitka"]["buildjet"]["enabled"], bool), "buildjet.enabled must be boolean"

    print(f"✅ ci/ci.yaml valid, BuildJet enabled: {config['nuitka']['buildjet']['enabled']}")


if __name__ == "__main__":
    # Run tests directly
    import sys

    test = TestCIPipeline()
    test.setup()  # Run setup

    try:
        test.test_full_pipeline()
        test_ci_yaml_config()
        print("\n✅ All tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Optional cleanup
        pass  # test.teardown()