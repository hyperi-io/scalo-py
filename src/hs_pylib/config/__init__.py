"""hs-pylib Config Module - Re-exports from config.py for backward compatibility."""

# Re-export everything from config.py
from .config import *  # noqa: F403

# Re-export merge functionality
from .merge import (  # noqa: F401
    detect_file_type,
    merge_files,
    merge_gitignore,
    merge_json,
    merge_toml,
    merge_yaml,
)
