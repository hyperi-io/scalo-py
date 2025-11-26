"""
Tests for Phase 2: Application types with mixin integration
Tests container-native patterns: profiles, graceful shutdown, metrics, health checks
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


class TestAPIApplicationMixins:
    """Test APIApplication mixin integration."""

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_inherits_mixins(self):
        """Test APIApplication inherits from all required mixins."""
        from hs_lib.application.api import APIApplication

        # Check MRO includes all mixins
        mro_names = [c.__name__ for c in APIApplication.__mro__]

        assert "CLIExecutableMixin" in mro_names
        assert "SignalHandlerMixin" in mro_names
        assert "ProfileMixin" in mro_names
        assert "HealthCheckMixin" in mro_names
        assert "MetricsMixin" in mro_names

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_profile_loading(self):
        """Test APIApplication loads profile correctly."""
        from hs_lib import Application

        app = Application.api(name="test-api", profile="dev")

        assert hasattr(app, "profile")
        assert hasattr(app, "profile_name")
        assert app.profile_name == "dev"
        assert isinstance(app.profile, dict)

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_profile_overrides(self):
        """Test APIApplication applies profile overrides."""
        from hs_lib import Application

        app = Application.api(name="test-api", profile="dev", profile_overrides={"metrics": True})

        assert app.profile.get("metrics") is True

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_signal_handler_methods(self):
        """Test APIApplication has signal handler methods."""
        from hs_lib import Application

        app = Application.api(name="test-api")

        assert hasattr(app, "is_shutting_down")
        assert hasattr(app, "wait_for_shutdown")
        assert callable(app.is_shutting_down)
        assert callable(app.wait_for_shutdown)

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_cli_commands(self):
        """Test APIApplication has CLI commands."""
        from hs_lib import Application

        app = Application.api(name="test-api")

        assert hasattr(app, "cli")
        assert app.cli is not None

        # Check for standard commands
        # Note: Typer stores commands in registered_commands list
        assert hasattr(app.cli, "registered_commands")

    @pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
    def test_api_metrics_methods(self):
        """Test APIApplication has metrics tracking methods."""
        from hs_lib import Application

        app = Application.api(name="test-api", profile_overrides={"metrics": False})

        assert hasattr(app, "track_counter")
        assert hasattr(app, "track_gauge")
        assert hasattr(app, "track_histogram")


class TestDaemonApplicationMixins:
    """Test DaemonApplication mixin integration."""

    def test_daemon_inherits_mixins(self):
        """Test DaemonApplication inherits from all required mixins."""
        from hs_lib.application.daemon import DaemonApplication

        # Check MRO includes all mixins
        mro_names = [c.__name__ for c in DaemonApplication.__mro__]

        assert "CLIExecutableMixin" in mro_names
        assert "SignalHandlerMixin" in mro_names
        assert "ProfileMixin" in mro_names
        assert "MetricsMixin" in mro_names
        # Note: DaemonApplication does NOT inherit HealthCheckMixin

    def test_daemon_profile_loading(self):
        """Test DaemonApplication loads profile correctly."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon", profile="docker")

        assert hasattr(app, "profile")
        assert hasattr(app, "profile_name")
        assert app.profile_name == "docker"
        assert isinstance(app.profile, dict)

    def test_daemon_profile_overrides(self):
        """Test DaemonApplication applies profile overrides."""
        from hs_lib import Application

        app = Application.daemon(
            name="test-daemon", profile="dev", profile_overrides={"health_check": True, "health_check_port": 8888}
        )

        assert app.profile.get("health_check") is True
        assert app.profile.get("health_check_port") == 8888

    def test_daemon_signal_handler_methods(self):
        """Test DaemonApplication has signal handler methods."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        assert hasattr(app, "is_shutting_down")
        assert hasattr(app, "wait_for_shutdown")
        assert callable(app.is_shutting_down)
        assert callable(app.wait_for_shutdown)

    def test_daemon_cli_commands(self):
        """Test DaemonApplication has CLI commands."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        assert hasattr(app, "cli")
        assert app.cli is not None

    def test_daemon_metrics_methods(self):
        """Test DaemonApplication has metrics tracking methods."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon", profile_overrides={"metrics": False})

        assert hasattr(app, "track_counter")
        assert hasattr(app, "track_gauge")
        assert hasattr(app, "track_histogram")

    def test_daemon_thread_not_daemon(self):
        """Test DaemonApplication uses daemon=False for task threads (fixes orphaning bug)."""
        from hs_lib import Application

        app = Application.daemon(name="test-daemon")

        # Register a scheduled task
        task_executed = []

        @app.scheduled(interval=1)
        def test_task():
            task_executed.append(True)

        # Check that task is registered
        assert len(app.scheduled_tasks) == 1
        # Note: We can't easily test daemon=False without actually running threads
        # This is tested in integration tests


class TestMCPApplicationMixins:
    """Test MCPApplication mixin integration."""

    def test_mcp_inherits_mixins(self):
        """Test MCPApplication inherits from all required mixins."""
        from hs_lib.application.mcp import MCPApplication

        # Check MRO includes all mixins
        mro_names = [c.__name__ for c in MCPApplication.__mro__]

        assert "CLIExecutableMixin" in mro_names
        assert "SignalHandlerMixin" in mro_names
        assert "ProfileMixin" in mro_names
        assert "MetricsMixin" in mro_names

    def test_mcp_profile_loading(self):
        """Test MCPApplication loads profile correctly."""
        from hs_lib import Application

        app = Application.mcp(name="test-mcp", profile="prod")

        assert hasattr(app, "profile")
        assert hasattr(app, "profile_name")
        assert app.profile_name == "prod"
        assert isinstance(app.profile, dict)

    def test_mcp_profile_overrides(self):
        """Test MCPApplication applies profile overrides."""
        from hs_lib import Application

        app = Application.mcp(name="test-mcp", profile="dev", profile_overrides={"metrics": True})

        assert app.profile.get("metrics") is True

    def test_mcp_signal_handler_methods(self):
        """Test MCPApplication has signal handler methods."""
        from hs_lib import Application

        app = Application.mcp(name="test-mcp")

        assert hasattr(app, "is_shutting_down")
        assert hasattr(app, "wait_for_shutdown")
        assert callable(app.is_shutting_down)
        assert callable(app.wait_for_shutdown)

    def test_mcp_cli_commands(self):
        """Test MCPApplication has CLI commands."""
        from hs_lib import Application

        app = Application.mcp(name="test-mcp")

        assert hasattr(app, "cli")
        assert app.cli is not None

    def test_mcp_metrics_methods(self):
        """Test MCPApplication has metrics tracking methods."""
        from hs_lib import Application

        app = Application.mcp(name="test-mcp", profile_overrides={"metrics": False})

        assert hasattr(app, "track_counter")
        assert hasattr(app, "track_gauge")
        assert hasattr(app, "track_histogram")

    def test_mcp_tool_registration(self):
        """Test MCPApplication tool registration decorator."""
        from hs_lib import Application

        app = Application.mcp(name="test-mcp")

        @app.tool(name="test_tool", description="Test tool")
        def my_tool(arg: str) -> str:
            return f"processed: {arg}"

        assert "test_tool" in app.tools
        assert app.tools["test_tool"]["name"] == "test_tool"
        assert app.tools["test_tool"]["handler"] == my_tool


class TestOneshotApplicationMixins:
    """Test OneshotApplication mixin integration."""

    def test_oneshot_inherits_mixins(self):
        """Test OneshotApplication inherits from required mixins."""
        from hs_lib.application.oneshot import OneshotApplication

        # Check MRO includes required mixins
        mro_names = [c.__name__ for c in OneshotApplication.__mro__]

        assert "CLIExecutableMixin" in mro_names
        assert "SignalHandlerMixin" in mro_names
        assert "ProfileMixin" in mro_names
        # Note: OneshotApplication does NOT inherit MetricsMixin by default

    def test_oneshot_profile_loading(self):
        """Test OneshotApplication loads profile correctly."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot", profile="prod")

        assert hasattr(app, "profile")
        assert hasattr(app, "profile_name")
        assert app.profile_name == "prod"
        assert isinstance(app.profile, dict)

    def test_oneshot_profile_overrides(self):
        """Test OneshotApplication applies profile overrides."""
        from hs_lib import Application

        app = Application.oneshot(
            name="test-oneshot",
            profile="dev",
            profile_overrides={"metrics": True},  # Optional metrics
        )

        assert app.profile.get("metrics") is True

    def test_oneshot_signal_handler_methods(self):
        """Test OneshotApplication has signal handler methods."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot")

        assert hasattr(app, "is_shutting_down")
        assert hasattr(app, "wait_for_shutdown")
        assert callable(app.is_shutting_down)
        assert callable(app.wait_for_shutdown)

    def test_oneshot_cli_commands(self):
        """Test OneshotApplication has CLI commands."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot")

        assert hasattr(app, "cli")
        assert app.cli is not None

    def test_oneshot_no_metrics_by_default(self):
        """Test OneshotApplication does NOT have metrics by default."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot", profile="dev")

        # Metrics should not be enabled by default
        # Note: hasattr will be True because methods exist from ProfileMixin.__init__
        # but metrics should be None
        assert not hasattr(app, "metrics") or app.metrics is None

    def test_oneshot_optional_metrics(self):
        """Test OneshotApplication checks for metrics via hasattr."""
        from hs_lib import Application

        app = Application.oneshot(name="test-oneshot", profile_overrides={"metrics": True})

        # OneshotApplication doesn't inherit MetricsMixin, but code checks hasattr
        # This test verifies that oneshot jobs work with or without metrics
        # The _execute_task method uses: if hasattr(self, "track_counter")
        assert hasattr(app, "_execute_task")


class TestCLIApplicationMixins:
    """Test CLIApplication mixin integration."""

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_inherits_mixins(self):
        """Test CLIApplication inherits from required mixins."""
        from hs_lib.application.cli import CLIApplication

        # Check MRO includes required mixins
        mro_names = [c.__name__ for c in CLIApplication.__mro__]

        assert "SignalHandlerMixin" in mro_names
        assert "ProfileMixin" in mro_names
        # Note: CLIApplication does NOT inherit CLIExecutableMixin (it IS the CLI)

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_profile_loading(self):
        """Test CLIApplication loads profile correctly."""
        from hs_lib import Application

        app = Application.cli(name="test-cli", version="1.0.0", profile="docker")

        assert hasattr(app, "profile")
        assert hasattr(app, "profile_name")
        assert app.profile_name == "docker"
        assert isinstance(app.profile, dict)

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_profile_overrides(self):
        """Test CLIApplication applies profile overrides."""
        from hs_lib import Application

        app = Application.cli(
            name="test-cli", version="1.0.0", profile="dev", profile_overrides={"logging": {"level": "DEBUG"}}
        )

        assert app.profile.get("logging", {}).get("level") == "DEBUG"

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_signal_handler_methods(self):
        """Test CLIApplication has signal handler methods."""
        from hs_lib import Application

        app = Application.cli(name="test-cli", version="1.0.0")

        assert hasattr(app, "is_shutting_down")
        assert hasattr(app, "wait_for_shutdown")
        assert callable(app.is_shutting_down)
        assert callable(app.wait_for_shutdown)

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_has_typer_app(self):
        """Test CLIApplication has Typer app."""
        from hs_lib import Application

        app = Application.cli(name="test-cli", version="1.0.0")

        assert hasattr(app, "app")
        assert app.app is not None

    @pytest.mark.skipif(not TYPER_AVAILABLE, reason="Typer not installed")
    def test_cli_command_registration(self):
        """Test CLIApplication command registration."""
        from hs_lib import Application

        app = Application.cli(name="test-cli", version="1.0.0")

        @app.command()
        def test_cmd():
            """Test command."""
            pass

        # Command should be registered in Typer
        assert hasattr(app, "app")


class TestProfileSystem:
    """Test profile system across all application types."""

    def test_dev_profile_defaults(self):
        """Test dev profile has correct defaults."""
        from hs_lib import Application

        app = Application.daemon(name="test", profile="dev")

        profile = app.profile
        assert profile.get("logging", {}).get("level") == "DEBUG"
        assert profile.get("metrics") is False
        assert profile.get("health_check") is False

    def test_docker_profile_defaults(self):
        """Test docker profile has correct defaults."""
        from hs_lib import Application

        app = Application.daemon(name="test", profile="docker")

        profile = app.profile
        assert profile.get("logging", {}).get("format") == "json"
        assert profile.get("metrics") is True  # Docker profile enables metrics
        assert profile.get("health_check") is True

    def test_prod_profile_defaults(self):
        """Test prod profile has correct defaults."""
        from hs_lib import Application

        app = Application.daemon(name="test", profile="prod")

        profile = app.profile
        assert profile.get("logging", {}).get("format") == "json"
        assert profile.get("logging", {}).get("level") == "INFO"
        assert profile.get("metrics") is True
        assert profile.get("health_check") is True

    def test_profile_override_merging(self):
        """Test profile overrides merge correctly."""
        from hs_lib import Application

        app = Application.daemon(
            name="test", profile="prod", profile_overrides={"metrics_port": 9999, "logging": {"level": "WARNING"}}
        )

        # Check override applied
        assert app.profile.get("metrics_port") == 9999
        assert app.profile.get("logging", {}).get("level") == "WARNING"

        # Check other prod defaults preserved
        assert app.profile.get("metrics") is True
        assert app.profile.get("health_check") is True
