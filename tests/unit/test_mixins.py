"""
Tests for application mixins.
"""

import signal
import threading
import time

import pytest
import typer.testing

from hyperlib.application.mixins import (
    CLIExecutableMixin,
    ProfileMixin,
    SignalHandlerMixin,
)


class TestProfileMixin:
    """Test ProfileMixin."""

    def test_profile_loading(self):
        """Test profile loads correctly."""

        class TestApp(ProfileMixin):
            pass

        app = TestApp(profile="dev")
        assert app.profile_name == "dev"
        assert app.profile["logging"]["format"] == "console"

    def test_profile_overrides(self):
        """Test profile overrides work."""

        class TestApp(ProfileMixin):
            pass

        app = TestApp(profile="dev", profile_overrides={"metrics": True, "metrics_port": 9091})
        assert app.profile["metrics"] is True
        assert app.profile["metrics_port"] == 9091

    def test_get_profile_setting(self):
        """Test getting profile settings."""

        class TestApp(ProfileMixin):
            pass

        app = TestApp(profile="dev")

        # Top-level key
        assert app.get_profile_setting("metrics") is False

        # Nested key
        assert app.get_profile_setting("logging.format") == "console"
        assert app.get_profile_setting("logging.level") == "DEBUG"

        # Missing key with default
        assert app.get_profile_setting("missing.key", "default") == "default"

        # Missing key without default
        assert app.get_profile_setting("missing.key") is None


class TestSignalHandlerMixin:
    """Test SignalHandlerMixin."""

    def test_signal_handlers_registered(self):
        """Test signal handlers are registered."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        app = TestApp(profile="dev")

        # Verify shutdown event exists
        assert hasattr(app, "_shutdown_event")
        assert isinstance(app._shutdown_event, threading.Event)

    def test_on_shutdown_decorator(self):
        """Test on_shutdown decorator registers handlers."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        app = TestApp(profile="dev")

        handler_called = []

        @app.on_shutdown
        def cleanup():
            handler_called.append(True)

        assert len(app._shutdown_handlers) == 1
        assert cleanup in app._shutdown_handlers

    def test_is_shutting_down(self):
        """Test is_shutting_down flag."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        app = TestApp(profile="dev")
        assert app.is_shutting_down() is False

        # Simulate shutdown
        app._shutting_down = True
        assert app.is_shutting_down() is True

    def test_shutdown_handler_execution(self):
        """Test shutdown handlers are executed."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        app = TestApp(profile="dev")

        execution_order = []

        @app.on_shutdown
        def first():
            execution_order.append(1)

        @app.on_shutdown
        def second():
            execution_order.append(2)

        # Run handlers manually
        app._run_shutdown_handlers(timeout=5)

        assert execution_order == [1, 2]

    def test_shutdown_handler_exception_handling(self):
        """Test shutdown continues even if handler raises exception."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        app = TestApp(profile="dev")

        executed = []

        @app.on_shutdown
        def failing_handler():
            executed.append("failing")
            raise RuntimeError("Handler failed")

        @app.on_shutdown
        def successful_handler():
            executed.append("successful")

        # Run handlers - should not raise
        app._run_shutdown_handlers(timeout=5)

        # Both handlers should have executed
        assert "failing" in executed
        assert "successful" in executed

    def test_graceful_shutdown_disabled(self):
        """Test signal handlers not registered when disabled."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        # Create profile override to disable graceful shutdown
        app = TestApp(profile="dev", profile_overrides={"graceful_shutdown": False})

        # Handlers should still be initialized but not registered with signals
        assert hasattr(app, "_shutdown_handlers")


class TestCLIExecutableMixin:
    """Test CLIExecutableMixin."""

    def test_cli_created(self):
        """Test Typer CLI is created."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        assert hasattr(app, "cli")
        assert isinstance(app.cli, typer.Typer)
        assert app.name == "test-app"
        assert app.version == "1.0.0"

    def test_version_command(self):
        """Test version command works."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        runner = typer.testing.CliRunner()
        result = runner.invoke(app.cli, ["version"])

        assert result.exit_code == 0
        assert "test-app v1.0.0" in result.stdout

    def test_config_command_json(self):
        """Test config command with JSON output."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        runner = typer.testing.CliRunner()
        result = runner.invoke(app.cli, ["config", "--format=json"])

        assert result.exit_code == 0
        assert '"name": "test-app"' in result.stdout
        assert '"version": "1.0.0"' in result.stdout
        assert '"profile": "dev"' in result.stdout

    def test_validate_command(self):
        """Test validate command works."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        runner = typer.testing.CliRunner()
        result = runner.invoke(app.cli, ["validate"])

        assert result.exit_code == 0
        assert "Profile 'dev' loaded successfully" in result.stdout
        assert "Configuration is valid" in result.stdout

    def test_health_check_command_disabled(self):
        """Test health-check command when health checks disabled."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        runner = typer.testing.CliRunner()
        result = runner.invoke(app.cli, ["health-check"])

        assert result.exit_code == 1
        assert "Health checks not enabled" in result.stdout

    def test_health_check_command_enabled(self):
        """Test health-check command when health checks enabled."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="docker")

        runner = typer.testing.CliRunner()
        result = runner.invoke(app.cli, ["health-check"])

        assert result.exit_code == 0
        assert "Application is" in result.stdout

    def test_custom_command(self):
        """Test adding custom commands works."""

        class TestApp(CLIExecutableMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        @app.cli.command()
        def custom():
            """Custom command."""
            typer.echo("Custom command executed")

        runner = typer.testing.CliRunner()
        result = runner.invoke(app.cli, ["custom"])

        assert result.exit_code == 0
        assert "Custom command executed" in result.stdout


class TestMixinComposition:
    """Test multiple mixins working together."""

    def test_all_mixins_together(self):
        """Test all mixins compose correctly."""

        class TestApp(CLIExecutableMixin, SignalHandlerMixin, ProfileMixin):
            pass

        app = TestApp(name="test-app", version="1.0.0", profile="dev")

        # ProfileMixin
        assert hasattr(app, "profile")
        assert app.profile_name == "dev"

        # SignalHandlerMixin
        assert hasattr(app, "_shutdown_handlers")
        assert hasattr(app, "on_shutdown")

        # CLIExecutableMixin
        assert hasattr(app, "cli")
        assert app.name == "test-app"
        assert app.version == "1.0.0"

    def test_mro_order(self):
        """Test method resolution order is correct."""

        class TestApp(CLIExecutableMixin, SignalHandlerMixin, ProfileMixin):
            pass

        # Verify MRO includes all mixins
        mro = [cls.__name__ for cls in TestApp.__mro__]
        assert "CLIExecutableMixin" in mro
        assert "SignalHandlerMixin" in mro
        assert "ProfileMixin" in mro

    def test_profile_affects_signal_handling(self):
        """Test profile settings affect mixin behavior."""

        class TestApp(SignalHandlerMixin, ProfileMixin):
            pass

        # Dev profile - graceful shutdown enabled
        app_dev = TestApp(profile="dev")
        assert app_dev.profile["graceful_shutdown"] is True

        # Custom override - graceful shutdown disabled
        app_no_shutdown = TestApp(profile="dev", profile_overrides={"graceful_shutdown": False})
        assert app_no_shutdown.profile["graceful_shutdown"] is False
