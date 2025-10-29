"""Pytest configuration and fixtures for hyperlib tests."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

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

    Prevents system overload from accumulated kubectl/minikube/helm processes.
    """
    patterns = [
        "minikube ssh",
        "kubectl exec.*waiting",
        "helm install.*waiting",
        "docker pull.*waiting"
    ]

    for pattern in patterns:
        try:
            subprocess.run(
                ["pkill", "-9", "-f", pattern],
                capture_output=True,
                timeout=5
            )
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
