"""
HyperLib API Application
FastAPI-based REST API service with container management
"""

from pathlib import Path
from typing import Any, Callable

from ..container import ContainerApp, ContainerConfig, MountConfig
from ..logger import logger


class APIApplication:
    """
    REST API service application using FastAPI.

    Provides:
    - FastAPI integration with automatic container management
    - Prometheus metrics on separate port
    - Health/ready endpoints
    - Graceful shutdown handling
    - Resource monitoring (memory, CPU)

    Example:
        app = Application.api(name="my-service", port=8000)

        @app.route("/")
        def root():
            return {"message": "Hello"}

        @app.route("/users/{user_id}")
        def get_user(user_id: int):
            return {"user_id": user_id}

        app.run()
    """

    def __init__(
        self,
        name: str,
        port: int = 8000,
        metrics_port: int = 8080,
        mounts: MountConfig | None = None,
        **kwargs,
    ):
        """
        Initialize API application.

        Args:
            name: Application name
            port: API server port
            metrics_port: Prometheus metrics port
            mounts: Container mount configuration
            **kwargs: Additional ContainerConfig options
        """
        self.name = name
        self.port = port
        self.metrics_port = metrics_port

        # Create FastAPI app
        try:
            from fastapi import FastAPI

            self.fastapi = FastAPI(
                title=name,
                description=f"{name} - HyperLib API Service",
                version="1.0.0",
            )
        except ImportError:
            raise ImportError(
                "FastAPI is required for API applications. "
                "Install it with: pip install fastapi uvicorn[standard]"
            )

        # Add default health endpoints
        self._add_health_endpoints()

        # Create container config
        if mounts is None:
            mounts = MountConfig(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
            )

        self.config = ContainerConfig(
            app_name=name,
            mounts=mounts,
            api_port=port,
            metrics_port=metrics_port,
            **kwargs,
        )

        # Container app will be created when run() is called
        self.container: ContainerApp | None = None

        logger.info(f"🚀 APIApplication '{name}' initialized (port={port})")

    def _add_health_endpoints(self):
        """Add default health and ready endpoints."""

        @self.fastapi.get("/health")
        async def health():
            """Health check endpoint for Kubernetes liveness probe."""
            return {
                "status": "healthy",
                "service": self.name,
            }

        @self.fastapi.get("/ready")
        async def ready():
            """Readiness check endpoint for Kubernetes readiness probe."""
            return {
                "status": "ready",
                "service": self.name,
            }

    def route(self, path: str, **kwargs) -> Callable:
        """
        Decorator to add GET route to API.

        Args:
            path: URL path (e.g., "/users/{user_id}")
            **kwargs: FastAPI route options (methods, status_code, etc.)

        Example:
            @app.route("/users/{user_id}")
            def get_user(user_id: int):
                return {"user_id": user_id}
        """
        return self.fastapi.get(path, **kwargs)

    def post(self, path: str, **kwargs) -> Callable:
        """Decorator to add POST route."""
        return self.fastapi.post(path, **kwargs)

    def put(self, path: str, **kwargs) -> Callable:
        """Decorator to add PUT route."""
        return self.fastapi.put(path, **kwargs)

    def delete(self, path: str, **kwargs) -> Callable:
        """Decorator to add DELETE route."""
        return self.fastapi.delete(path, **kwargs)

    def patch(self, path: str, **kwargs) -> Callable:
        """Decorator to add PATCH route."""
        return self.fastapi.patch(path, **kwargs)

    def add_route(self, path: str, endpoint: Callable, methods: list[str] = None, **kwargs):
        """
        Programmatically add route to API.

        Args:
            path: URL path
            endpoint: Function to handle requests
            methods: HTTP methods (default: ["GET"])
            **kwargs: FastAPI route options
        """
        if methods is None:
            methods = ["GET"]

        self.fastapi.add_api_route(path, endpoint, methods=methods, **kwargs)

    def run(self):
        """
        Start the API service.

        Starts:
        - FastAPI server on api_port
        - Prometheus metrics on metrics_port
        - Health/ready endpoints
        - Graceful shutdown handling
        """
        logger.info(f"Starting API service '{self.name}' on port {self.port}")

        # Create container app (business logic is None for pure API)
        self.container = ContainerApp(
            business_logic=None,
            config=self.config,
        )

        # Run daemon with API
        self.container.run_daemon_api(fastapi_app=self.fastapi)
