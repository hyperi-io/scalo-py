"""hs-lib Logger Module - Re-exports from logger.py for backward compatibility."""

# Re-export everything from logger.py
# This creates: hs_lib.logger.logger, hs_lib.logger.info, etc.
from .logger import *  # noqa: F403
