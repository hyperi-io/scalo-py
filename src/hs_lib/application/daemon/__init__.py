"""
hs-lib Daemon Application
Long-running background service with scheduled tasks and worker pools
"""

from .application import DaemonApplication

__all__ = ["DaemonApplication"]
