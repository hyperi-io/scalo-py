"""
HyperLib Runtime Environment - Unified path management for container and local deployment

Provides consistent directory structure regardless of deployment mode:
- Container: /app/config, /app/data, /app/tmp
- Local: ~/.config/appname, ~/.local/share/appname, /tmp/appname
"""

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from .logger import logger


@dataclass
class RuntimePaths:
    """
    Unified path configuration for application resources.

    Supports both containerized and local deployment with same semantics:
    - config_dir: Read-only configuration (ConfigMap in K8s, ~/.config locally)
    - data_dir: Persistent data (PVC in K8s, ~/.local/share locally)
    - temp_dir: Ephemeral data (EmptyDir in K8s, /tmp locally)
    - log_dir: Log output (stdout in container, file locally)
    """

    config_dir: Path
    data_dir: Path
    temp_dir: Path
    log_dir: Path | None = None

    # Runtime metadata
    is_container: bool = False
    detection_method: str = "unknown"


class RuntimeEnvironment:
    """
    Detect and configure runtime environment (container vs local).

    Provides unified path resolution for:
    - Configuration files (read-only)
    - Persistent data storage
    - Ephemeral/temporary files
    - Log output

    Automatically detects container environment and provides appropriate paths.
    """

    def __init__(self, app_name: str, force_mode: str | None = None):
        """
        Initialize runtime environment.

        Args:
            app_name: Application name (used for local paths)
            force_mode: Override detection ("container" or "local")
        """
        self.app_name = app_name
        self.force_mode = force_mode

    def detect_runtime(self) -> RuntimePaths:
        """
        Detect runtime environment and return appropriate paths.

        Detection order:
        1. force_mode override (if set)
        2. Container detection (cgroups, /.dockerenv, KUBERNETES_SERVICE_HOST)
        3. Fallback to local mode
        """

        # Override detection if requested
        if self.force_mode == "container":
            return self._get_container_paths()
        elif self.force_mode == "local":
            return self._get_local_paths()

        # Auto-detect container environment
        is_container, method = self._is_container()

        if is_container:
            logger.info(f"Container environment detected ({method})")
            return self._get_container_paths(detection_method=method)
        else:
            logger.info("Local environment detected")
            return self._get_local_paths()

    def _is_container(self) -> tuple[bool, str]:
        """
        Detect if running inside a container.

        Returns:
            (is_container, detection_method)
        """

        # Method 1: Check for /.dockerenv (Docker)
        if Path("/.dockerenv").exists():
            return True, "dockerenv"

        # Method 2: Check for Kubernetes environment
        if os.getenv("KUBERNETES_SERVICE_HOST"):
            return True, "kubernetes"

        # Method 3: Check cgroups (Docker/K8s)
        try:
            with open("/proc/1/cgroup") as f:
                content = f.read()
                if "docker" in content or "kubepods" in content:
                    return True, "cgroups"
        except (FileNotFoundError, PermissionError):
            pass

        # Method 4: Check if running as PID 1 (container init process)
        if os.getpid() == 1:
            return True, "pid1"

        # Default: local environment
        return False, "none"

    def _get_container_paths(self, detection_method: str = "forced") -> RuntimePaths:
        """
        Get container-standard paths.

        Follows Kubernetes/Docker conventions:
        - /app/config - ConfigMap (read-only configuration)
        - /app/data   - PVC (persistent data)
        - /app/tmp    - EmptyDir (ephemeral storage)
        - stdout/stderr for logs (captured by container runtime)
        """
        return RuntimePaths(
            config_dir=Path("/app/config"),
            data_dir=Path("/app/data"),
            temp_dir=Path("/app/tmp"),
            log_dir=None,  # Container logs go to stdout
            is_container=True,
            detection_method=detection_method,
        )

    def _get_local_paths(self) -> RuntimePaths:
        """
        Get XDG-compliant local paths for development/testing.

        Follows XDG Base Directory specification:
        - ~/.config/appname     - Configuration
        - ~/.local/share/appname - Persistent data
        - /tmp/appname          - Ephemeral storage
        - ~/.local/share/appname/logs - Log files
        """

        system = platform.system()
        home = Path.home()

        if system == "Linux":
            # XDG Base Directory specification
            config_base = Path(os.getenv("XDG_CONFIG_HOME", home / ".config"))
            data_base = Path(os.getenv("XDG_DATA_HOME", home / ".local/share"))
            cache_base = Path(os.getenv("XDG_CACHE_HOME", home / ".cache"))

        elif system == "Darwin":  # macOS
            config_base = home / "Library/Application Support"
            data_base = home / "Library/Application Support"
            cache_base = home / "Library/Caches"

        elif system == "Windows":
            # Windows paths
            appdata = Path(os.getenv("APPDATA", home / "AppData/Roaming"))
            localappdata = Path(os.getenv("LOCALAPPDATA", home / "AppData/Local"))
            config_base = appdata
            data_base = localappdata
            cache_base = localappdata

        else:
            # Fallback for unknown systems
            config_base = home / ".config"
            data_base = home / ".local/share"
            cache_base = home / ".cache"

        # Application-specific paths
        config_dir = config_base / self.app_name
        data_dir = data_base / self.app_name
        temp_dir = Path("/tmp") / self.app_name if system != "Windows" else cache_base / self.app_name / "temp"
        log_dir = data_dir / "logs"

        return RuntimePaths(
            config_dir=config_dir,
            data_dir=data_dir,
            temp_dir=temp_dir,
            log_dir=log_dir,
            is_container=False,
            detection_method="local",
        )

    def ensure_directories(self, paths: RuntimePaths, create_config: bool = False):
        """
        Ensure required directories exist.

        Args:
            paths: RuntimePaths to create
            create_config: Create config_dir (normally read-only in containers)
        """

        # Always create data and temp directories
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        paths.temp_dir.mkdir(parents=True, exist_ok=True)

        # Create log directory if specified
        if paths.log_dir:
            paths.log_dir.mkdir(parents=True, exist_ok=True)

        # Only create config in local mode (containers mount ConfigMaps)
        if create_config or not paths.is_container:
            paths.config_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Ensured directories for {self.app_name}")
        logger.debug(f"  Config: {paths.config_dir}")
        logger.debug(f"  Data: {paths.data_dir}")
        logger.debug(f"  Temp: {paths.temp_dir}")
        if paths.log_dir:
            logger.debug(f"  Logs: {paths.log_dir}")


# Convenience function
def get_runtime_paths(app_name: str, ensure_dirs: bool = True) -> RuntimePaths:
    """
    Get runtime paths for application (auto-detect environment).

    Args:
        app_name: Application name
        ensure_dirs: Create directories if they don't exist

    Returns:
        RuntimePaths with appropriate paths for current environment

    Example:
        paths = get_runtime_paths("my-app")
        config_file = paths.config_dir / "app.yaml"
        data_file = paths.data_dir / "state.db"
    """
    runtime = RuntimeEnvironment(app_name)
    paths = runtime.detect_runtime()

    if ensure_dirs:
        runtime.ensure_directories(paths)

    return paths
