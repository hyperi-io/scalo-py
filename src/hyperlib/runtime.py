"""
HyperLib Runtime Environment - Unified path management for container and local deployment

Provides consistent directory structure regardless of deployment mode:
- Container: {base}/config, {base}/data, {base}/tmp (base defaults to /app)
- Local: ~/.config/appname, ~/.local/share/appname, /tmp/appname

Container base path can be customized via CONTAINER_BASE_PATH environment variable.
Default: /app (can be changed to /mnt, /dfe, /opt/app, etc.)
"""

import os
import platform
import tempfile
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
    - cache_dir: Cache data (defaults to data_dir/cache if not set)
    - run_dir: Runtime state - PID files, sockets (optional)
    """

    config_dir: Path
    data_dir: Path
    temp_dir: Path
    log_dir: Path | None = None
    cache_dir: Path | None = None
    run_dir: Path | None = None

    # Runtime metadata
    is_container: bool = False
    detection_method: str = "unknown"

    @property
    def effective_cache_dir(self) -> Path:
        """Get cache directory, falling back to data_dir/cache if not explicitly set."""
        return self.cache_dir or (self.data_dir / "cache")


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

        Uses layered detection with high-confidence checks first:
        1. K8s service account token (100% reliable for K8s)
        2. Kubernetes environment variables
        3. Docker-specific files
        4. cgroups inspection (v1 and v2)
        5. Mountinfo inspection
        6. Container-specific env vars
        7. Init process check (PID 1)

        Returns:
            (is_container, detection_method)
        """

        # HIGH CONFIDENCE CHECKS (do these first)

        # 1. K8s service account token (100% reliable for K8s)
        if Path("/var/run/secrets/kubernetes.io/serviceaccount").exists():
            return True, "k8s_serviceaccount"

        # 2. Kubernetes env vars
        if os.getenv("KUBERNETES_SERVICE_HOST"):
            return True, "kubernetes"

        # 3. Docker-specific file
        if Path("/.dockerenv").exists():
            return True, "dockerenv"

        # MEDIUM CONFIDENCE CHECKS

        # 4. cgroups v1 and v2 (both /proc/1/cgroup and /proc/self/cgroup)
        for cgroup_file in ["/proc/1/cgroup", "/proc/self/cgroup"]:
            try:
                with open(cgroup_file) as f:
                    content = f.read()
                    if any(x in content for x in ["docker", "kubepods", "containerd", "crio"]):
                        return True, f"cgroups_{cgroup_file.split('/')[-1]}"
            except (FileNotFoundError, PermissionError):
                pass

        # 5. Mountinfo inspection (very reliable)
        try:
            with open("/proc/self/mountinfo") as f:
                content = f.read()
                if any(x in content for x in ["docker", "kubelet", "overlay", "containerd"]):
                    return True, "mountinfo"
        except (FileNotFoundError, PermissionError):
            pass

        # 6. Container-specific env vars
        container_vars = ["container", "DOCKER_CONTAINER", "ECS_CONTAINER_METADATA_URI"]
        for var in container_vars:
            if os.getenv(var):
                return True, f"env_{var.lower()}"

        # LOW CONFIDENCE CHECKS (only if nothing else matched)

        # 7. Init process check (PID 1 running non-systemd)
        if os.getpid() == 1:
            try:
                with open("/proc/1/comm") as f:
                    init_name = f.read().strip()
                    if init_name not in ["systemd", "init", "launchd"]:
                        return True, f"pid1_{init_name}"
            except (FileNotFoundError, PermissionError):
                return True, "pid1"

        # Default: local environment
        return False, "none"

    def _get_container_paths(self, detection_method: str = "forced") -> RuntimePaths:
        """
        Get container-standard paths.

        Base path can be overridden with CONTAINER_BASE_PATH environment variable.
        Default: /app

        Follows Kubernetes/Docker conventions:
        - {base}/config - ConfigMap (read-only configuration)
        - {base}/data   - PVC (persistent data)
        - {base}/tmp    - EmptyDir (ephemeral storage)
        - {base}/cache  - Cache data (can be EmptyDir or PVC)
        - /run/{app}    - Runtime state (PID files, sockets)
        - stdout/stderr for logs (captured by container runtime)

        Environment Variables:
            CONTAINER_BASE_PATH: Override base path (default: /app)
                Examples: /mnt, /dfe, /opt/app

        Example:
            >>> # Default: /app
            >>> runtime = RuntimeEnvironment("myapp")
            >>> paths = runtime.detect_runtime()
            >>> paths.config_dir
            Path('/app/config')

            >>> # Custom base: /mnt
            >>> os.environ["CONTAINER_BASE_PATH"] = "/mnt"
            >>> paths = runtime.detect_runtime()
            >>> paths.config_dir
            Path('/mnt/config')
        """
        # Get base path from environment or use /app default
        base_path = Path(os.getenv("CONTAINER_BASE_PATH", "/app"))

        return RuntimePaths(
            config_dir=base_path / "config",
            data_dir=base_path / "data",
            temp_dir=base_path / "tmp",
            log_dir=None,  # Container logs go to stdout
            cache_dir=base_path / "cache",
            run_dir=Path(f"/run/{self.app_name}"),
            is_container=True,
            detection_method=detection_method,
        )

    def _get_local_paths(self) -> RuntimePaths:
        """
        Get local paths for CLI tools and daemons.

        Follows Unix daemon/CLI conventions:
        - /etc/appname or ~/.appname/config       - Configuration
        - /var/lib/appname or ~/.appname/data     - Persistent data
        - /tmp/appname                            - Ephemeral storage
        - /var/log/appname or ~/.appname/logs     - Log files
        - /var/cache/appname or data/cache        - Cache data
        - /run/appname or /var/run/appname        - Runtime state (PID files, sockets)

        For non-root users: Everything under ~/.appname/
        For root/system: Standard Unix paths (/etc, /var/lib, /var/log, /var/cache, /run)
        """

        home = Path.home()

        # Check if running as root/system user
        is_root = os.getuid() == 0 if hasattr(os, "getuid") else False

        if is_root:
            # System daemon paths (traditional Unix)
            config_dir = Path("/etc") / self.app_name
            data_dir = Path("/var/lib") / self.app_name
            temp_dir = Path(tempfile.gettempdir()) / self.app_name
            log_dir = Path("/var/log") / self.app_name
            cache_dir = Path("/var/cache") / self.app_name
            run_dir = Path("/run") / self.app_name
        else:
            # User daemon/CLI paths
            app_home = home / f".{self.app_name}"
            config_dir = app_home / "config"
            data_dir = app_home / "data"
            temp_dir = Path(tempfile.gettempdir()) / f"{self.app_name}-{os.getuid()}"
            log_dir = app_home / "logs"
            cache_dir = app_home / "cache"
            run_dir = None  # Non-root doesn't typically use /run

        return RuntimePaths(
            config_dir=config_dir,
            data_dir=data_dir,
            temp_dir=temp_dir,
            log_dir=log_dir,
            cache_dir=cache_dir,
            run_dir=run_dir,
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

        # Create cache directory (use effective_cache_dir for fallback)
        paths.effective_cache_dir.mkdir(parents=True, exist_ok=True)

        # Create run directory if specified
        if paths.run_dir:
            try:
                paths.run_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # /run may require elevated permissions, skip silently
                logger.debug(f"Could not create run directory: {paths.run_dir}")

        # Only create config in local mode (containers mount ConfigMaps)
        if create_config or not paths.is_container:
            paths.config_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Ensured directories for {self.app_name}")
        logger.debug(f"  Config: {paths.config_dir}")
        logger.debug(f"  Data: {paths.data_dir}")
        logger.debug(f"  Temp: {paths.temp_dir}")
        logger.debug(f"  Cache: {paths.effective_cache_dir}")
        if paths.log_dir:
            logger.debug(f"  Logs: {paths.log_dir}")
        if paths.run_dir:
            logger.debug(f"  Run: {paths.run_dir}")


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
