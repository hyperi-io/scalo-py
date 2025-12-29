"""Pytest configuration and fixtures for hs-pylib tests."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Enable DEBUG logging for all tests
os.environ["LOG_LEVEL"] = "DEBUG"

# Load .env file for test credentials (Artifactory, database, etc.)
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value


def cleanup_hung_processes():
    """
    Kill hung background processes from previous test runs.

    Uses HS_LIB-specific labels to avoid killing other projects' processes.
    """
    # Kill processes with HS_LIB test labels
    hs_pylib_patterns = ["HS_LIB_TEST_HELM", "HS_LIB_TEST_K8S", "HS_LIB_TEST_DOCKER", "HS_LIB_TEST_MINIKUBE"]

    for pattern in hs_pylib_patterns:
        try:
            subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, Exception):
            pass  # Best effort cleanup

    # Also kill generic hung Kubernetes commands (broad cleanup)
    generic_patterns = [
        "minikube ssh.*docker login",
        "kubectl.*helm-hs-pylib",  # hs-pylib-specific namespace
        "helm install.*hs-pylib",  # hs-pylib-specific releases
    ]

    for pattern in generic_patterns:
        try:
            subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, Exception):
            pass  # Best effort cleanup


@pytest.fixture(scope="session", autouse=True)
def session_cleanup():
    """Session-level fixture to cleanup before and after all tests."""
    # Cleanup before tests start
    cleanup_hung_processes()

    yield

    # Cleanup after all tests complete
    cleanup_hung_processes()


@pytest.fixture
def temp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# Note: httpx_mock fixture is provided by pytest-httpx automatically
# No need to define it manually
