"""
HealthCheckMixin: Health and readiness endpoints for Kubernetes.

This mixin provides /health and /ready endpoints for container health checks.
Supports standalone HTTP server for non-HTTP applications (Daemon, MCP, Oneshot).
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from json import dumps as json_dumps
from typing import Any, Callable

from hyperlib.logger import logger


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoints."""

    def __init__(self, app_instance: Any, *args: Any, **kwargs: Any):
        """
        Initialize handler with reference to application instance.

        Args:
            app_instance: Reference to the application (to access health checks)
            *args: Positional args for BaseHTTPRequestHandler
            **kwargs: Keyword args for BaseHTTPRequestHandler
        """
        self.app = app_instance
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests for /health and /ready endpoints."""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/ready":
            self._handle_ready()
        else:
            self.send_error(404, "Not Found")

    def _handle_health(self) -> None:
        """Handle /health endpoint (liveness probe)."""
        response = {"status": "healthy", "service": self.app.name}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json_dumps(response).encode())

    def _handle_ready(self) -> None:
        """Handle /ready endpoint (readiness probe with dependency checks)."""
        # Run health check handlers if any registered
        if hasattr(self.app, "_health_check_handlers") and self.app._health_check_handlers:
            for handler in self.app._health_check_handlers:
                try:
                    if not handler():
                        response = {"status": "not ready", "service": self.app.name}
                        self.send_response(503)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json_dumps(response).encode())
                        return
                except Exception as e:
                    logger.error(f"Health check failed: {e}")
                    response = {"status": "not ready", "service": self.app.name, "error": str(e)}
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json_dumps(response).encode())
                    return

        # All checks passed
        response = {"status": "ready", "service": self.app.name}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json_dumps(response).encode())

    def log_message(self, format: str, *args: Any) -> None:  # noqa: ARG002
        """Suppress default HTTP server logging (use hyperlib logger instead)."""
        pass


class HealthCheckMixin:
    """
    Mixin to add health check capabilities to applications.

    Provides /health (liveness) and /ready (readiness) endpoints for
    Kubernetes probes. Supports dependency checks (database, cache, etc.)

    For HTTP applications (API), endpoints are added to the main HTTP server.
    For non-HTTP applications (Daemon, MCP, Oneshot), a standalone HTTP
    server is started in a background thread.

    Example:
        app = Application.daemon(name="worker", profile="prod")

        @app.health_check
        def check_database():
            try:
                db.ping()
                return True
            except Exception:
                return False

        @app.health_check
        def check_redis():
            try:
                redis.ping()
                return True
            except Exception:
                return False
    """

    def __init__(self, **kwargs: Any):
        """
        Initialize health check mixin.

        Args:
            **kwargs: Additional args passed to next mixin in chain
        """
        self._health_check_handlers: list[Callable[[], bool]] = []
        self._health_server: HTTPServer | None = None
        self._health_server_thread: threading.Thread | None = None

        # Call next mixin in MRO chain FIRST (so ProfileMixin is initialized)
        super().__init__(**kwargs)

        # Setup health check endpoints if enabled in profile (AFTER ProfileMixin)
        if self._should_setup_health_checks():
            self._setup_health_checks()

        # Register shutdown handler AFTER setup
        if self._health_server:
            if hasattr(self, "on_shutdown"):
                self.on_shutdown(self._stop_health_server)

    def _should_setup_health_checks(self) -> bool:
        """Check if health checks should be enabled based on profile."""
        if hasattr(self, "profile"):
            return self.profile.get("health_check", False)
        return False

    def _setup_health_checks(self) -> None:
        """
        Setup health check endpoints.

        For HTTP applications (has self.fastapi), endpoints are added to
        the main FastAPI app by the application class itself.

        For non-HTTP applications, start a standalone HTTP server.
        """
        # Skip if this is an HTTP application (API handles it directly)
        if hasattr(self, "fastapi"):
            logger.debug("Health checks will be handled by FastAPI")
            return

        # Start standalone HTTP server for non-HTTP apps
        port = self.profile.get("health_check_port", 8080)
        self._start_health_server(port)

    def _start_health_server(self, port: int) -> None:
        """
        Start standalone HTTP server for health checks.

        Args:
            port: Port to bind the health server to
        """

        def handler(*args: Any, **kwargs: Any) -> HealthCheckHandler:
            """Create handler with reference to app instance."""
            return HealthCheckHandler(self, *args, **kwargs)

        try:
            self._health_server = HTTPServer(("0.0.0.0", port), handler)  # nosec B104
            self._health_server_thread = threading.Thread(
                target=self._health_server.serve_forever, name="health-server", daemon=True
            )
            self._health_server_thread.start()
            logger.info(f"Health server started on port {port} (/health, /ready)")
        except Exception as e:
            logger.error(f"Failed to start health server on port {port}: {e}")

    def _stop_health_server(self) -> None:
        """Stop the standalone health server."""
        if self._health_server:
            logger.info("Stopping health server...")
            self._health_server.shutdown()
            self._health_server = None
            if self._health_server_thread:
                self._health_server_thread.join(timeout=5)
                self._health_server_thread = None

    def health_check(self, func: Callable[[], bool]) -> Callable[[], bool]:
        """
        Register a health check handler (decorator).

        The registered function will be called during /ready endpoint checks.
        It should return True if the dependency is healthy, False otherwise.

        Args:
            func: Function that returns True if healthy, False if not

        Returns:
            The original function (allows use as decorator)

        Example:
            @app.health_check
            def check_database():
                try:
                    db.ping()
                    return True
                except Exception:
                    return False
        """
        self._health_check_handlers.append(func)
        logger.debug(f"Registered health check: {func.__name__}")
        return func
