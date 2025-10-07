"""
HyperLib Application Framework
Factory-based application builder for all deployment types

Provides:
- Application.api() - REST API services (FastAPI)
- Application.daemon() - Long-running background services
- Application.cli() - Command-line applications (Click)
- Application.oneshot() - Single-execution tasks

Pattern: Composition over inheritance (like Flask, FastAPI, Click)
"""

from .base import Application
from .api import APIApplication
from .daemon import DaemonApplication
from .cli import CLIApplication
from .oneshot import OneshotApplication

__all__ = [
    "Application",
    "APIApplication",
    "DaemonApplication",
    "CLIApplication",
    "OneshotApplication",
]
