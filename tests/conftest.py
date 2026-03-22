"""Pytest configuration and fixtures for hyperi-pylib tests."""

import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

# Enable DEBUG logging for all tests
os.environ["LOG_LEVEL"] = "DEBUG"

# Disable OTel OTLP exporter in tests — prevents atexit export errors
# when no collector is running (causes exit code 1 even with all tests passing)

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
KAFKA_CONTAINER_NAME = "hyperi-pylib-kafka"
KAFKA_PROJECT_NAME = "hyperi-pylib-test"  # Unique project name to avoid conflicts

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
        print("\n  Starting local Docker Kafka (hyperi-pylib-test)...")
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
        print("\n  Stopping Docker Kafka (hyperi-pylib-test)...")
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
    from hyperi_pylib.kafka.config import ADMIN_DEFAULTS, config_from_env, merge_config

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
        pytest.skip("No local Kafka available. Run: docker compose -f docker-compose.kafka.yml up -d")

    # Register cleanup finalizer
    request.addfinalizer(_stop_docker_kafka)

    return config


def cleanup_hung_processes():
    """
    Kill hung background processes from previous test runs.

    Uses HYPERI_LIB-specific labels to avoid killing other projects' processes.
    """
    # Kill processes with HYPERI_LIB test labels
    hyperi_pylib_patterns = [
        "HYPERI_LIB_TEST_HELM",
        "HYPERI_LIB_TEST_K8S",
        "HYPERI_LIB_TEST_DOCKER",
        "HYPERI_LIB_TEST_MINIKUBE",
    ]

    for pattern in hyperi_pylib_patterns:
        try:
            subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, Exception):
            pass  # Best effort cleanup

    # Also kill generic hung Kubernetes commands (broad cleanup)
    generic_patterns = [
        "minikube ssh.*docker login",
        "kubectl.*helm-hyperi-pylib",  # hyperi-pylib-specific namespace
        "helm install.*hyperi-pylib",  # hyperi-pylib-specific releases
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
# PostgreSQL Integration Test Support
# =============================================================================

POSTGRES_DOCKER_COMPOSE = Path(__file__).parent.parent / "docker-compose.postgres.yml"
POSTGRES_CONTAINER_NAME = "hyperi-pylib-postgres"
POSTGRES_PROJECT_NAME = "hyperi-pylib-test"  # Same project name as Kafka for simplicity

# Default connection settings for Docker PostgreSQL
POSTGRES_DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/hyperi_pylib_test"

# Track if we started Docker PostgreSQL (so we know to clean it up)
_postgres_started_by_tests = False


def _check_postgres_connection(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if PostgreSQL is reachable via TCP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except (TimeoutError, OSError):
        return False


def _is_our_postgres_container_running() -> bool:
    """Check if our specific test PostgreSQL container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", POSTGRES_CONTAINER_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and "true" in result.stdout.lower()
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _start_docker_postgres() -> bool:
    """
    Start local Docker PostgreSQL if not running.

    Uses a unique project name to avoid conflicts with other PostgreSQL containers.
    """
    global _postgres_started_by_tests

    if not POSTGRES_DOCKER_COMPOSE.exists():
        return False

    try:
        # Check if our container is already running
        if _is_our_postgres_container_running():
            return True

        # Check if something else is using port 5432
        if _check_postgres_connection("localhost", 5432, timeout=1.0):
            # Port is in use by something else - use it but don't track for cleanup
            print("\n  Found existing PostgreSQL on localhost:5432 (not started by tests)")
            return True

        # Start the container with unique project name
        print("\n  Starting local Docker PostgreSQL (hyperi-pylib-test)...")
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(POSTGRES_DOCKER_COMPOSE),
                "-p",
                POSTGRES_PROJECT_NAME,
                "up",
                "-d",
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )

        # Wait for PostgreSQL to be ready (up to 30 seconds)
        for i in range(30):
            if _check_postgres_connection("localhost", 5432, timeout=1.0):
                print(f"  Docker PostgreSQL ready after {i + 1}s")
                _postgres_started_by_tests = True
                return True
            time.sleep(1)

        print("  Docker PostgreSQL failed to start within 30s")
        return False

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  Failed to start Docker PostgreSQL: {e}")
        return False


def _stop_docker_postgres() -> None:
    """Stop Docker PostgreSQL if we started it."""
    global _postgres_started_by_tests

    if not _postgres_started_by_tests:
        return

    if not POSTGRES_DOCKER_COMPOSE.exists():
        return

    try:
        print("\n  Stopping Docker PostgreSQL (hyperi-pylib-test)...")
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(POSTGRES_DOCKER_COMPOSE),
                "-p",
                POSTGRES_PROJECT_NAME,
                "down",
                "-v",  # -v removes volumes for clean state
            ],
            capture_output=True,
            timeout=30,
        )
        _postgres_started_by_tests = False
        print("  Docker PostgreSQL stopped and cleaned up")
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  Failed to stop Docker PostgreSQL: {e}")


def _get_postgres_dsn_for_env(force_local: bool = False) -> tuple[str | None, str]:
    """
    Get PostgreSQL DSN based on environment.

    Args:
        force_local: If True, skip remote PostgreSQL and use local Docker only.

    Priority:
    1. Remote PostgreSQL from DFE_POSTGRES_* env vars if reachable (unless force_local)
    2. Local Docker PostgreSQL (localhost:5432) if reachable or can be started

    Returns:
        Tuple of (DSN string or None, source description)
    """
    # Try remote PostgreSQL from env first (unless forcing local)
    if not force_local:
        pg_host = os.environ.get("DFE_POSTGRES_HOST", "")
        if pg_host:
            pg_port = int(os.environ.get("DFE_POSTGRES_PORT", "5432"))
            if _check_postgres_connection(pg_host, pg_port, timeout=3.0):
                pg_user = os.environ.get("DFE_POSTGRES_USER", "postgres")
                pg_pass = os.environ.get("DFE_POSTGRES_PASSWORD", "")
                pg_db = os.environ.get("DFE_POSTGRES_DATABASE", "hyperi_pylib_test")
                dsn = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
                print(f"\n  Using remote PostgreSQL: {pg_host}:{pg_port}/{pg_db}")
                return dsn, "remote"

    # Try local Docker PostgreSQL
    if _check_postgres_connection("localhost", 5432, timeout=1.0) or _start_docker_postgres():
        print("\n  Using local Docker PostgreSQL: localhost:5432/hyperi_pylib_test")
        return POSTGRES_DEFAULT_DSN, "local"

    return None, "none"


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    """Check if any PostgreSQL is available for integration tests."""
    dsn, _ = _get_postgres_dsn_for_env()
    return dsn is not None


@pytest.fixture(scope="session")
def postgres_dsn(request):
    """
    Provide PostgreSQL DSN for integration tests.

    Automatically selects:
    1. Remote PostgreSQL (from DFE_POSTGRES_* env) if reachable
    2. Local Docker PostgreSQL if available or can be started
    3. Skips test if no PostgreSQL is available

    Cleans up Docker PostgreSQL after tests if we started it.
    """
    dsn, source = _get_postgres_dsn_for_env()
    if dsn is None:
        pytest.skip(
            "No PostgreSQL available. Set DFE_POSTGRES_HOST in .env or "
            "run: docker compose -f docker-compose.postgres.yml up -d"
        )

    # Register cleanup finalizer
    request.addfinalizer(_stop_docker_postgres)

    return dsn


@pytest.fixture(scope="session")
def postgres_dsn_local_only(request):
    """
    Provide PostgreSQL DSN forcing local Docker only.

    Skips remote PostgreSQL even if configured in env.
    Useful for testing the Docker fallback path.
    """
    dsn, source = _get_postgres_dsn_for_env(force_local=True)
    if dsn is None:
        pytest.skip("No local PostgreSQL available. Run: docker compose -f docker-compose.postgres.yml up -d")

    # Register cleanup finalizer
    request.addfinalizer(_stop_docker_postgres)

    return dsn
