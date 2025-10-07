"""Unit tests for hyperlib.runtime module."""

import os
import platform
from pathlib import Path
from unittest import mock

import pytest

from hyperlib.runtime import RuntimeEnvironment, RuntimePaths, get_runtime_paths


class TestRuntimeEnvironment:
    """Test RuntimeEnvironment class."""

    def test_init(self):
        """Test RuntimeEnvironment initialization."""
        runtime = RuntimeEnvironment("test-app")
        assert runtime.app_name == "test-app"
        assert runtime.force_mode is None

    def test_init_with_force_mode(self):
        """Test RuntimeEnvironment with forced mode."""
        runtime = RuntimeEnvironment("test-app", force_mode="container")
        assert runtime.force_mode == "container"

    def test_force_container_mode(self):
        """Test forced container mode."""
        runtime = RuntimeEnvironment("test-app", force_mode="container")
        paths = runtime.detect_runtime()

        assert paths.is_container is True
        assert paths.config_dir == Path("/app/config")
        assert paths.data_dir == Path("/app/data")
        assert paths.temp_dir == Path("/app/tmp")
        assert paths.log_dir is None  # Container logs to stdout

    def test_force_local_mode(self):
        """Test forced local mode."""
        runtime = RuntimeEnvironment("test-app", force_mode="local")
        paths = runtime.detect_runtime()

        assert paths.is_container is False
        assert "test-app" in str(paths.config_dir)
        assert "test-app" in str(paths.data_dir)
        assert "test-app" in str(paths.temp_dir)
        assert paths.log_dir is not None

    def test_container_paths_structure(self):
        """Test container paths follow K8s conventions."""
        runtime = RuntimeEnvironment("my-service", force_mode="container")
        paths = runtime.detect_runtime()

        # Standard K8s mount points
        assert paths.config_dir == Path("/app/config")
        assert paths.data_dir == Path("/app/data")
        assert paths.temp_dir == Path("/app/tmp")
        assert paths.log_dir is None
        assert paths.detection_method == "forced"

    @pytest.mark.skipif(platform.system() == "Windows", reason="Unix-specific test")
    def test_local_paths_linux(self):
        """Test local paths on Linux (XDG)."""
        runtime = RuntimeEnvironment("my-app", force_mode="local")
        paths = runtime.detect_runtime()

        home = Path.home()
        assert paths.config_dir == home / ".config/my-app"
        assert paths.data_dir == home / ".local/share/my-app"
        assert paths.temp_dir == Path("/tmp/my-app")
        assert paths.log_dir == home / ".local/share/my-app/logs"

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-specific test")
    def test_local_paths_macos(self):
        """Test local paths on macOS."""
        runtime = RuntimeEnvironment("my-app", force_mode="local")
        paths = runtime.detect_runtime()

        assert "Library/Application Support" in str(paths.config_dir)
        assert "my-app" in str(paths.config_dir)

    def test_container_detection_dockerenv(self):
        """Test container detection via /.dockerenv."""
        runtime = RuntimeEnvironment("test-app")

        with mock.patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "dockerenv"

    def test_container_detection_kubernetes(self):
        """Test container detection via Kubernetes env."""
        runtime = RuntimeEnvironment("test-app")

        with mock.patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "10.0.0.1"}):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "kubernetes"

    def test_container_detection_cgroups(self):
        """Test container detection via cgroups."""
        runtime = RuntimeEnvironment("test-app")

        mock_open = mock.mock_open(read_data="12:memory:/kubepods/pod123")
        with mock.patch("builtins.open", mock_open), mock.patch("pathlib.Path.exists", return_value=False):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "cgroups"

    def test_container_detection_none(self):
        """Test no container detection (local mode)."""
        runtime = RuntimeEnvironment("test-app")

        with (
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("os.getpid", return_value=1234),
        ):
            is_container, method = runtime._is_container()

            assert is_container is False
            assert method == "none"

    def test_ensure_directories_local(self, tmp_path):
        """Test directory creation in local mode."""
        runtime = RuntimeEnvironment("test-app", force_mode="local")

        # Create custom paths using tmp_path
        paths = RuntimePaths(
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            temp_dir=tmp_path / "tmp",
            log_dir=tmp_path / "logs",
            is_container=False,
            detection_method="test",
        )

        runtime.ensure_directories(paths)

        assert paths.config_dir.exists()
        assert paths.data_dir.exists()
        assert paths.temp_dir.exists()
        assert paths.log_dir.exists()

    def test_ensure_directories_container(self, tmp_path):
        """Test directory creation in container mode."""
        runtime = RuntimeEnvironment("test-app", force_mode="container")

        # Create custom paths using tmp_path
        paths = RuntimePaths(
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
            temp_dir=tmp_path / "tmp",
            log_dir=None,
            is_container=True,
            detection_method="test",
        )

        # Without create_config, config_dir should NOT be created in container mode
        runtime.ensure_directories(paths, create_config=False)

        assert not paths.config_dir.exists()  # Not created in container mode
        assert paths.data_dir.exists()
        assert paths.temp_dir.exists()

        # With create_config, config_dir should be created
        runtime.ensure_directories(paths, create_config=True)
        assert paths.config_dir.exists()


class TestRuntimePaths:
    """Test RuntimePaths dataclass."""

    def test_runtime_paths_creation(self):
        """Test RuntimePaths creation."""
        paths = RuntimePaths(
            config_dir=Path("/app/config"),
            data_dir=Path("/app/data"),
            temp_dir=Path("/app/tmp"),
            is_container=True,
            detection_method="kubernetes",
        )

        assert paths.config_dir == Path("/app/config")
        assert paths.data_dir == Path("/app/data")
        assert paths.temp_dir == Path("/app/tmp")
        assert paths.log_dir is None
        assert paths.is_container is True
        assert paths.detection_method == "kubernetes"

    def test_runtime_paths_with_logs(self):
        """Test RuntimePaths with log directory."""
        paths = RuntimePaths(
            config_dir=Path("/home/user/.config/app"),
            data_dir=Path("/home/user/.local/share/app"),
            temp_dir=Path("/tmp/app"),
            log_dir=Path("/home/user/.local/share/app/logs"),
            is_container=False,
            detection_method="local",
        )

        assert paths.log_dir == Path("/home/user/.local/share/app/logs")
        assert paths.is_container is False


class TestConvenienceFunction:
    """Test get_runtime_paths convenience function."""

    def test_get_runtime_paths_local(self, tmp_path):
        """Test convenience function in local mode."""
        with (
            mock.patch("hyperlib.runtime.RuntimeEnvironment.detect_runtime") as mock_detect,
            mock.patch("hyperlib.runtime.RuntimeEnvironment.ensure_directories"),
        ):
            mock_paths = RuntimePaths(
                config_dir=tmp_path / "config",
                data_dir=tmp_path / "data",
                temp_dir=tmp_path / "tmp",
                log_dir=tmp_path / "logs",
                is_container=False,
                detection_method="local",
            )
            mock_detect.return_value = mock_paths

            paths = get_runtime_paths("test-app")

            assert paths.config_dir == tmp_path / "config"
            assert paths.data_dir == tmp_path / "data"
            assert paths.is_container is False

    def test_get_runtime_paths_container(self):
        """Test convenience function in container mode."""
        with (
            mock.patch("hyperlib.runtime.RuntimeEnvironment.detect_runtime") as mock_detect,
            mock.patch("hyperlib.runtime.RuntimeEnvironment.ensure_directories"),
        ):
            mock_paths = RuntimePaths(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
                log_dir=None,
                is_container=True,
                detection_method="kubernetes",
            )
            mock_detect.return_value = mock_paths

            paths = get_runtime_paths("test-app")

            assert paths.config_dir == Path("/app/config")
            assert paths.is_container is True

    def test_get_runtime_paths_no_ensure(self):
        """Test convenience function without directory creation."""
        with mock.patch("hyperlib.runtime.RuntimeEnvironment.detect_runtime") as mock_detect, mock.patch(
            "hyperlib.runtime.RuntimeEnvironment.ensure_directories"
        ) as mock_ensure:
            mock_paths = RuntimePaths(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
                is_container=True,
                detection_method="test",
            )
            mock_detect.return_value = mock_paths

            get_runtime_paths("test-app", ensure_dirs=False)

            # ensure_directories should NOT be called
            mock_ensure.assert_not_called()


class TestIntegration:
    """Integration tests for runtime environment."""

    def test_full_workflow_local(self, tmp_path, monkeypatch):
        """Test full workflow in local mode."""
        # Force XDG paths to tmp_path for testing
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

        runtime = RuntimeEnvironment("my-test-app", force_mode="local")
        paths = runtime.detect_runtime()
        runtime.ensure_directories(paths)

        # Verify directories were created
        assert paths.config_dir.exists()
        assert paths.data_dir.exists()
        assert paths.temp_dir.exists()

        # Test writing files
        config_file = paths.config_dir / "settings.yaml"
        config_file.write_text("test: true")
        assert config_file.exists()

        data_file = paths.data_dir / "state.db"
        data_file.write_text("data")
        assert data_file.exists()

    def test_app_name_in_paths(self):
        """Test app name appears in local paths."""
        runtime = RuntimeEnvironment("my-special-app", force_mode="local")
        paths = runtime.detect_runtime()

        assert "my-special-app" in str(paths.config_dir)
        assert "my-special-app" in str(paths.data_dir)
        assert "my-special-app" in str(paths.temp_dir)
