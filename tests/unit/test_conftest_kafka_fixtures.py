# Project:   hs-pylib
# File:      tests/unit/test_conftest_kafka_fixtures.py
# Purpose:   Unit tests for Kafka fixture logic in conftest.py
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Unit tests for Kafka fixture helpers in conftest.py.

Tests the helper functions used by Kafka fixtures without requiring
actual Kafka or Docker connections.
"""

import importlib.util
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import conftest.py directly (it's not a normal module)
conftest_path = Path(__file__).parent.parent / "conftest.py"
spec = importlib.util.spec_from_file_location("conftest", conftest_path)
conftest = importlib.util.module_from_spec(spec)
sys.modules["conftest"] = conftest
spec.loader.exec_module(conftest)

# Now we can access the functions
KAFKA_CONTAINER_NAME = conftest.KAFKA_CONTAINER_NAME
KAFKA_DOCKER_COMPOSE = conftest.KAFKA_DOCKER_COMPOSE
KAFKA_PROJECT_NAME = conftest.KAFKA_PROJECT_NAME
_check_kafka_connection = conftest._check_kafka_connection
_get_kafka_config_for_env = conftest._get_kafka_config_for_env
_is_our_kafka_container_running = conftest._is_our_kafka_container_running


class TestKafkaConnectionCheck:
    """Tests for _check_kafka_connection helper."""

    def test_returns_true_when_connection_succeeds(self):
        """Should return True when TCP connection succeeds."""
        mock_socket = MagicMock()

        with patch("socket.socket", return_value=mock_socket):
            result = _check_kafka_connection("localhost", 9092, timeout=1.0)

        assert result is True
        mock_socket.settimeout.assert_called_once_with(1.0)
        mock_socket.connect.assert_called_once_with(("localhost", 9092))
        mock_socket.close.assert_called_once()

    def test_returns_false_on_socket_timeout(self):
        """Should return False when connection times out."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = TimeoutError("Connection timed out")

        with patch("socket.socket", return_value=mock_socket):
            result = _check_kafka_connection("localhost", 9092, timeout=1.0)

        assert result is False

    def test_returns_false_on_socket_error(self):
        """Should return False when connection is refused."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = OSError("Connection refused")

        with patch("socket.socket", return_value=mock_socket):
            result = _check_kafka_connection("localhost", 9092, timeout=1.0)

        assert result is False

    def test_returns_false_on_os_error(self):
        """Should return False on OS-level errors."""
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = OSError("Network unreachable")

        with patch("socket.socket", return_value=mock_socket):
            result = _check_kafka_connection("localhost", 9092, timeout=1.0)

        assert result is False

    def test_uses_provided_timeout(self):
        """Should use the timeout value provided."""
        mock_socket = MagicMock()

        with patch("socket.socket", return_value=mock_socket):
            _check_kafka_connection("localhost", 9092, timeout=5.0)

        mock_socket.settimeout.assert_called_once_with(5.0)

    def test_connects_to_correct_host_and_port(self):
        """Should connect to the specified host and port."""
        mock_socket = MagicMock()

        with patch("socket.socket", return_value=mock_socket):
            _check_kafka_connection("k8s.tyrell.com.au", 30092, timeout=1.0)

        mock_socket.connect.assert_called_once_with(("k8s.tyrell.com.au", 30092))


class TestKafkaContainerRunningCheck:
    """Tests for _is_our_kafka_container_running helper."""

    def test_returns_true_when_container_running(self):
        """Should return True when our container is running."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "true\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _is_our_kafka_container_running()

        assert result is True
        mock_run.assert_called_once()
        # Verify we're checking our specific container
        call_args = mock_run.call_args[0][0]
        assert KAFKA_CONTAINER_NAME in call_args

    def test_returns_false_when_container_not_running(self):
        """Should return False when container is not running."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "false\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _is_our_kafka_container_running()

        assert result is False

    def test_returns_false_when_container_not_found(self):
        """Should return False when container doesn't exist."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _is_our_kafka_container_running()

        assert result is False

    def test_returns_false_when_docker_not_available(self):
        """Should return False when docker command not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
            result = _is_our_kafka_container_running()

        assert result is False

    def test_returns_false_on_subprocess_error(self):
        """Should return False on subprocess errors."""
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("error")):
            result = _is_our_kafka_container_running()

        assert result is False


class TestKafkaConfigForEnv:
    """Tests for _get_kafka_config_for_env helper."""

    @patch.object(conftest, "_check_kafka_connection")
    @patch.object(conftest, "_start_docker_kafka")
    def test_returns_remote_config_when_available(self, mock_start_docker, mock_check_conn):
        """Should return remote config when remote Kafka is reachable."""
        # Remote Kafka is reachable
        mock_check_conn.return_value = True

        # Mock the kafka config module
        with patch.dict(
            "os.environ",
            {"KAFKA_BOOTSTRAP_SERVERS": "k8s.tyrell.com.au:30092"},
        ):
            config, source = conftest._get_kafka_config_for_env(force_local=False)

        assert source == "remote"
        assert config is not None
        assert "k8s.tyrell.com.au:30092" in config.get("bootstrap.servers", "")
        # Should not try to start Docker when remote is available
        mock_start_docker.assert_not_called()

    @patch.object(conftest, "_check_kafka_connection")
    @patch.object(conftest, "_start_docker_kafka")
    def test_returns_local_config_when_remote_unavailable(self, mock_start_docker, mock_check_conn):
        """Should fall back to local Docker when remote is unavailable."""
        # First call (remote check) fails, second call (local check) succeeds
        mock_check_conn.side_effect = [False, True]

        with patch.dict(
            "os.environ",
            {"KAFKA_BOOTSTRAP_SERVERS": "k8s.tyrell.com.au:30092"},
        ):
            config, source = conftest._get_kafka_config_for_env(force_local=False)

        assert source == "local"
        assert config is not None
        assert config.get("bootstrap.servers") == "localhost:9092"

    @patch.object(conftest, "_check_kafka_connection")
    @patch.object(conftest, "_start_docker_kafka")
    def test_force_local_skips_remote_check(self, mock_start_docker, mock_check_conn):
        """Should skip remote and use local when force_local=True."""
        mock_check_conn.return_value = True  # Local is available

        with patch.dict(
            "os.environ",
            {"KAFKA_BOOTSTRAP_SERVERS": "k8s.tyrell.com.au:30092"},
        ):
            config, source = conftest._get_kafka_config_for_env(force_local=True)

        assert source == "local"
        assert config is not None
        assert config.get("bootstrap.servers") == "localhost:9092"
        # Should only check local, not remote
        mock_check_conn.assert_called_once_with("localhost", 9092, timeout=1.0)

    @patch.object(conftest, "_check_kafka_connection")
    @patch.object(conftest, "_start_docker_kafka")
    def test_starts_docker_when_local_not_running(self, mock_start_docker, mock_check_conn):
        """Should start Docker when local Kafka not already running."""
        # Remote fails, local check fails, but Docker start succeeds
        mock_check_conn.return_value = False
        mock_start_docker.return_value = True

        with patch.dict(
            "os.environ",
            {"KAFKA_BOOTSTRAP_SERVERS": "k8s.tyrell.com.au:30092"},
        ):
            config, source = conftest._get_kafka_config_for_env(force_local=False)

        assert source == "local"
        mock_start_docker.assert_called_once()

    @patch.object(conftest, "_check_kafka_connection")
    @patch.object(conftest, "_start_docker_kafka")
    def test_returns_none_when_no_kafka_available(self, mock_start_docker, mock_check_conn):
        """Should return None when no Kafka is available."""
        mock_check_conn.return_value = False
        mock_start_docker.return_value = False

        with patch.dict("os.environ", {}, clear=True):
            config, source = conftest._get_kafka_config_for_env(force_local=True)

        assert config is None
        assert source == "none"


class TestKafkaFixtureConstants:
    """Tests for Kafka fixture constants."""

    def test_docker_compose_path_is_valid(self):
        """Docker compose file path should be valid."""
        assert KAFKA_DOCKER_COMPOSE.name == "docker-compose.kafka.yml"
        assert KAFKA_DOCKER_COMPOSE.exists(), f"Docker compose file not found at {KAFKA_DOCKER_COMPOSE}"

    def test_container_name_is_set(self):
        """Container name should be defined."""
        assert KAFKA_CONTAINER_NAME == "hs-pylib-kafka"

    def test_project_name_is_unique(self):
        """Project name should be unique to avoid conflicts."""
        assert KAFKA_PROJECT_NAME == "hs-pylib-test"
        # Should contain hs-pylib to identify it
        assert "hs-pylib" in KAFKA_PROJECT_NAME
