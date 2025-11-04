"""HyperLib Config Module - Re-exports from config.py for backward compatibility."""

# Re-export everything from config.py
from .config import *  # noqa: F403

# Re-export merge functionality
from .merge import (  # noqa: F401
    merge_files,
    detect_file_type,
    merge_json,
    merge_yaml,
    merge_toml,
    merge_gitignore,
)
