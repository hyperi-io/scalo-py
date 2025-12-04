"""
hs-lib API Application
FastAPI-based REST API service with container-native patterns
"""

from collections.abc import Callable
from typing import Any

from ...logger import logger
from ..mixins import (
    CLIExecutableMixin,
    HealthCheckMixin,
    MetricsMixin,
    ProfileMixin,
    SignalHandlerMixin,
)


class APIApplication(
    CLIExecutableMixin,
    SignalHandlerMixin,
    ProfileMixin,
    HealthCheckMixin,
    MetricsMixin,
):
    """
    REST API service application using FastAPI.

    Provides container-native patterns out of the box:
    - Profile-based configuration (dev/docker/prod)
    - Graceful shutdown (SIGTERM/SIGINT)
    - Health endpoints (/health, /ready) for k8s probes
    - Automatic HTTP metrics (Prometheus/OTEL)
    - Typer CLI commands (serve, health-check, validate, version, config)

    Example (simple):
        app = Application.api(name="my-api", version="1.0.0", profile="prod")

        @app.route("/")
        def root():
            return {"message": "Hello"}

        if __name__ == "__main__":
            app.run()  # Runs Typer CLI

    Example (production):
        # Container CMD: python -m my_api serve --profile prod
        # Automatically gets: health checks, metrics, graceful shutdown

    Example (custom routes):
        app = Application.api(name="my-api", version="1.0.0")

        @app.route("/users/{user_id}")
        def get_user(user_id: int):
            return {"user_id": user_id}

        @app.post("/users")
        def create_user(name: str):
            return {"id": 123, "name": name}
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        profile: str = "dev",
        port: int = 8000,
        enable_cors: bool = False,
        cors_origins: list[str] | None = None,
        profile_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize API application.

        Args:
            name: Application name
            version: Application version
            profile: Environment profile ("dev", "docker", "prod")
            port: API server port (default: 8000)
            enable_cors: Enable CORS middleware
            cors_origins: List of allowed origins (default: ["*"])
            profile_overrides: Override profile settings
            **kwargs: Additional configuration options
        """
        # Initialize mixins (MRO: CLI -> Signal -> Profile -> Health -> Metrics)
        super().__init__(
            name=name,
            version=version,
            profile=profile,
            profile_overrides=profile_overrides,
            description=f"{name} - hs-lib API Service",
        )

        self.port = port
        self.startup_handlers: list[Callable] = []

        # Create FastAPI app
        try:
            from fastapi import FastAPI

            self.fastapi = FastAPI(
                title=name,
                description=f"{name} - hs-lib API Service",
                version=version,
            )
        except ImportError:
            raise ImportError(
                "FastAPI is required for API applications. Install it with: pip install fastapi uvicorn[standard]"
            )

        # Add CORS middleware if enabled
        if enable_cors:
            self._add_cors_middleware(cors_origins or ["*"])

        # Add health endpoints if enabled in profile
        if self.profile.get("health_check"):
            self._add_health_endpoints()

        # Add metrics middleware if enabled in profile
        if self.profile.get("metrics"):
            self._add_metrics_middleware()

        # Add serve command to CLI
        self._add_serve_command()

        logger.info(f"APIApplication '{name}' initialized (port={port}, profile={profile})")

    def _add_cors_middleware(self, origins: list[str]) -> None:
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

    def _add_health_endpoints(self) -> None:
        """Add /health and /ready endpoints for k8s probes."""

        @self.fastapi.get("/health")
        async def health():
            """Liveness probe - returns 200 if application is running."""
            return {"status": "healthy", "service": self.name}

        @self.fastapi.get("/ready")
        async def ready():
            """Readiness probe - checks dependencies."""
            # Run health check handlers if any registered
            if hasattr(self, "_health_check_handlers") and self._health_check_handlers:
                for handler in self._health_check_handlers:
                    try:
                        if not handler():
                            return {"status": "not ready", "service": self.name}
                    except Exception as e:
                        logger.error(f"Health check failed: {e}")
                        return {"status": "not ready", "error": "health check failed"}

            return {"status": "ready", "service": self.name}

        logger.debug("Health endpoints added: /health, /ready")

    def _add_metrics_middleware(self) -> None:
        """Add metrics collection middleware for HTTP requests."""
        import time

        from fastapi import Request, Response

        @self.fastapi.middleware("http")
        async def metrics_middleware(request: Request, call_next):
            """Track HTTP request metrics."""
            start_time = time.time()

            # Track request
            self.track_counter(
                "http_requests_total",
                labels={"method": request.method, "endpoint": request.url.path},
            )

            # Process request
            response: Response = await call_next(request)

            # Track duration
            duration = time.time() - start_time
            self.track_histogram(
                "http_request_duration_seconds",
                duration,
                labels={
                    "method": request.method,
                    "endpoint": request.url.path,
                    "status": str(response.status_code),
                },
            )

            return response

        logger.debug("Metrics middleware added")

    def _add_serve_command(self) -> None:
        """Add 'serve' command to CLI."""
        import typer

        @self.cli.command()
        def serve(
            host: str = typer.Option("0.0.0.0", help="Host to bind to"),  # nosec B104 - containerized app
            port: int = typer.Option(self.port, help="Port to bind to"),
            reload: bool = typer.Option(self.profile.get("reload", False), help="Enable auto-reload"),
        ):
            """Start the API server."""
            logger.info(f"Starting API server '{self.name}' on {host}:{port} (profile={self.profile_name})")

            try:
                import uvicorn

                uvicorn.run(
                    self.fastapi,
                    host=host,
                    port=port,
                    reload=reload,
                    log_config=None,  # Use hs_lib logger
                )
            except ImportError:
                typer.echo(
                    "Error: uvicorn is required. Install with: pip install uvicorn[standard]",
                    err=True,
                )
                raise typer.Exit(1)

    def get(self, path: str, **kwargs: Any) -> Callable:
        """Decorator to add GET route to API."""
        return self.fastapi.get(path, **kwargs)

    def route(self, path: str, **kwargs: Any) -> Callable:
        """
        Alias for get() for backward compatibility.

        Args:
            path: URL path (e.g., "/users/{user_id}")
            **kwargs: FastAPI route options (methods, status_code, etc.)

        Example:
            @app.route("/users/{user_id}")
            def get_user(user_id: int):
                return {"user_id": user_id}
        """
        return self.get(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable:
        """Decorator to add POST route."""
        return self.fastapi.post(path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable:
        """Decorator to add PUT route."""
        return self.fastapi.put(path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable:
        """Decorator to add DELETE route."""
        return self.fastapi.delete(path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable:
        """Decorator to add PATCH route."""
        return self.fastapi.patch(path, **kwargs)

    def add_route(
        self,
        path: str,
        endpoint: Callable,
        methods: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
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

    def include_router(self, router: Any, *, prefix: str = "", **kwargs: Any) -> None:
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

            app = Application.api(name="my-api")
            app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
        """
        self.fastapi.include_router(router, prefix=prefix, **kwargs)
        logger.debug(f"Included router with prefix: {prefix}")

    def add_middleware(self, middleware_class: Any, **options: Any) -> None:
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
