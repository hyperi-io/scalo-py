"""Pytest configuration and fixtures for scalo tests."""

import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_scalo_env_prefix():
    """Isolate the process-global env-var prefix between tests.

    The single scalo env prefix (set via ServiceApp/set_env_prefix or the bare
    ENV_PREFIX var) is process-global. A CLI/app test that sets it would
    otherwise leak into later tests, making bare control-var reads miss.
    """
    import scalo._env_compat as _ec

    _ec._prefix_override = None
    os.environ.pop("ENV_PREFIX", None)
    yield
    _ec._prefix_override = None


# Enable DEBUG logging for all tests
os.environ["LOG_LEVEL"] = "DEBUG"

# Disable OTel OTLP exporter in tests -- prevents atexit export errors
# when no collector is running (causes exit code 1 even with all tests passing).
# Tests that specifically validate OTLP reader creation pass explicit config.
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

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
KAFKA_CONTAINER_NAME = "scalo-kafka"
KAFKA_PROJECT_NAME = "scalo-test"  # Unique project name to avoid conflicts

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
    except (TimeoutError, OSError):
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
        print("\n  Starting local Docker Kafka (scalo-test)...")
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(KAFKA_DOCKER_COMPOSE),
                "-p",
                KAFKA_PROJECT_NAME,
                "up",
                "-d",
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
        print("\n  Stopping Docker Kafka (scalo-test)...")
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(KAFKA_DOCKER_COMPOSE),
                "-p",
                KAFKA_PROJECT_NAME,
                "down",
                "-v",  # -v removes volumes for clean state
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
    from scalo.kafka.config import ADMIN_DEFAULTS, config_from_env, merge_config

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
def kafka_config():
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

    yield config

    _stop_docker_kafka()


@pytest.fixture(scope="session")
def kafka_config_local_only():
    """
    Provide Kafka configuration forcing local Docker only.

    Skips remote Kafka even if configured in .env.
    Useful for testing the Docker fallback path.
    """
    config, source = _get_kafka_config_for_env(force_local=True)
    if config is None:
        pytest.skip("No local Kafka available. Run: docker compose -f docker-compose.kafka.yml up -d")

    yield config

    _stop_docker_kafka()


def cleanup_hung_processes():
    """
    Kill hung background processes from previous test runs.

    Uses LIB-specific labels to avoid killing other projects' processes.
    """
    # Kill processes with LIB test labels
    scalo_patterns = [
        "TEST_HELM",
        "TEST_K8S",
        "TEST_DOCKER",
        "TEST_MINIKUBE",
    ]

    for pattern in scalo_patterns:
        try:
            subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, Exception):
            pass  # Best effort cleanup

    # Also kill generic hung Kubernetes commands (broad cleanup)
    generic_patterns = [
        "minikube ssh.*docker login",
        "kubectl.*helm-scalo",  # scalo-specific namespace
        "helm install.*scalo",  # scalo-specific releases
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


# =============================================================================
# OpenBao / Vault Integration Test Support
# =============================================================================

OPENBAO_DOCKER_COMPOSE = Path(__file__).parent.parent / "docker-compose.openbao.yml"
OPENBAO_CONTAINER_NAME = "scalo-openbao"
OPENBAO_PROJECT_NAME = "scalo-test"  # Same project as Kafka for shared cleanup
OPENBAO_DEFAULT_ADDR = "http://localhost:8200"
OPENBAO_DEFAULT_TOKEN = "scalo-test-root"

_openbao_started_by_tests = False


def _is_our_openbao_container_running() -> bool:
    """Check if our specific test OpenBao container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", OPENBAO_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and "true" in result.stdout.lower()
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _check_openbao_ready(addr: str, timeout: float = 2.0) -> bool:
    """Probe Vault /v1/sys/health. Healthy when 200 (sealed/unsealed both fine for our tests)."""
    try:
        import urllib.request

        with urllib.request.urlopen(f"{addr}/v1/sys/health", timeout=timeout):  # noqa: S310 -- local-only test fixture
            return True
    except Exception:
        return False


def _start_docker_openbao() -> bool:
    """Start local OpenBao via docker-compose if not running."""
    global _openbao_started_by_tests

    if not OPENBAO_DOCKER_COMPOSE.exists():
        return False

    try:
        if _is_our_openbao_container_running():
            return True

        if _check_openbao_ready(OPENBAO_DEFAULT_ADDR, timeout=1.0):
            print("\n  Found existing OpenBao on localhost:8200 (not started by tests)")
            return True

        print("\n  Starting local Docker OpenBao (scalo-test)...")
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(OPENBAO_DOCKER_COMPOSE),
                "-p",
                OPENBAO_PROJECT_NAME,
                "up",
                "-d",
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )

        for i in range(30):
            if _check_openbao_ready(OPENBAO_DEFAULT_ADDR, timeout=1.0):
                print(f"  Docker OpenBao ready after {i + 1}s")
                _openbao_started_by_tests = True
                return True
            time.sleep(1)

        print("  Docker OpenBao failed to start within 30s")
        return False
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  Failed to start Docker OpenBao: {e}")
        return False


def _stop_docker_openbao() -> None:
    """Stop Docker OpenBao if we started it."""
    global _openbao_started_by_tests

    if not _openbao_started_by_tests or not OPENBAO_DOCKER_COMPOSE.exists():
        return

    try:
        print("\n  Stopping Docker OpenBao (scalo-test)...")
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(OPENBAO_DOCKER_COMPOSE),
                "-p",
                OPENBAO_PROJECT_NAME,
                "down",
                "-v",
            ],
            capture_output=True,
            timeout=30,
        )
        _openbao_started_by_tests = False
        print("  Docker OpenBao stopped and cleaned up")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  Failed to stop Docker OpenBao: {e}")


@pytest.fixture(scope="session")
def openbao_endpoint():
    """OpenBao address + token. Cascade: existing local instance → docker compose → skip.

    Yields a (addr, token) tuple for tests to construct an OpenBaoConfig.
    Mirrors the Kafka fixture pattern earlier in this file.
    """
    if _check_openbao_ready(OPENBAO_DEFAULT_ADDR, timeout=1.0):
        # Use existing local instance -- token may be different; honour env if set
        token = os.environ.get("OPENBAO_DEV_ROOT_TOKEN", OPENBAO_DEFAULT_TOKEN)
        yield (OPENBAO_DEFAULT_ADDR, token)
        return

    if _start_docker_openbao():
        yield (OPENBAO_DEFAULT_ADDR, OPENBAO_DEFAULT_TOKEN)
        _stop_docker_openbao()
        return

    pytest.skip(
        "OpenBao not available. Set up local Vault on :8200 or run: docker compose -f docker-compose.openbao.yml up -d"
    )
