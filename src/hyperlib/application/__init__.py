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

from .api import APIApplication
from .base import Application
from .cli import CLIApplication
from .daemon import DaemonApplication
from .mcp import MCPApplication
from .oneshot import OneshotApplication

__all__ = [
    "Application",
    "APIApplication",
    "DaemonApplication",
    "CLIApplication",
    "MCPApplication",
    "OneshotApplication",
]
