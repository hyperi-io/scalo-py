"""
MCP Server Application with container-native patterns

Provides MCP (Model Context Protocol) servers with profile-based configuration.
Supports stdio and HTTP transports with tool/resource/prompt registration.
"""

import asyncio
import json
import sys
from collections.abc import Callable
from typing import Any, Optional

from ...logger import logger
from ..mixins import (
    CLIExecutableMixin,
    HealthCheckMixin,
    MetricsMixin,
    ProfileMixin,
    SignalHandlerMixin,
)


class MCPApplication(
    CLIExecutableMixin,
    SignalHandlerMixin,
    ProfileMixin,
    HealthCheckMixin,
    MetricsMixin,
):
    """
    MCP Server application with container-native patterns.

    Provides container-native patterns out of the box:
    - Profile-based configuration (dev/docker/prod)
    - Graceful shutdown (SIGTERM/SIGINT)
    - Automatic MCP metrics (request count, duration)
    - Typer CLI commands (serve, validate, version, config)

    Example (simple):
        app = Application.mcp(name="my-server", version="1.0.0", profile="prod")

        @app.tool(name="analyze", description="Analyze code")
        def analyze(code: str) -> dict:
            return {"result": "analysis"}

        if __name__ == "__main__":
            app.run()  # Runs Typer CLI

    Example (production):
        # Container CMD: python -m my_mcp serve --profile prod
        # Automatically gets: metrics, graceful shutdown

    Supports MCP protocol over stdio or HTTP transport.
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        profile: str = "dev",
        transport: str = "stdio",
        capabilities: list[str] | None = None,
        profile_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize MCP server application.

        Args:
            name: Application name
            version: Application version
            profile: Environment profile ("dev", "docker", "prod")
            transport: Communication transport ("stdio" or "http")
            capabilities: MCP capabilities to advertise
            profile_overrides: Override profile settings
            **kwargs: Additional configuration
        """
        # Initialize mixins (MRO: CLI -> Signal -> Profile -> Metrics)
        super().__init__(
            name=name,
            version=version,
            profile=profile,
            profile_overrides=profile_overrides,
            description=f"{name} - HyperLib MCP Server",
        )

        self.transport = transport
        self.capabilities = capabilities or ["tools", "resources", "prompts"]

        # MCP protocol handlers
        self.tools: dict[str, dict[str, Any]] = {}
        self.resources: dict[str, dict[str, Any]] = {}
        self.prompts: dict[str, dict[str, Any]] = {}

        # Add serve command to CLI
        self._add_serve_command()

        logger.info(f"MCPApplication '{name}' initialized (transport={transport}, profile={profile})")
        logger.debug(f"Capabilities: {', '.join(self.capabilities)}")

    def _add_serve_command(self) -> None:
        """Add 'serve' command to CLI."""
        import typer

        @self.cli.command()
        def serve():
            """Start the MCP server."""
            logger.info(f"Starting MCP server '{self.name}' (transport={self.transport}, profile={self.profile_name})")
            self._run_server()

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
            @app.resource(uri="file://")
            def list_files() -> list:
                return ["file1.txt", "file2.txt"]
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
        Decorator to register an MCP prompt.

        Args:
            name: Prompt name
            description: Prompt description

        Example:
            @app.prompt(name="system", description="System prompt")
            def system_prompt() -> str:
                return "You are a helpful assistant"
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

    def _run_server(self) -> None:
        """
        Run the MCP server.

        Supports stdio and HTTP transports.
        """
        if self.transport == "stdio":
            self._run_stdio_server()
        elif self.transport == "http":
            self._run_http_server()
        else:
            raise ValueError(f"Unknown transport: {self.transport}")

    def _run_stdio_server(self) -> None:
        """Run MCP server over stdio transport."""
        logger.info("MCP server running on stdio")
        logger.info(f"Registered {len(self.tools)} tools, {len(self.resources)} resources, {len(self.prompts)} prompts")

        while not self.is_shutting_down():
            try:
                # Read request from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line)
                self.track_counter(
                    "mcp_requests_total",
                    labels={"method": request.get("method", "unknown"), "transport": "stdio"},
                )

                # Handle request
                response = self._handle_request(request)

                # Write response to stdout
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            except KeyboardInterrupt:
                logger.info("Interrupted")
                break
            except Exception as e:
                logger.error(f"Error handling request: {e}", exc_info=True)

        logger.info("MCP stdio server stopped")

    def _run_http_server(self) -> None:
        """Run MCP server over HTTP transport."""
        # HTTP server implementation (placeholder for now)
        logger.warning("HTTP transport not fully implemented yet")
        logger.info("Use stdio transport for production")

        # Wait for shutdown signal
        self.wait_for_shutdown()

    def _handle_request(self, request: dict) -> dict:
        """Handle MCP protocol request."""
        method = request.get("method")

        # Track request duration
        import time

        start_time = time.time()

        try:
            if method == "tools/list":
                tools_list = []
                for t in self.tools.values():
                    tools_list.append({"name": t["name"], "description": t["description"]})
                result = {"tools": tools_list}
            elif method == "tools/call":
                tool_name = request.get("params", {}).get("name")
                args = request.get("params", {}).get("arguments", {})
                if tool_name in self.tools:
                    result = self.tools[tool_name]["handler"](**args)
                else:
                    return {"error": f"Tool not found: {tool_name}"}
            elif method == "resources/list":
                result = {
                    "resources": [{"uri": r["uri"], "description": r["description"]} for r in self.resources.values()]
                }
            elif method == "prompts/list":
                result = {
                    "prompts": [{"name": p["name"], "description": p["description"]} for p in self.prompts.values()]
                }
            else:
                return {"error": f"Unknown method: {method}"}

            # Track success
            duration = time.time() - start_time
            self.track_histogram(
                "mcp_request_duration_seconds",
                duration,
                labels={"method": method, "status": "success"},
            )

            return {"id": request.get("id"), "result": result}

        except Exception as e:
            logger.error(f"Error handling {method}: {e}", exc_info=True)

            # Track error
            duration = time.time() - start_time
            self.track_histogram(
                "mcp_request_duration_seconds",
                duration,
                labels={"method": method, "status": "error"},
            )

            return {"id": request.get("id"), "error": str(e)}

    def on_startup(self, func: Callable) -> Callable:
        """Register startup hook."""
        if not hasattr(self, "_startup_hooks"):
            self._startup_hooks = []
        self._startup_hooks.append(func)
        logger.debug(f"Registered startup hook: {func.__name__}")
        return func
