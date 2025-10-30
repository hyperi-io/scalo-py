"""
HyperLib Config - Standard Dynaconf Interface with Container Auto-Detection

Provides:
- Consistent configuration usage across ALL /src code
- Auto-detection of container environments (K8s, Docker, bare metal)
- Smart defaults for mount paths based on detected environment
- Container deployment patterns (daemon, API, one-shot)
"""

import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dynaconf import Dynaconf


# Container environment detection
def detect_environment() -> Literal["kubernetes", "docker", "container", "bare_metal"]:
    """
    Detect the current runtime environment.

    Returns:
        Environment type: "kubernetes", "docker", "container", or "bare_metal"
    """
    # K8s detection - check for service account token
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token"):
        if os.getenv("HYPERLIB_DEBUG"):
            print("Environment detected: Kubernetes")
        return "kubernetes"

    # Docker detection - check for .dockerenv file
    if os.path.exists("/.dockerenv"):
        if os.getenv("HYPERLIB_DEBUG"):
            print("Environment detected: Docker")
        return "docker"

    # Container detection via cgroups
    try:
        with open("/proc/1/cgroup") as f:
            cgroup_content = f.read()
            if "docker" in cgroup_content or "containerd" in cgroup_content:
                if os.getenv("HYPERLIB_DEBUG"):
                    print("Environment detected: Container (via cgroups)")
                return "container"
    except (FileNotFoundError, PermissionError):
        pass

    # Default to bare metal
    if os.getenv("HYPERLIB_DEBUG"):
        print("Environment detected: Bare metal")
    return "bare_metal"


@dataclass
class MountConfig:
    """
    Container mount configuration for standard disk locations.

    Follows K8s/HELM/Docker/DevOps patterns:

    Core paths (always detected):
    - config_dir: READ-ONLY configuration (ConfigMap/configs)
    - secrets_dir: READ-ONLY secrets (K8s Secret/Docker secrets)
    - data_dir: PERSISTENT data (PVC/volumes)
    - temp_dir: EPHEMERAL temporary files (EmptyDir/tmpfs)
    - logs_dir: Application logs (PVC/EmptyDir/stdout)

    Additional DevOps paths (auto-detected if present):
    - cache_dir: Application cache (Redis/computed data)
    - run_dir: Runtime state (PID files, sockets)
    """

    # Core paths
    config_dir: Path | None = None
    secrets_dir: Path | None = None
    data_dir: Path | None = None
    temp_dir: Path | None = None
    logs_dir: Path | None = None

    # Additional commonly used paths
    cache_dir: Path | None = None
    run_dir: Path | None = None

    def __post_init__(self):
        """Convert strings to Path objects and ensure directories exist"""
        # All fields in the dataclass
        all_fields = ["config_dir", "secrets_dir", "data_dir", "temp_dir", "logs_dir", "cache_dir", "run_dir"]

        # Read-only directories that shouldn't be created
        read_only_fields = ["config_dir", "secrets_dir"]

        for field in all_fields:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, Path(value))

            # Try to create directory if it doesn't exist (skip read-only dirs)
            if value and field not in read_only_fields:
                path = Path(value)
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except (PermissionError, OSError) as e:
                    if os.getenv("HYPERLIB_DEBUG"):
                        print(f"Could not create {field}: {e}")


def detect_helm_deployment() -> bool:
    """
    Detect if running in a HELM-deployed pod.

    HELM deployments typically have:
    - Specific labels (app.kubernetes.io/managed-by=Helm)
    - HELM-specific environment variables
    - Standard mount patterns (/config, /secrets, /data)
    """
    # Check for HELM-specific environment variables
    if os.getenv("HELM_RELEASE_NAME"):
        return True

    # Check for standard HELM mount points
    helm_mounts = ["/config", "/secrets", "/data"]
    if sum(Path(mount).exists() for mount in helm_mounts) >= 2:
        return True

    # Check K8s downward API for HELM labels
    try:
        labels_file = Path("/etc/podinfo/labels")
        if labels_file.exists():
            labels = labels_file.read_text()
            if "app.kubernetes.io/managed-by=Helm" in labels:
                return True
    except:
        pass

    return False


def detect_standard_mounts() -> dict[str, Path]:
    """
    Auto-detect standard mount points based on what exists.

    Returns dict of detected mount points.
    """
    detected = {}

    # Standard paths to check in priority order
    # Use the globally detected app name (respects K8s APP_NAME, etc.)
    app_name = APP_NAME

    mount_checks = {
        "config_dir": [
            "/config",  # HELM standard
            "/app/config",  # Docker standard
            f"/etc/{app_name}",  # Linux standard with app name
            "/etc/config",  # Generic Linux
            f"/opt/{app_name}/config",  # Alternative app-specific
        ],
        "secrets_dir": [
            "/secrets",  # HELM standard
            "/run/secrets",  # Docker secrets standard
            "/app/secrets",  # Docker app-specific
            f"/etc/{app_name}/secrets",  # Linux app-specific
            "/var/run/secrets",  # Alternative runtime secrets
        ],
        "data_dir": [
            "/data",  # HELM standard
            "/app/data",  # Docker standard
            f"/var/lib/{app_name}",  # Linux standard with app name
            "/persistent",  # Generic PVC
            f"/opt/{app_name}/data",  # Alternative app-specific
        ],
        "logs_dir": [
            "/logs",  # HELM simple standard
            "/app/logs",  # Docker standard
            f"/var/log/{app_name}",  # Linux standard with app name
            "/data/logs",  # Persistent logs in data volume
            "/var/log",  # Fallback to general log dir
        ],
        "temp_dir": [
            tempfile.gettempdir(),  # Universal standard
            f"{tempfile.gettempdir()}/{app_name}",  # App-specific temp
            "/app/tmp",  # Docker app temp
            "/var/tmp",  # Alternative system temp
            "/run/tmp",  # Runtime temp (tmpfs)
        ],
        # Additional commonly used paths in DevOps
        "cache_dir": [
            "/cache",  # Simple cache volume
            "/app/cache",  # Docker app cache
            f"/var/cache/{app_name}",  # Linux standard cache
            "/data/cache",  # Persistent cache in data
        ],
        "run_dir": [
            f"/run/{app_name}",  # Runtime state (PIDs, sockets)
            f"/var/run/{app_name}",  # Alternative runtime
            "/app/run",  # Docker runtime
        ],
    }

    for mount_type, paths in mount_checks.items():
        for path_str in paths:
            path = Path(path_str)
            if path.exists():
                detected[mount_type] = path
                if os.getenv("HYPERLIB_DEBUG"):
                    print(f"Detected {mount_type}: {path}")
                break

    return detected


def get_default_mounts(environment: str, app_name: str, auto_detect: bool = True) -> MountConfig:
    """
    Return sensible mount defaults based on detected environment.

    Priority:
    1. Auto-detected existing mounts
    2. HELM standard paths (if HELM detected)
    3. Environment-specific defaults
    4. Generic fallback

    Args:
        environment: Detected environment type
        app_name: Application name for path construction
        auto_detect: Whether to use auto-detected paths

    Returns:
        MountConfig with appropriate paths for the environment
    """
    if not auto_detect:
        # Use generic paths when auto-detection is disabled
        return MountConfig(
            config_dir=Path("/app/config"),
            secrets_dir=Path("/app/secrets"),
            data_dir=Path("/app/data"),
            temp_dir=Path(tempfile.gettempdir()),
            logs_dir=Path("/app/logs"),
        )

    # First, try to detect existing standard mounts
    detected = detect_standard_mounts()

    # Check if this is a HELM deployment
    is_helm = detect_helm_deployment()

    if environment == "kubernetes":
        if is_helm:
            # HELM standard paths
            config = MountConfig(
                config_dir=detected.get("config_dir", Path("/config")),
                secrets_dir=detected.get("secrets_dir", Path("/secrets")),
                data_dir=detected.get("data_dir", Path("/data")),
                temp_dir=detected.get("temp_dir", Path(tempfile.gettempdir())),
                logs_dir=detected.get("logs_dir", Path("/logs")),
                cache_dir=detected.get("cache_dir"),  # Optional
                run_dir=detected.get("run_dir"),  # Optional
            )
            if os.getenv("HYPERLIB_DEBUG"):
                print("HELM K8s mount paths detected")
        else:
            # Generic K8s paths
            config = MountConfig(
                config_dir=detected.get("config_dir", Path("/app/config")),
                secrets_dir=detected.get("secrets_dir", Path("/app/secrets")),
                data_dir=detected.get("data_dir", Path("/app/data")),
                temp_dir=detected.get("temp_dir", Path(tempfile.gettempdir())),
                logs_dir=detected.get("logs_dir", Path("/app/logs")),
                cache_dir=detected.get("cache_dir"),  # Optional
                run_dir=detected.get("run_dir"),  # Optional
            )
            if os.getenv("HYPERLIB_DEBUG"):
                print("K8s mount paths - using app namespace")

    elif environment in ["docker", "container"]:
        # Docker convention - /app namespace with detected overrides
        config = MountConfig(
            config_dir=detected.get("config_dir", Path("/app/config")),
            secrets_dir=detected.get("secrets_dir", Path("/run/secrets")),
            data_dir=detected.get("data_dir", Path("/app/data")),
            temp_dir=detected.get("temp_dir", Path(tempfile.gettempdir()) / app_name),  # nosec B108,
            logs_dir=detected.get("logs_dir", Path("/app/logs")),
            cache_dir=detected.get("cache_dir", Path("/app/cache")),
            run_dir=detected.get("run_dir", Path(f"/run/{app_name}")),
        )
        if os.getenv("HYPERLIB_DEBUG"):
            print("Docker mount paths - /app namespace")

    else:  # bare_metal
        # Local development - user home directory
        home = Path.home()
        config = MountConfig(
            config_dir=home / f".config/{app_name}",
            secrets_dir=home / f".{app_name}/secrets",
            data_dir=home / f".local/share/{app_name}",
            temp_dir=Path(tempfile.gettempdir()) / app_name,  # nosec B108
            logs_dir=home / f".local/share/{app_name}/logs",
            cache_dir=home / f".cache/{app_name}",
            run_dir=Path(f"/run/user/{os.getuid()}/{app_name}") if hasattr(os, "getuid") else None,
        )
        if os.getenv("HYPERLIB_DEBUG"):
            print("Local mount paths - user home directory")

    return config


# Configurable environment variable prefix and app name
# Set HYPERLIB_ENV_PREFIX to override (e.g., HYPERLIB_ENV_PREFIX=MYAPP)
# Default: APP (e.g., APP_LOG_LEVEL, APP_DATABASE_URL)
ENV_PREFIX = os.getenv("HYPERLIB_ENV_PREFIX", "APP")


# Determine app name with proper priority:
# 1. K8s/Docker standard APP_NAME environment variable
# 2. HYPERLIB_APP_NAME override
# 3. Python package name (if detectable)
# 4. Default to "app"
def get_app_name() -> str:
    """Get application name with proper priority.

    Priority order:
    1. APP_NAME environment variable (K8s/Docker standard)
    2. HYPERLIB_APP_NAME override
    3. Root application package name (not hyperlib)
    4. Main module name from sys.argv[0]
    5. Default to "app"
    """
    # Priority 1: K8s/Docker standard
    app_name = os.getenv("APP_NAME")
    if app_name:
        return app_name

    # Priority 2: Hyperlib override
    app_name = os.getenv("HYPERLIB_APP_NAME")
    if app_name:
        return app_name

    # Priority 3: Try to detect root application package name
    try:
        import importlib.metadata
        import sys

        # Get all installed packages
        for dist in importlib.metadata.distributions():
            name = dist.metadata.get("Name", "").lower()
            # Skip common libraries and hyperlib itself
            if name and name not in ("hyperlib", "pip", "setuptools", "wheel"):
                # Check if this package is in the current Python path
                try:
                    module = __import__(name.replace("-", "_"))
                    # If we can import it and it's not a standard library module
                    if hasattr(module, "__file__") and module.__file__:
                        module_path = Path(module.__file__).parent
                        # Check if it's in the current working directory or a local package
                        if str(Path.cwd()) in str(module_path) or "site-packages" not in str(module_path):
                            return name
                except (ImportError, AttributeError):
                    pass

        # Priority 4: Try main module from sys.argv
        if sys.argv and sys.argv[0]:
            # If running as module (python -m package)
            if sys.argv[0] == "-m" and len(sys.argv) > 1:
                return sys.argv[1].split(".")[0].replace("_", "-")
            # If running a script
            main_module = Path(sys.argv[0]).stem
            if main_module and main_module not in ("__main__", "pytest", "python"):
                return main_module.replace("_", "-")

    except Exception:
        pass

    # Priority 5: Default
    return "app"


APP_NAME = get_app_name()

# Auto-detection settings (can be disabled via env var)
AUTO_DETECT = os.getenv("HYPERLIB_AUTO_DETECT", "true").lower() in ("true", "1", "yes")
DETECTED_ENV = detect_environment() if AUTO_DETECT else "bare_metal"

# Get mount configuration based on environment
MOUNT_CONFIG = get_default_mounts(DETECTED_ENV, APP_NAME, AUTO_DETECT)

# Determine config directory based on environment
if DETECTED_ENV in ["kubernetes", "docker", "container"]:
    # Container environment - use mount config
    config_dir = MOUNT_CONFIG.config_dir
else:
    # Development environment - use local paths
    current_file = Path(__file__)
    if "/src/hyperlib/" in str(current_file):
        # Development: use project root
        project_root = current_file.parent.parent.parent
        config_dir = project_root / "config"
    else:
        # Installed package: use mount config
        config_dir = MOUNT_CONFIG.config_dir

# Build settings file list (check what exists)
settings_files = []
if config_dir and config_dir.exists():
    # Check for various config file names
    for filename in ["config.yaml", "config.yml", "settings.yaml", "settings.yml"]:
        config_file = config_dir / filename
        if config_file.exists():
            settings_files.append(str(config_file))
            if os.getenv("HYPERLIB_DEBUG"):
                print(f"Config file found: {config_file}")

    # Check for app-specific config
    app_config_dir = config_dir / APP_NAME
    if app_config_dir.exists():
        for filename in ["default.yaml", "default.yml", "config.yaml", "config.yml"]:
            app_config_file = app_config_dir / filename
            if app_config_file.exists():
                settings_files.append(str(app_config_file))
                if os.getenv("HYPERLIB_DEBUG"):
                    print(f"App config file found: {app_config_file}")

# Initialize Dynaconf with discovered settings
settings = Dynaconf(
    envvar_prefix=ENV_PREFIX,  # Environment variables use {ENV_PREFIX}_ prefix
    settings_files=settings_files if settings_files else [],  # Use discovered files
    load_dotenv=True,  # Load .env file (3rd priority)
    environments=False,  # Single config approach
    # PRECEDENCE: CLI → ENV → .env → config override → default → hardcoded
)


def get_settings():
    """Get standard dynaconf settings object"""
    return settings


def setup():
    """Setup configuration (for compatibility)"""
    return settings


def get_mount_config() -> MountConfig:
    """
    Get the detected or configured mount configuration.

    Returns:
        MountConfig with paths for config, data, and temp directories
    """
    return MOUNT_CONFIG


def get_environment() -> str:
    """
    Get the detected runtime environment.

    Returns:
        Environment string: "kubernetes", "docker", "container", or "bare_metal"
    """
    return DETECTED_ENV


def get_standard_env_vars() -> dict:
    """
    Get standard container environment variables.

    Detects and returns common environment variables used in
    HELM and Docker deployments.

    Returns:
        Dictionary of standard environment variables and their values
    """
    env_vars = {}

    # HELM standard environment variables
    helm_vars = {
        "HELM_RELEASE_NAME": os.getenv("HELM_RELEASE_NAME"),
        "HELM_NAMESPACE": os.getenv("HELM_NAMESPACE") or os.getenv("KUBERNETES_NAMESPACE"),
    }

    # Kubernetes standard environment variables
    k8s_vars = {
        "KUBERNETES_NAMESPACE": os.getenv("KUBERNETES_NAMESPACE") or os.getenv("NAMESPACE"),
        "POD_NAME": os.getenv("POD_NAME") or os.getenv("HOSTNAME"),
        "NODE_NAME": os.getenv("NODE_NAME"),
        "POD_IP": os.getenv("POD_IP"),
        "SERVICE_ACCOUNT": os.getenv("SERVICE_ACCOUNT"),
    }

    # Docker standard environment variables
    docker_vars = {
        "CONTAINER_ID": os.getenv("CONTAINER_ID"),
        "DOCKER_CONTAINER": os.getenv("DOCKER_CONTAINER"),
        "DOCKER_HOST": os.getenv("DOCKER_HOST"),
    }

    # Application standard environment variables
    app_vars = {
        "APP_NAME": os.getenv("APP_NAME") or APP_NAME,
        "APP_ENV": os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or DETECTED_ENV,
        "APP_VERSION": os.getenv("APP_VERSION") or os.getenv("VERSION"),
        "LOG_LEVEL": os.getenv("LOG_LEVEL"),
        "DEBUG": os.getenv("DEBUG"),
    }

    # Database standard environment variables
    db_vars = {}
    for prefix in ["POSTGRES", "MYSQL", "MONGO", "REDIS", "CLICKHOUSE"]:
        for suffix in ["HOST", "PORT", "USER", "PASSWORD", "DATABASE", "DB"]:
            key = f"{prefix}_{suffix}"
            value = os.getenv(key)
            if value:
                db_vars[key] = value

    # Combine all detected variables
    for var_dict in [helm_vars, k8s_vars, docker_vars, app_vars, db_vars]:
        for key, value in var_dict.items():
            if value is not None:
                env_vars[key] = value

    return env_vars


def get_database_config(db_type: str = "postgresql", env_prefix: str = None) -> dict:
    """
    Get database configuration from environment variables.

    Args:
        db_type: Type of database (postgresql, mysql, clickhouse, redis, mongo)
        env_prefix: Environment variable prefix (default: uppercase db_type)

    Returns:
        Dictionary with database configuration
    """
    if env_prefix is None:
        env_prefix = db_type.upper()

    # Standard suffixes for database configuration
    config = {
        "host": os.getenv(f"{env_prefix}_HOST", "localhost"),
        "port": os.getenv(f"{env_prefix}_PORT"),
        "user": os.getenv(f"{env_prefix}_USER") or os.getenv(f"{env_prefix}_USERNAME"),
        "password": os.getenv(f"{env_prefix}_PASSWORD") or os.getenv(f"{env_prefix}_PASS"),
        "database": os.getenv(f"{env_prefix}_DATABASE") or os.getenv(f"{env_prefix}_DB"),
    }

    # Set default ports based on database type
    if not config["port"]:
        default_ports = {
            "postgresql": "5432",
            "postgres": "5432",
            "mysql": "3306",
            "clickhouse": "9000",
            "redis": "6379",
            "mongo": "27017",
            "mongodb": "27017",
        }
        config["port"] = default_ports.get(db_type.lower(), "5432")

    # Additional database-specific configuration
    if db_type.lower() in ["postgresql", "postgres"]:
        config["sslmode"] = os.getenv(f"{env_prefix}_SSLMODE", "prefer")

    return {k: v for k, v in config.items() if v is not None}


def get_container_config() -> dict:
    """
    Get container-aware configuration including mounts and environment.

    Returns:
        Dictionary with container configuration:
        - environment: Detected environment type
        - app_name: Application name
        - mounts: Mount paths (config, secrets, data, temp, logs)
        - auto_detect: Whether auto-detection is enabled
        - is_helm: Whether HELM deployment was detected
        - standard_env: Standard environment variables detected
    """
    return {
        "environment": DETECTED_ENV,
        "app_name": APP_NAME,
        "mounts": {
            "config_dir": str(MOUNT_CONFIG.config_dir) if MOUNT_CONFIG.config_dir else None,
            "secrets_dir": str(MOUNT_CONFIG.secrets_dir) if MOUNT_CONFIG.secrets_dir else None,
            "data_dir": str(MOUNT_CONFIG.data_dir) if MOUNT_CONFIG.data_dir else None,
            "temp_dir": str(MOUNT_CONFIG.temp_dir) if MOUNT_CONFIG.temp_dir else None,
            "logs_dir": str(MOUNT_CONFIG.logs_dir) if MOUNT_CONFIG.logs_dir else None,
        },
        "auto_detect": AUTO_DETECT,
        "env_prefix": ENV_PREFIX,
        "is_helm": detect_helm_deployment() if DETECTED_ENV == "kubernetes" else False,
        "standard_env": get_standard_env_vars(),
    }


# Standard configuration access functions
def get_api_config():
    """Get API configuration"""
    api_config = settings.get("api", {})
    return {
        "max_retries": api_config.get("max_retries", 3),
        "retry_delay": api_config.get("retry_delay", 5),
        "timeout": api_config.get("timeout", 120),
    }


def get_logging_config():
    """Get container-aware logging configuration with K8s standard env vars.

    Supports standard K8s/cloud-native logging environment variables:
    - LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - LOG_FORMAT: Output format (json, text, console, logfmt)
    - LOG_OUTPUT: Destination (stdout, stderr, file)
    - LOG_COLOR / NO_COLOR: Color control for output
    - LOG_TIMESTAMP_FORMAT: Timestamp format (iso8601, rfc3339, unix, epoch)
    - LOG_CALLER: Include source location (true/false)
    - LOG_STACKTRACE_LEVEL: Minimum level for stack traces (ERROR, CRITICAL)

    Environment Variable Prefix:
    - Default: APP_ (e.g., APP_LOGGING__LEVEL)
    - Configurable via: HYPERLIB_ENV_PREFIX (e.g., HYPERLIB_ENV_PREFIX=MYAPP)

    Priority order (CLI → ENV → .env → config → default → hardcoded):
    1. Standard environment variables (LOG_*)
    2. Dynaconf prefixed variables ({ENV_PREFIX}_LOGGING__*)
    3. Config file (logging.*)
    4. Hardcoded defaults
    """
    import os
    import sys

    logging_config = settings.get("logging", {})

    # LOG_LEVEL: Standard log level
    log_level = os.getenv("LOG_LEVEL")
    if not log_level:
        log_level = logging_config.get("level", "INFO")

    # LOG_FORMAT: Output format (json, text, console, logfmt)
    log_format = os.getenv("LOG_FORMAT")
    if not log_format:
        log_format = logging_config.get("format", "console")

    # LOG_OUTPUT: Destination (stdout, stderr, file)
    log_output = os.getenv("LOG_OUTPUT")
    if not log_output:
        log_output = logging_config.get("output", "stderr")

    # LOG_COLOR / NO_COLOR: Color control
    # NO_COLOR is a standard env var: https://no-color.org/
    log_color = os.getenv("LOG_COLOR")
    no_color = os.getenv("NO_COLOR")
    if log_color is not None:
        use_color = log_color.lower() in ("true", "1", "yes")
    elif no_color is not None:
        use_color = False  # NO_COLOR disables colors
    elif not sys.stderr.isatty():
        use_color = False  # Disable colors when not a TTY (K8s containers)
    else:
        use_color = logging_config.get("color", True)

    # LOG_TIMESTAMP_FORMAT: Timestamp format
    timestamp_format = os.getenv("LOG_TIMESTAMP_FORMAT")
    if not timestamp_format:
        timestamp_format = logging_config.get("timestamp_format", "rfc3339")

    # LOG_CALLER: Include source location
    log_caller = os.getenv("LOG_CALLER")
    if log_caller is not None:
        include_caller = log_caller.lower() in ("true", "1", "yes")
    else:
        include_caller = logging_config.get("caller", True)

    # LOG_STACKTRACE_LEVEL: Minimum level for stack traces
    stacktrace_level = os.getenv("LOG_STACKTRACE_LEVEL")
    if not stacktrace_level:
        stacktrace_level = logging_config.get("stacktrace_level", "ERROR")

    # Get container-aware log file path
    log_file = logging_config.get("file")
    if log_file and not log_file.startswith("/"):
        # Relative path - make it container-aware
        if MOUNT_CONFIG.data_dir:
            log_file = str(MOUNT_CONFIG.data_dir / "logs" / log_file)
        else:
            log_file = str(Path("/var/log") / APP_NAME / log_file)

    return {
        "level": log_level,
        "format": log_format,
        "output": log_output,
        "color": use_color,
        "timestamp_format": timestamp_format,
        "caller": include_caller,
        "stacktrace_level": stacktrace_level,
        "console": logging_config.get("console", True),
        "file": log_file,
    }


def get_target_config(target: str = None, targets_file: str = None) -> dict:
    """
    Get target-specific configuration for multi-environment setups.

    Loads configuration from a targets file (YAML) with environment-specific
    settings. Supports environment variable overrides.

    Args:
        target: Target environment name (e.g., "production", "staging").
               If None, uses default_target from config or TARGET env var.
        targets_file: Path to targets YAML file.
                     Default: ~/.{APP_NAME}/targets.yaml or TARGETS_FILE env var

    Returns:
        Dictionary with target configuration

    Example targets.yaml:
        default_target: development

        targets:
          production:
            database_url: postgresql://prod.example.com/db
            api_key: ${PROD_API_KEY}

          development:
            database_url: postgresql://localhost/db
            api_key: dev-key-123

    Usage:
        config = get_target_config("production")
        db_url = config["database_url"]

        # Or with env var: export TARGET=staging
        config = get_target_config()
    """
    from pathlib import Path

    import yaml

    # Determine targets file path
    if targets_file is None:
        targets_file = os.getenv("TARGETS_FILE")

    if targets_file is None:
        # Default to ~/.{APP_NAME}/targets.yaml
        home = Path.home()
        targets_file = home / f".{APP_NAME}" / "targets.yaml"

    targets_path = Path(targets_file).expanduser()

    if not targets_path.exists():
        raise FileNotFoundError(
            f"Targets configuration file not found: {targets_path}\n" f"Create it with your environment configurations."
        )

    # Load targets file
    with open(targets_path) as f:
        targets_data = yaml.safe_load(f) or {}

    # Determine target name
    if target is None:
        target = os.getenv("TARGET") or targets_data.get("default_target")

    if not target:
        raise ValueError(
            "No target specified. Set TARGET env var, provide target parameter, "
            "or define default_target in targets file."
        )

    # Get target config
    targets = targets_data.get("targets", {})
    if target not in targets:
        available = ", ".join(targets.keys())
        raise ValueError(f"Target '{target}' not found in configuration.\n" f"Available targets: {available}")

    target_config = targets[target].copy()
    target_config["target_name"] = target

    return target_config


def init_config_directory(
    app_name: str = None,
    config_dir: str = None,
    create_targets: bool = True,
    create_env: bool = True,
) -> Path:
    """
    Initialize configuration directory for CLI/daemon applications.

    Creates config directory structure and optional template files:
    - ~/.{app_name}/
    - ~/.{app_name}/config/       (config files)
    - ~/.{app_name}/targets.yaml  (multi-environment config)
    - ~/.{app_name}/.env          (environment variables)

    Args:
        app_name: Application name (default: APP_NAME from config)
        config_dir: Custom config directory (default: ~/.{app_name})
        create_targets: Create targets.yaml template
        create_env: Create .env template

    Returns:
        Path to config directory

    Example:
        from hyperlib.config import init_config_directory

        # Initialize with defaults
        config_dir = init_config_directory("my-cli")

        # Or custom location
        config_dir = init_config_directory(
            "my-cli",
            config_dir="/etc/my-cli",
            create_targets=True
        )
    """
    from pathlib import Path

    if app_name is None:
        app_name = APP_NAME

    # Determine config directory
    config_dir = Path.home() / f".{app_name}" if config_dir is None else Path(config_dir)

    # Create directory structure
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config").mkdir(exist_ok=True)

    # Create targets.yaml template
    if create_targets:
        targets_file = config_dir / "targets.yaml"
        if not targets_file.exists():
            targets_template = f"""# Multi-environment configuration for {app_name}
# Reference: https://docs.hyperlib.io/config/targets

default_target: development

targets:
  production:
    # Production environment settings
    # Use ${{ENV_VAR}} for environment variable substitution
    example_setting: value

  staging:
    # Staging environment settings
    example_setting: value

  development:
    # Development environment settings
    example_setting: value
"""
            targets_file.write_text(targets_template)
            print(f"✅ Created targets template: {targets_file}")

    # Create .env template
    if create_env:
        env_file = config_dir / ".env"
        if not env_file.exists():
            env_template = f"""# Environment variables for {app_name}
# These override settings in targets.yaml

# Select target environment
# TARGET=production

# Application settings
# {ENV_PREFIX}_SETTING_NAME=value
"""
            env_file.write_text(env_template)
            print(f"✅ Created .env template: {env_file}")

    print(f"✅ Config directory initialized: {config_dir}")
    return config_dir


# Export for direct access
__all__ = [
    "settings",
    "get_settings",
    "setup",
    "get_api_config",
    "get_logging_config",
    "get_target_config",
    "init_config_directory",
    "ENV_PREFIX",
    "APP_NAME",
    # Container-aware exports
    "MountConfig",
    "detect_environment",
    "detect_helm_deployment",
    "detect_standard_mounts",
    "get_default_mounts",
    "get_mount_config",
    "get_environment",
    "get_container_config",
    "get_standard_env_vars",
    "get_database_config",
    "DETECTED_ENV",
    "MOUNT_CONFIG",
    "AUTO_DETECT",
]
