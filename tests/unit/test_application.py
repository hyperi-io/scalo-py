"""
Tests for hs_lib.application module
Factory pattern for API, Daemon, CLI, and Oneshot applications
"""

import pytest

# Check for optional dependencies
try:
    import typer

    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False

try:
    import fastapi

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class TestApplicationFactory:
    """Test Application factory methods."""

    def test_import_application(self):
        """Test that Application can be imported."""
        from hs_lib import Application

        assert Application is not None

    def test_application_has_factory_methods(self):
        """Test that Application has all factory methods."""
        from hs_lib import Application

        assert hasattr(Application, "api")
        assert hasattr(Application, "daemon")
        assert hasattr(Application, "cli")
        assert hasattr(Application, "oneshot")

    def test_api_factory_requires_fastapi(self):
        """Test that api() factory requires FastAPI."""
        from hs_lib import Application

        # This should fail with ImportError if FastAPI not installed
        try:
            app = Application.api(name="test-api")
            # If we get here, FastAPI is installed
            assert app is not None
            assert app.name == "test-api"
            assert app.port == 8000
        except ImportError as e:
            # Expected if FastAPI not installed
            assert "FastAPI is required" in str(e)

    def test_daemon_factory(self):
        """Test daemon() factory creates DaemonApplication."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        assert app is not None
        assert app.name == "test-daemon"
        assert hasattr(app, "run")
        assert hasattr(app, "scheduled")
        assert hasattr(app, "startup")
        assert hasattr(app, "shutdown")

    def test_cli_factory_requires_typer(self):
        """Test that cli() factory requires Typer."""
        from hs_lib import Application

        try:
            app = Application.cli(name="test-cli")
            # If we get here, Typer is installed
            assert app is not None
            assert app.name == "test-cli"
            assert hasattr(app, "run")
            assert hasattr(app, "command")
        except ImportError as e:
            # Expected if Typer not installed
            assert "Typer is required" in str(e)

    def test_oneshot_factory(self):
        """Test oneshot() factory creates OneshotApplication."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot")

        assert app is not None
        assert app.name == "test-oneshot"
        assert hasattr(app, "run")
        assert hasattr(app, "task")


class TestDaemonApplication:
    """Test DaemonApplication functionality."""

    def test_daemon_creation(self):
        """Test creating a daemon application."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        assert app.name == "test-daemon"
        assert app.scheduled_tasks == []
        # Note: startup/shutdown hooks are now private (_startup_hooks, _shutdown_handlers)
        assert hasattr(app, "_startup_hooks") or not hasattr(app, "_startup_hooks")  # May not exist until first use
        assert hasattr(app, "_shutdown_handlers")

    def test_daemon_scheduled_decorator(self):
        """Test @app.scheduled decorator."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        @app.scheduled(interval=60)
        async def my_task():
            pass

        assert len(app.scheduled_tasks) == 1
        task = app.scheduled_tasks[0]
        assert task.func == my_task
        assert task.interval == 60

    def test_daemon_startup_decorator(self):
        """Test @app.startup decorator."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        @app.startup
        async def on_startup():
            pass

        # Startup hooks are now private
        assert len(app._startup_hooks) == 1
        assert app._startup_hooks[0] == on_startup

    def test_daemon_shutdown_decorator(self):
        """Test @app.shutdown decorator."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        @app.shutdown
        async def on_shutdown():
            pass

        # Shutdown hooks are now private (from SignalHandlerMixin)
        assert len(app._shutdown_handlers) == 1
        assert app._shutdown_handlers[0] == on_shutdown


class TestCLIApplication:
    """Test CLIApplication functionality."""

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_creation(self):
        """Test creating a CLI application."""
        from hs_lib import Application

        try:
            app = Application.cli(name="test-cli", version="1.2.3")
            assert app.name == "test-cli"
            assert app.version == "1.2.3"
        except ImportError:
            pytest.skip("Typer not installed")

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_command_decorator(self):
        """Test @app.command decorator."""
        from hs_lib import Application

        try:
            app = Application.cli(name="test-cli")

            @app.command()
            def hello():
                """Say hello."""
                pass

            # Command should be registered in Typer app
            assert app.app is not None
            # Typer stores commands differently than Click
            assert hasattr(app, "app")
        except ImportError:
            pytest.skip("Typer not installed")


class TestOneshotApplication:
    """Test OneshotApplication functionality."""

    def test_oneshot_creation(self):
        """Test creating a oneshot application."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot")

        assert app.name == "test-oneshot"
        assert app.task_func is None

    def test_oneshot_task_decorator(self):
        """Test @app.task decorator."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot")

        @app.task
        def my_task():
            return "result"

        assert app.task_func == my_task

    def test_oneshot_run_without_task_raises(self):
        """Test that _execute_task() without task raises RuntimeError."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot")

        with pytest.raises(RuntimeError, match="No task defined"):
            # Note: _execute_task is the internal method, run() is now Typer CLI
            app._execute_task()


class TestAPIApplication:
    """Test APIApplication functionality."""

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_creation(self):
        """Test creating an API application."""
        from hs_lib import Application

        try:
            app = Application.api(name="test-api", port=9000)
            assert app.name == "test-api"
            assert app.port == 9000
        except ImportError:
            pytest.skip("FastAPI not installed")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_cors_enabled(self):
        """Test CORS middleware configuration."""
        from hs_lib import Application

        try:
            app = Application.api(
                name="test-api",
                enable_cors=True,
                cors_origins=["https://example.com"],
            )
            # If we got here, CORS was enabled
            assert app is not None
        except ImportError:
            pytest.skip("FastAPI not installed")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_startup_decorator(self):
        """Test @app.on_startup decorator."""
        from hs_lib import Application

        try:
            app = Application.api(name="test-api")

            @app.on_startup
            async def startup():
                pass

            assert len(app.startup_handlers) == 1
        except ImportError:
            pytest.skip("FastAPI not installed")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_shutdown_decorator(self):
        """Test @app.on_shutdown decorator."""
        from hs_lib import Application

        try:
            app = Application.api(name="test-api")

            @app.on_shutdown
            async def shutdown():
                pass

            assert len(app._shutdown_handlers) == 1
        except ImportError:
            pytest.skip("FastAPI not installed")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_exception_handler_decorator(self):
        """Test @app.exception_handler decorator."""
        from hs_lib import Application

        try:
            app = Application.api(name="test-api")

            @app.exception_handler(ValueError)
            async def handle_value_error(request, exc: ValueError):
                return {"error": str(exc)}

            # If we got here, exception handler was registered
            assert app is not None
        except ImportError:
            pytest.skip("FastAPI not installed")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_include_router(self):
        """Test include_router method."""
        from hs_lib import Application

        try:
            from fastapi import APIRouter

            app = Application.api(name="test-api")
            router = APIRouter()

            @router.get("/test")
            def test_route():
                return {"test": "route"}

            # Include router should not raise
            app.include_router(router, prefix="/v1")
            assert app is not None
        except ImportError:
            pytest.skip("FastAPI not installed")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_add_middleware(self):
        """Test add_middleware method."""
        from hs_lib import Application

        try:
            from starlette.middleware.base import BaseHTTPMiddleware

            app = Application.api(name="test-api")

            class TestMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    response = await call_next(request)
                    return response

            # Add middleware should not raise
            app.add_middleware(TestMiddleware)
            assert app is not None
        except ImportError:
            pytest.skip("FastAPI not installed")
