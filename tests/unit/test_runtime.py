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
        assert paths.cache_dir == Path("/app/cache")
        assert paths.run_dir == Path("/run/test-app")

    def test_force_local_mode(self):
        """Test forced local mode."""
        runtime = RuntimeEnvironment("test-app", force_mode="local")
        paths = runtime.detect_runtime()

        assert paths.is_container is False
        assert "test-app" in str(paths.config_dir)
        assert "test-app" in str(paths.data_dir)
        assert "test-app" in str(paths.temp_dir)
        assert paths.log_dir is not None
        assert paths.cache_dir is not None
        assert "test-app" in str(paths.cache_dir)

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
        """Test local paths on Linux (daemon/CLI conventions)."""
        runtime = RuntimeEnvironment("my-app", force_mode="local")
        paths = runtime.detect_runtime()

        home = Path.home()
        # Non-root user: ~/.my-app/* structure
        assert paths.config_dir == home / ".my-app/config"
        assert paths.data_dir == home / ".my-app/data"
        assert paths.temp_dir == Path(f"/tmp/my-app-{os.getuid()}")
        assert paths.log_dir == home / ".my-app/logs"

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-specific test")
    def test_local_paths_macos(self):
        """Test local paths on macOS (daemon/CLI conventions)."""
        runtime = RuntimeEnvironment("my-app", force_mode="local")
        paths = runtime.detect_runtime()

        home = Path.home()
        # Non-root user: ~/.my-app/* structure (same as Linux)
        assert paths.config_dir == home / ".my-app/config"
        assert paths.data_dir == home / ".my-app/data"

    def test_container_detection_k8s_serviceaccount(self):
        """Test container detection via K8s service account (highest priority)."""
        runtime = RuntimeEnvironment("test-app")

        def mock_exists_k8s(self):
            return str(self) == "/var/run/secrets/kubernetes.io/serviceaccount"

        with mock.patch.object(Path, "exists", mock_exists_k8s):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "k8s_serviceaccount"

    def test_container_detection_kubernetes(self):
        """Test container detection via Kubernetes env."""
        runtime = RuntimeEnvironment("test-app")

        with mock.patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "10.0.0.1"}), mock.patch(
            "pathlib.Path.exists", return_value=False
        ):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "kubernetes"

    def test_container_detection_dockerenv(self):
        """Test container detection via /.dockerenv."""
        runtime = RuntimeEnvironment("test-app")

        def mock_exists_docker(self):
            return str(self) == "/.dockerenv"

        with mock.patch.object(Path, "exists", mock_exists_docker), mock.patch.dict(os.environ, {}, clear=True):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "dockerenv"

    def test_container_detection_cgroups_proc1(self):
        """Test container detection via /proc/1/cgroup."""
        runtime = RuntimeEnvironment("test-app")

        mock_open = mock.mock_open(read_data="12:memory:/kubepods/pod123")
        with mock.patch("builtins.open", mock_open), mock.patch("pathlib.Path.exists", return_value=False), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "cgroups_cgroup"

    def test_container_detection_cgroups_docker(self):
        """Test container detection via cgroups with docker pattern."""
        runtime = RuntimeEnvironment("test-app")

        mock_open = mock.mock_open(read_data="12:memory:/docker/abc123")
        with mock.patch("builtins.open", mock_open), mock.patch("pathlib.Path.exists", return_value=False), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "cgroups_cgroup"

    def test_container_detection_cgroups_containerd(self):
        """Test container detection via cgroups with containerd pattern."""
        runtime = RuntimeEnvironment("test-app")

        mock_open = mock.mock_open(read_data="0::/system.slice/containerd.service")
        with mock.patch("builtins.open", mock_open), mock.patch("pathlib.Path.exists", return_value=False), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "cgroups_cgroup"

    def test_container_detection_mountinfo(self):
        """Test container detection via /proc/self/mountinfo."""
        runtime = RuntimeEnvironment("test-app")

        # Mock /proc/1/cgroup to not match, then mountinfo to match
        def mock_open_mountinfo(path, *args, **kwargs):
            if "cgroup" in path:
                return mock.mock_open(read_data="0::/user.slice")(path, *args, **kwargs)
            elif "mountinfo" in path:
                return mock.mock_open(read_data="overlay /app overlay rw")(path, *args, **kwargs)
            else:
                raise FileNotFoundError

        with mock.patch("builtins.open", side_effect=mock_open_mountinfo), mock.patch(
            "pathlib.Path.exists", return_value=False
        ), mock.patch.dict(os.environ, {}, clear=True):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "mountinfo"

    def test_container_detection_env_vars(self):
        """Test container detection via container-specific env vars."""
        runtime = RuntimeEnvironment("test-app")

        # Test various container env vars
        for env_var in ["container", "DOCKER_CONTAINER", "ECS_CONTAINER_METADATA_URI"]:
            with mock.patch("pathlib.Path.exists", return_value=False), mock.patch.dict(
                os.environ, {env_var: "true"}, clear=True
            ), mock.patch("builtins.open", side_effect=FileNotFoundError):
                is_container, method = runtime._is_container()

                assert is_container is True
                assert method == f"env_{env_var.lower()}"

    def test_container_detection_pid1_with_init_name(self):
        """Test container detection via PID 1 with init process name."""
        runtime = RuntimeEnvironment("test-app")

        # Mock PID 1 with non-systemd init (e.g., tini, sh, python)
        mock_open = mock.mock_open(read_data="tini")
        with mock.patch("os.getpid", return_value=1), mock.patch("builtins.open", mock_open), mock.patch(
            "pathlib.Path.exists", return_value=False
        ), mock.patch.dict(os.environ, {}, clear=True):
            is_container, method = runtime._is_container()

            assert is_container is True
            assert method == "pid1_tini"

    def test_container_detection_pid1_systemd_not_container(self):
        """Test PID 1 with systemd is NOT detected as container."""
        runtime = RuntimeEnvironment("test-app")

        # Mock PID 1 with systemd (not a container)
        mock_open = mock.mock_open(read_data="systemd")
        with mock.patch("os.getpid", return_value=1), mock.patch("builtins.open", mock_open), mock.patch(
            "pathlib.Path.exists", return_value=False
        ), mock.patch.dict(os.environ, {}, clear=True):
            is_container, method = runtime._is_container()

            # Should NOT detect as container (systemd is normal init)
            assert is_container is False
            assert method == "none"

    def test_container_detection_none(self):
        """Test no container detection (local mode)."""
        runtime = RuntimeEnvironment("test-app")

        with (
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("os.getpid", return_value=1234),
            mock.patch("builtins.open", side_effect=FileNotFoundError),
        ):
            is_container, method = runtime._is_container()

            assert is_container is False
            assert method == "none"

    def test_container_detection_priority_order(self):
        """Test detection priority: K8s serviceaccount > K8s env > dockerenv."""
        runtime = RuntimeEnvironment("test-app")

        # Mock all detection methods returning true, verify K8s serviceaccount wins
        def mock_exists_all(self):
            return str(self) in ["/var/run/secrets/kubernetes.io/serviceaccount", "/.dockerenv"]

        with mock.patch.object(Path, "exists", mock_exists_all), mock.patch.dict(
            os.environ, {"KUBERNETES_SERVICE_HOST": "10.0.0.1"}
        ):
            is_container, method = runtime._is_container()

            # K8s serviceaccount should be detected first (highest priority)
            assert is_container is True
            assert method == "k8s_serviceaccount"

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
        assert paths.cache_dir is None
        assert paths.run_dir is None
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

    def test_runtime_paths_with_cache_and_run(self):
        """Test RuntimePaths with cache and run directories."""
        paths = RuntimePaths(
            config_dir=Path("/app/config"),
            data_dir=Path("/app/data"),
            temp_dir=Path("/app/tmp"),
            cache_dir=Path("/app/cache"),
            run_dir=Path("/run/myapp"),
            is_container=True,
            detection_method="kubernetes",
        )

        assert paths.cache_dir == Path("/app/cache")
        assert paths.run_dir == Path("/run/myapp")
        assert paths.effective_cache_dir == Path("/app/cache")

    def test_effective_cache_dir_with_explicit_cache(self):
        """Test effective_cache_dir returns explicit cache_dir when set."""
        paths = RuntimePaths(
            config_dir=Path("/app/config"),
            data_dir=Path("/app/data"),
            temp_dir=Path("/app/tmp"),
            cache_dir=Path("/app/cache"),
            is_container=True,
            detection_method="test",
        )

        assert paths.effective_cache_dir == Path("/app/cache")

    def test_effective_cache_dir_fallback_to_data(self):
        """Test effective_cache_dir falls back to data_dir/cache when cache_dir is None."""
        paths = RuntimePaths(
            config_dir=Path("/app/config"),
            data_dir=Path("/app/data"),
            temp_dir=Path("/app/tmp"),
            cache_dir=None,
            is_container=True,
            detection_method="test",
        )

        assert paths.effective_cache_dir == Path("/app/data/cache")


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
        # Force HOME to tmp_path for testing (daemon paths use ~/.appname)
        monkeypatch.setenv("HOME", str(tmp_path))

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

        # Daemon paths: ~/.my-special-app/*
        assert ".my-special-app" in str(paths.config_dir)
        assert ".my-special-app" in str(paths.data_dir)
        assert "my-special-app" in str(paths.temp_dir)
