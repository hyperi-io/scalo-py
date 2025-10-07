"""
End-to-end tests for hyperlib.application
Tests actual decorator and runtime behavior
"""

import pytest

# Check for optional dependencies
try:
    import click

    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False

try:
    import fastapi
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestAPIE2E:
    """End-to-end tests for API application."""

    def test_api_route_decorator_works(self):
        """Test that @app.route actually creates routes."""
        from hyperlib import Application

        app = Application.api(name="test-api", port=8000)

        @app.route("/test")
        def test_endpoint():
            return {"message": "test"}

        # Verify route was registered
        client = TestClient(app.fastapi)
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"message": "test"}

    def test_api_health_endpoints_work(self):
        """Test default health endpoints."""
        from hyperlib import Application

        app = Application.api(name="test-api")
        client = TestClient(app.fastapi)

        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "test-api"

        # Test ready endpoint
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_api_startup_shutdown_called(self):
        """Test startup and shutdown decorators are called."""
        from hyperlib import Application

        app = Application.api(name="test-api")

        startup_called = []
        shutdown_called = []

        @app.on_startup
        async def startup():
            startup_called.append(True)

        @app.on_shutdown
        async def shutdown():
            shutdown_called.append(True)

        # Create test client (triggers startup)
        with TestClient(app.fastapi) as client:
            # Startup should have been called
            assert len(startup_called) == 1

        # Shutdown should have been called after context exit
        assert len(shutdown_called) == 1

    def test_api_exception_handler_works(self):
        """Test exception handler decorator."""
        from hyperlib import Application
        from fastapi.responses import JSONResponse

        app = Application.api(name="test-api")

        @app.exception_handler(ValueError)
        async def handle_value_error(request, exc: ValueError):
            return JSONResponse(
                status_code=400,
                content={"error": "Value error", "detail": str(exc)},
            )

        @app.route("/error")
        def error_endpoint():
            raise ValueError("Test error")

        client = TestClient(app.fastapi)
        response = client.get("/error")

        assert response.status_code == 400
        assert response.json()["error"] == "Value error"
        assert "Test error" in response.json()["detail"]


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="Click not installed")
class TestCLIE2E:
    """End-to-end tests for CLI application."""

    def test_cli_command_works(self):
        """Test that @app.command decorator works."""
        from hyperlib import Application
        from click.testing import CliRunner

        app = Application.cli(name="test-cli")

        @app.command()
        def hello():
            """Say hello."""
            import click

            click.echo("Hello World")

        runner = CliRunner()
        result = runner.invoke(app.group, ["hello"])

        assert result.exit_code == 0
        assert "Hello World" in result.output

    def test_cli_without_logging_flags(self):
        """Test CLI without verbose/quiet flags (avoid logging issues in tests)."""
        from hyperlib import Application
        from click.testing import CliRunner

        # Create app without verbose/quiet to avoid logging conflicts
        app = Application.cli(
            name="test-cli",
            version="1.0.0",
            add_verbose=False,
            add_quiet=False,
        )

        @app.command()
        def process():
            """Process something."""
            import click

            click.echo("Processing")

        runner = CliRunner()
        result = runner.invoke(app.group, ["process"])
        assert result.exit_code == 0
        assert "Processing" in result.output

    def test_cli_version_flag_works(self):
        """Test built-in --version flag."""
        from hyperlib import Application
        from click.testing import CliRunner

        app = Application.cli(name="test-cli", version="2.5.3")

        runner = CliRunner()
        result = runner.invoke(app.group, ["--version"])

        assert result.exit_code == 0
        assert "2.5.3" in result.output


class TestDaemonE2E:
    """End-to-end tests for Daemon application."""

    def test_daemon_scheduled_decorator_works(self):
        """Test that @app.scheduled decorator registers tasks."""
        from hyperlib import Application

        app = Application.daemon(name="test-daemon")

        task_called = []

        @app.scheduled(interval=1)
        async def my_task():
            task_called.append(True)

        # Verify task was registered
        assert len(app.scheduled_tasks) == 1
        assert app.scheduled_tasks[0][0] == my_task
        assert app.scheduled_tasks[0][1] == 1  # interval

    def test_daemon_startup_shutdown_hooks(self):
        """Test startup/shutdown hooks registration."""
        from hyperlib import Application

        app = Application.daemon(name="test-daemon")

        @app.startup
        async def on_start():
            pass

        @app.shutdown
        async def on_stop():
            pass

        assert len(app.startup_hooks) == 1
        assert len(app.shutdown_hooks) == 1


class TestOneshotE2E:
    """End-to-end tests for Oneshot application."""

    def test_oneshot_task_decorator_works(self):
        """Test that @app.task decorator works."""
        from hyperlib import Application

        app = Application.oneshot(name="test-oneshot")

        @app.task
        def my_task():
            return "success"

        assert app.task_func == my_task

    def test_oneshot_run_without_decorator_raises(self):
        """Test that run() without task raises ValueError."""
        from hyperlib import Application

        app = Application.oneshot(name="test-oneshot")

        with pytest.raises(ValueError, match="No task function registered"):
            app.run()
