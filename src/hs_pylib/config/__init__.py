"""hs-pylib Config Module - Re-exports from config.py for backward compatibility."""

from .config import (
    MountConfig,
    detect_environment,
    detect_helm_deployment,
    detect_standard_mounts,
    get_api_config,
    get_app_name,
    get_config,
    get_container_config,
    get_database_config,
    get_default_mounts,
    get_environment,
    get_logging_config,
    get_mount_config,
    get_settings,
    get_standard_env_vars,
    get_target_config,
    init_config_directory,
    settings,
    setup,
)
from .merge import (
    detect_file_type,
    merge_files,
    merge_gitignore,
    merge_json,
    merge_toml,
    merge_yaml,
)
from .postgres_loader import (
    PostgresConfigError,
    PostgresConfigLoader,
    PostgresConfigUnavailable,
    get_default_loader,
    load_postgres_config,
)

__all__ = [
    # Config classes and functions
    "MountConfig",
    "detect_environment",
    "detect_helm_deployment",
    "detect_standard_mounts",
    "get_api_config",
    "get_app_name",
    "get_config",
    "get_container_config",
    "get_database_config",
    "get_default_mounts",
    "get_environment",
    "get_logging_config",
    "get_mount_config",
    "get_settings",
    "get_standard_env_vars",
    "get_target_config",
    "init_config_directory",
    "settings",
    "setup",
    # Merge functions
    "detect_file_type",
    "merge_files",
    "merge_gitignore",
    "merge_json",
    "merge_toml",
    "merge_yaml",
    # PostgreSQL config loader
    "PostgresConfigLoader",
    "PostgresConfigError",
    "PostgresConfigUnavailable",
    "load_postgres_config",
    "get_default_loader",
]
