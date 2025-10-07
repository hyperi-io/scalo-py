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
        enable_cors: bool = False,
        cors_origins: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize API application.

        Args:
            name: Application name
            port: API server port
            metrics_port: Prometheus metrics port
            mounts: Container mount configuration
            enable_cors: Enable CORS middleware
            cors_origins: List of allowed origins (default: ["*"])
            **kwargs: Additional ContainerConfig options
        """
        self.name = name
        self.port = port
        self.metrics_port = metrics_port
        self.startup_handlers: list[Callable] = []
        self.shutdown_handlers: list[Callable] = []

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

        # Add CORS middleware if enabled
        if enable_cors:
            self._add_cors_middleware(cors_origins or ["*"])

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

    def _add_cors_middleware(self, origins: list[str]):
        """Add CORS middleware to FastAPI app."""
        try:
            from fastapi.middleware.cors import CORSMiddleware

            self.fastapi.add_middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            logger.debug(f"CORS middleware enabled with origins: {origins}")
        except ImportError:
            logger.warning("CORSMiddleware not available, skipping CORS setup")

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

    def on_startup(self, func: Callable) -> Callable:
        """
        Decorator to register startup event handler.

        Example:
            @app.on_startup
            async def startup():
                logger.info("API starting...")
                # Initialize database connections, etc.
        """
        self.startup_handlers.append(func)
        self.fastapi.add_event_handler("startup", func)
        logger.debug(f"Registered startup handler: {func.__name__}")
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """
        Decorator to register shutdown event handler.

        Example:
            @app.on_shutdown
            async def shutdown():
                logger.info("API shutting down...")
                # Close database connections, etc.
        """
        self.shutdown_handlers.append(func)
        self.fastapi.add_event_handler("shutdown", func)
        logger.debug(f"Registered shutdown handler: {func.__name__}")
        return func

    def exception_handler(self, exc_class: type[Exception]) -> Callable:
        """
        Decorator to register exception handler.

        Args:
            exc_class: Exception class to handle

        Example:
            @app.exception_handler(ValueError)
            async def handle_value_error(request, exc: ValueError):
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)}
                )
        """

        def decorator(func: Callable) -> Callable:
            self.fastapi.add_exception_handler(exc_class, func)
            logger.debug(f"Registered exception handler for {exc_class.__name__}")
            return func

        return decorator

    def include_router(self, router, *, prefix: str = "", **kwargs):
        """
        Include an APIRouter for modular API organization.

        Args:
            router: FastAPI APIRouter instance
            prefix: URL prefix for all routes in this router
            **kwargs: Additional FastAPI router options (tags, dependencies, etc.)

        Example:
            from fastapi import APIRouter

            auth_router = APIRouter()

            @auth_router.get("/login")
            def login():
                return {"token": "..."}

            @auth_router.post("/logout")
            def logout():
                return {"status": "logged out"}

            app = Application.api(name="my-api")
            app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
        """
        self.fastapi.include_router(router, prefix=prefix, **kwargs)
        logger.debug(f"Included router with prefix: {prefix}")

    def add_middleware(self, middleware_class, **options):
        """
        Add custom middleware to the API.

        Args:
            middleware_class: Middleware class (e.g., BaseHTTPMiddleware subclass)
            **options: Middleware-specific configuration options

        Example:
            from starlette.middleware.base import BaseHTTPMiddleware
            import time

            class TimingMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    start = time.time()
                    response = await call_next(request)
                    elapsed = time.time() - start
                    response.headers["X-Process-Time"] = str(elapsed)
                    return response

            app = Application.api(name="my-api")
            app.add_middleware(TimingMiddleware)
        """
        self.fastapi.add_middleware(middleware_class, **options)
        logger.debug(f"Added middleware: {middleware_class.__name__}")

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
