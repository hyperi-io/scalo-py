"""Pytest configuration and fixtures for hs-pylib tests."""

import os
import socket
import subprocess
import tempfile
import time
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
                # Strip quotes from value
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value


# =============================================================================
# Kafka Integration Test Support
# =============================================================================

KAFKA_DOCKER_COMPOSE = Path(__file__).parent.parent / "docker-compose.kafka.yml"
KAFKA_CONTAINER_NAME = "hs-pylib-kafka"
KAFKA_PROJECT_NAME = "hs-pylib-test"  # Unique project name to avoid conflicts

# Track if we started Docker Kafka (so we know to clean it up)
_kafka_started_by_tests = False


def _check_kafka_connection(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if Kafka broker is reachable via TCP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False


def _is_our_kafka_container_running() -> bool:
    """Check if our specific test Kafka container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", KAFKA_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and "true" in result.stdout.lower()
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _start_docker_kafka() -> bool:
    """
    Start local Docker Kafka if not running.

    Uses a unique project name to avoid conflicts with other Kafka containers.
    """
    global _kafka_started_by_tests

    if not KAFKA_DOCKER_COMPOSE.exists():
        return False

    try:
        # Check if our container is already running
        if _is_our_kafka_container_running():
            return True

        # Check if something else is using port 9092
        if _check_kafka_connection("localhost", 9092, timeout=1.0):
            # Port is in use by something else - use it but don't track for cleanup
            print("\n  Found existing Kafka on localhost:9092 (not started by tests)")
            return True

        # Start the container with unique project name
        print("\n  Starting local Docker Kafka (hs-pylib-test)...")
        subprocess.run(
            [
                "docker", "compose",
                "-f", str(KAFKA_DOCKER_COMPOSE),
                "-p", KAFKA_PROJECT_NAME,
                "up", "-d",
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )

        # Wait for Kafka to be ready (up to 45 seconds for first start)
        for i in range(45):
            if _check_kafka_connection("localhost", 9092, timeout=1.0):
                print(f"  Docker Kafka ready after {i + 1}s")
                _kafka_started_by_tests = True
                return True
            time.sleep(1)

        print("  Docker Kafka failed to start within 45s")
        return False

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  Failed to start Docker Kafka: {e}")
        return False


def _stop_docker_kafka() -> None:
    """Stop Docker Kafka if we started it."""
    global _kafka_started_by_tests

    if not _kafka_started_by_tests:
        return

    if not KAFKA_DOCKER_COMPOSE.exists():
        return

    try:
        print("\n  Stopping Docker Kafka (hs-pylib-test)...")
        subprocess.run(
            [
                "docker", "compose",
                "-f", str(KAFKA_DOCKER_COMPOSE),
                "-p", KAFKA_PROJECT_NAME,
                "down", "-v",  # -v removes volumes for clean state
            ],
            capture_output=True,
            timeout=30,
        )
        _kafka_started_by_tests = False
        print("  Docker Kafka stopped and cleaned up")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  Failed to stop Docker Kafka: {e}")


def _get_kafka_config_for_env(force_local: bool = False) -> tuple[dict | None, str]:
    """
    Get Kafka configuration based on environment.

    Args:
        force_local: If True, skip remote Kafka and use local Docker only.

    Priority:
    1. Remote Kafka from .env (k8s.tyrell.com.au) if reachable (unless force_local)
    2. Local Docker Kafka (localhost:9092) if reachable or can be started

    Returns:
        Tuple of (config dict or None, source description)
    """
    from hs_pylib.kafka.config import ADMIN_DEFAULTS, config_from_env, merge_config

    # Try remote Kafka from .env first (unless forcing local)
    if not force_local:
        env_config = config_from_env()
        bootstrap_servers = env_config.get("bootstrap.servers", "")

        if bootstrap_servers:
            # Parse host:port from bootstrap servers
            first_broker = bootstrap_servers.split(",")[0]
            if ":" in first_broker:
                host, port = first_broker.rsplit(":", 1)
                try:
                    port = int(port)
                    if _check_kafka_connection(host, port, timeout=3.0):
                        print(f"\n  Using remote Kafka: {bootstrap_servers}")
                        return merge_config(env_config, ADMIN_DEFAULTS, verify_ssl=False), "remote"
                except ValueError:
                    pass

    # Try local Docker Kafka
    if _check_kafka_connection("localhost", 9092, timeout=1.0) or _start_docker_kafka():
        print("\n  Using local Docker Kafka: localhost:9092")
        return merge_config(
            {"bootstrap.servers": "localhost:9092"},
            ADMIN_DEFAULTS,
            verify_ssl=False,
        ), "local"

    return None, "none"


@pytest.fixture(scope="session")
def kafka_available() -> bool:
    """Check if any Kafka broker is available for integration tests."""
    config, _ = _get_kafka_config_for_env()
    return config is not None


@pytest.fixture(scope="session")
def kafka_config(request):
    """
    Provide Kafka configuration for integration tests.

    Automatically selects:
    1. Remote Kafka (from .env) if reachable
    2. Local Docker Kafka if available or can be started
    3. Skips test if no Kafka is available

    Cleans up Docker Kafka after tests if we started it.
    """
    config, source = _get_kafka_config_for_env()
    if config is None:
        pytest.skip(
            "No Kafka available. Set KAFKA_BOOTSTRAP_SERVERS in .env or "
            "run: docker compose -f docker-compose.kafka.yml up -d"
        )

    # Register cleanup finalizer
    request.addfinalizer(_stop_docker_kafka)

    return config


@pytest.fixture(scope="session")
def kafka_config_local_only(request):
    """
    Provide Kafka configuration forcing local Docker only.

    Skips remote Kafka even if configured in .env.
    Useful for testing the Docker fallback path.
    """
    config, source = _get_kafka_config_for_env(force_local=True)
    if config is None:
        pytest.skip(
            "No local Kafka available. "
            "Run: docker compose -f docker-compose.kafka.yml up -d"
        )

    # Register cleanup finalizer
    request.addfinalizer(_stop_docker_kafka)

    return config


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
