"""
MCP Server Application

Provides a factory for creating MCP (Model Context Protocol) servers.
Supports stdio and HTTP transports with tool/resource/prompt registration.
"""

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import MountConfig, get_mount_config
from ..logger import logger


class MCPApplication:
    """
    MCP Server application with tool/resource/prompt registration.

    Supports MCP protocol over stdio or HTTP transport.
    Pre-wired with hyperlib logger and config cascade.

    Example:
        app = Application.mcp(name="my-server", transport="stdio")

        @app.tool(name="analyze", description="Analyze code")
        def analyze(code: str) -> dict:
            return {"result": "analysis"}

        @app.resource(uri="file://")
        def list_files() -> list:
            return ["file1.txt", "file2.txt"]

        app.run()
    """

    def __init__(
        self,
        name: str,
        transport: str = "stdio",
        capabilities: list[str] | None = None,
        mounts: MountConfig | None = None,
        **kwargs,
    ):
        """
        Initialize MCP server application.

        Args:
            name: Application name
            transport: Communication transport ("stdio" or "http")
            capabilities: MCP capabilities to advertise
            mounts: Container mount configuration
            **kwargs: Additional configuration
        """
        self.name = name
        self.transport = transport
        self.capabilities = capabilities or ["tools", "resources", "prompts"]
        self.mounts = mounts or get_mount_config()

        # MCP protocol handlers
        self.tools = {}
        self.resources = {}
        self.prompts = {}

        # Lifecycle hooks
        self.startup_hooks = []
        self.shutdown_hooks = []

        logger.info(f"🔧 MCPApplication '{name}' initialized (transport={transport})")
        logger.debug(f"Capabilities: {', '.join(self.capabilities)}")

    def tool(self, name: str, description: str = "", schema: dict | None = None):
        """
        Decorator to register an MCP tool.

        Args:
            name: Tool name
            description: Tool description
            schema: JSON schema for tool parameters

        Example:
            @app.tool(name="get_data", description="Fetch data from source")
            def get_data(source: str) -> dict:
                return {"data": fetch(source)}
        """

        def decorator(func: Callable) -> Callable:
            self.tools[name] = {
                "name": name,
                "description": description or func.__doc__ or "",
                "schema": schema or {},
                "handler": func,
            }
            logger.debug(f"Registered tool: {name}")
            return func

        return decorator

    def resource(self, uri: str, description: str = ""):
        """
        Decorator to register an MCP resource.

        Args:
            uri: Resource URI pattern
            description: Resource description

        Example:
            @app.resource(uri="file://", description="File system access")
            def list_files(path: str) -> list:
                return os.listdir(path)
        """

        def decorator(func: Callable) -> Callable:
            self.resources[uri] = {
                "uri": uri,
                "description": description or func.__doc__ or "",
                "handler": func,
            }
            logger.debug(f"Registered resource: {uri}")
            return func

        return decorator

    def prompt(self, name: str, description: str = ""):
        """
        Decorator to register an MCP prompt template.

        Args:
            name: Prompt name
            description: Prompt description

        Example:
            @app.prompt(name="analyze", description="Code analysis prompt")
            def analyze_prompt(context: str) -> str:
                return f"Analyze this code: {context}"
        """

        def decorator(func: Callable) -> Callable:
            self.prompts[name] = {
                "name": name,
                "description": description or func.__doc__ or "",
                "handler": func,
            }
            logger.debug(f"Registered prompt: {name}")
            return func

        return decorator

    def on_startup(self, func: Callable) -> Callable:
        """Decorator to register startup hook."""
        self.startup_hooks.append(func)
        logger.debug(f"Registered startup hook: {func.__name__}")
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """Decorator to register shutdown hook."""
        self.shutdown_hooks.append(func)
        logger.debug(f"Registered shutdown hook: {func.__name__}")
        return func

    async def handle_request(self, request: dict) -> dict:
        """
        Handle incoming MCP request.

        Implements JSON-RPC 2.0 protocol for MCP.
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            # Handle MCP protocol methods
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {cap: {} for cap in self.capabilities},
                        "serverInfo": {"name": self.name, "version": "0.1.0"},
                    },
                }

            elif method == "tools/list":
                tool_list = [
                    {
                        "name": tool["name"],
                        "description": tool["description"],
                        "inputSchema": tool["schema"],
                    }
                    for tool in self.tools.values()
                ]
                return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tool_list}}

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name not in self.tools:
                    raise ValueError(f"Tool not found: {tool_name}")

                tool = self.tools[tool_name]
                result = tool["handler"](**arguments)

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": str(result)}]},
                }

            elif method == "resources/list":
                resource_list = [
                    {"uri": res["uri"], "name": res["uri"], "description": res["description"]}
                    for res in self.resources.values()
                ]
                return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": resource_list}}

            elif method == "prompts/list":
                prompt_list = [
                    {"name": prompt["name"], "description": prompt["description"]} for prompt in self.prompts.values()
                ]
                return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": prompt_list}}

            else:
                raise ValueError(f"Unknown method: {method}")

        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)},
            }

    async def run_stdio(self):
        """Run MCP server over stdio transport."""
        logger.info(f"Starting MCP server '{self.name}' on stdio")

        # Run startup hooks
        for hook in self.startup_hooks:
            if asyncio.iscoroutinefunction(hook):
                await hook()
            else:
                hook()

        try:
            # Read JSON-RPC requests from stdin, write responses to stdout
            while True:
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line)
                    response = await self.handle_request(request)
                    print(json.dumps(response), flush=True)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    continue

        finally:
            # Run shutdown hooks
            for hook in self.shutdown_hooks:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()

            logger.info(f"MCP server '{self.name}' stopped")

    def run_http(self):
        """Run MCP server over HTTP transport (using FastAPI)."""
        logger.info(f"Starting MCP server '{self.name}' over HTTP")

        try:
            import uvicorn
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse
        except ImportError:
            logger.error("FastAPI not installed - HTTP transport requires: pip install fastapi uvicorn")
            raise

        app = FastAPI(title=self.name)

        @app.post("/mcp")
        async def mcp_endpoint(request: dict):
            """Handle MCP requests over HTTP."""
            response = await self.handle_request(request)
            return JSONResponse(content=response)

        # Run startup hooks
        for hook in self.startup_hooks:
            app.add_event_handler("startup", hook)

        # Run shutdown hooks
        for hook in self.shutdown_hooks:
            app.add_event_handler("shutdown", hook)

        # Start HTTP server - bind to all interfaces for containerized environments
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")  # nosec B104 - Intentional for containers

    def run(self):
        """
        Start MCP server with configured transport.

        Uses hyperlib logger for all logging.
        Uses hyperlib config cascade for configuration.
        """
        logger.info(f"MCP server '{self.name}' starting (transport={self.transport})")
        logger.info(
            f"Registered: {len(self.tools)} tools, {len(self.resources)} resources, {len(self.prompts)} prompts"
        )

        try:
            if self.transport == "stdio":
                asyncio.run(self.run_stdio())
            elif self.transport == "http":
                self.run_http()
            else:
                raise ValueError(f"Unknown transport: {self.transport}")
        except KeyboardInterrupt:
            logger.info(f"MCP server '{self.name}' interrupted")
        except Exception as e:
            logger.error(f"MCP server error: {e}")
            raise
