"""hs-pylib Logger Module - Re-exports from logger.py for backward compatibility."""

# Re-export everything from logger.py
# This creates: hs_pylib.logger.logger, hs_pylib.logger.info, etc.
from .logger import *  # noqa: F403
