"""
MCP Server Application

Provides a factory for creating MCP (Model Context Protocol) servers.
Supports stdio and HTTP transports with tool/resource/prompt registration.
"""

from .application import MCPApplication

__all__ = ["MCPApplication"]
