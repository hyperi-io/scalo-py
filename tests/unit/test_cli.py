"""Tests for hyperlib.application.cli module."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest


class TestCLIApplication:
    """Test CLI application factory."""

    def test_cli_application_creation(self):
        """Test creating a CLI application."""
        from hyperlib import Application

        app = Application.cli(name="test-cli", version="1.0.0")

        assert app.name == "test-cli"
        assert app.version == "1.0.0"
        assert app.group is not None

    def test_cli_auto_version_detection(self):
        """Test automatic version detection from package metadata."""
        from hyperlib import Application

        # Should detect hyperlib's version or return "unknown"
        app = Application.cli(name="hyperlib")

        # Version should be detected or "unknown"
        assert app.version is not None
        assert isinstance(app.version, str)

    def test_cli_version_unknown_for_nonexistent_package(self):
        """Test version detection for non-existent package."""
        from hyperlib import Application

        app = Application.cli(name="nonexistent-package-12345")

        assert app.version == "unknown"

    def test_cli_command_registration(self):
        """Test registering commands."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.command()
        def hello():
            """Say hello."""
            pass

        # Command should be registered
        assert "hello" in app.group.commands

    def test_cli_option_decorator(self):
        """Test option decorator."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.command()
        @app.option("--verbose", "-v", is_flag=True)
        def mytest(verbose):
            """Test command with option."""
            return verbose

        # Command should be registered
        assert "mytest" in app.group.commands

    def test_cli_argument_decorator(self):
        """Test argument decorator."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.command()
        @app.argument("filename")
        def processfile(filename):
            """Process a file."""
            return filename

        assert "processfile" in app.group.commands


class TestEnvOverride:
    """Test environment variable override functionality."""

    def test_env_override_callback(self):
        """Test env override callback function."""
        from hyperlib.application.cli import CLIApplication

        # Mock Click parameter
        param = mock.Mock()
        param.name = "target"

        # Test without env var
        with mock.patch.dict(os.environ, {}, clear=True):
            result = CLIApplication.env_override_callback(None, param, "cli-value")
            assert result == "cli-value"

        # Test with env var
        with mock.patch.dict(os.environ, {"TARGET": "env-value"}):
            result = CLIApplication.env_override_callback(None, param, "cli-value")
            assert result == "env-value"

    def test_option_with_env_auto_derive(self):
        """Test option_with_env with auto-derived env var."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.command()
        @app.option_with_env("--target", "-t", help="Deployment target")
        def deploy(target):
            """Deploy application."""
            return target

        # Command should be registered
        assert "deploy" in app.group.commands

    def test_option_with_env_custom_var(self):
        """Test option_with_env with custom env var name."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.command()
        @app.option_with_env("--host", env_var="CUSTOM_HOST", help="Server host")
        def connect(host):
            """Connect to server."""
            return host

        assert "connect" in app.group.commands


class TestCLIGroupCommands:
    """Test CLI command groups."""

    def test_group_command_creation(self):
        """Test creating command groups."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.group_command()
        def database():
            """Database management commands."""
            pass

        # Group should be registered
        assert "database" in app.group.commands

    def test_subcommand_in_group(self):
        """Test adding subcommands to groups."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        @app.group_command()
        def db():
            """Database commands."""
            pass

        @db.command()
        def migrate():
            """Run migrations."""
            pass

        # Subcommand should exist
        assert "migrate" in db.commands


class TestGlobalOptions:
    """Test global CLI options."""

    def test_verbose_flag_added(self):
        """Test that verbose flag is added by default."""
        from hyperlib import Application

        app = Application.cli(name="test-cli", add_verbose=True)

        # Verbose flag should be in group callback
        assert app.group.callback is not None

    def test_quiet_flag_added(self):
        """Test that quiet flag is added by default."""
        from hyperlib import Application

        app = Application.cli(name="test-cli", add_quiet=True)

        # Quiet flag should be in group callback
        assert app.group.callback is not None

    def test_version_option_added(self):
        """Test that version option is added by default."""
        from hyperlib import Application

        app = Application.cli(name="test-cli", version="1.2.3", add_version=True)

        # Version should be set
        assert app.version == "1.2.3"

    def test_disable_global_options(self):
        """Test disabling global options."""
        from hyperlib import Application

        app = Application.cli(
            name="test-cli",
            add_verbose=False,
            add_quiet=False,
            add_version=False
        )

        # Should still create app successfully
        assert app.name == "test-cli"


class TestAddCommand:
    """Test programmatic command addition."""

    def test_add_command_programmatically(self):
        """Test adding commands programmatically."""
        from hyperlib import Application

        app = Application.cli(name="test-cli")

        def my_command():
            """My custom command."""
            pass

        app.add_command(my_command, name="custom")

        # Command should be registered
        assert "custom" in app.group.commands


class TestTargetConfig:
    """Test multi-environment configuration."""

    def test_get_target_config_with_file(self):
        """Test loading target configuration from file."""
        from hyperlib.config import get_target_config

        # Create temp targets file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            f.write("""
default_target: development

targets:
  production:
    database_url: postgresql://prod.example.com/db
    api_key: prod-key-123

  development:
    database_url: postgresql://localhost/db
    api_key: dev-key-123
""")
            targets_file = f.name

        try:
            # Load production config
            config = get_target_config(target="production", targets_file=targets_file)

            assert config["target_name"] == "production"
            assert config["database_url"] == "postgresql://prod.example.com/db"
            assert config["api_key"] == "prod-key-123"

            # Load development config
            config = get_target_config(target="development", targets_file=targets_file)

            assert config["target_name"] == "development"
            assert config["database_url"] == "postgresql://localhost/db"

        finally:
            Path(targets_file).unlink()

    def test_get_target_config_default_target(self):
        """Test using default target from config file."""
        from hyperlib.config import get_target_config

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            f.write("""
default_target: staging

targets:
  staging:
    env: staging
  production:
    env: production
""")
            targets_file = f.name

        try:
            # Should use default_target
            config = get_target_config(targets_file=targets_file)

            assert config["target_name"] == "staging"
            assert config["env"] == "staging"

        finally:
            Path(targets_file).unlink()

    def test_get_target_config_env_var_override(self):
        """Test TARGET env var overrides default target."""
        from hyperlib.config import get_target_config

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            f.write("""
default_target: development

targets:
  development:
    env: dev
  production:
    env: prod
""")
            targets_file = f.name

        try:
            with mock.patch.dict(os.environ, {"TARGET": "production"}):
                config = get_target_config(targets_file=targets_file)

                assert config["target_name"] == "production"
                assert config["env"] == "prod"

        finally:
            Path(targets_file).unlink()

    def test_get_target_config_missing_target(self):
        """Test error when target doesn't exist."""
        from hyperlib.config import get_target_config

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            f.write("""
targets:
  development:
    env: dev
""")
            targets_file = f.name

        try:
            with pytest.raises(ValueError, match="not found in configuration"):
                get_target_config(target="nonexistent", targets_file=targets_file)

        finally:
            Path(targets_file).unlink()

    def test_get_target_config_missing_file(self):
        """Test error when targets file doesn't exist."""
        from hyperlib.config import get_target_config

        with pytest.raises(FileNotFoundError):
            get_target_config(targets_file="/nonexistent/targets.yaml")


class TestInitConfigDirectory:
    """Test config directory initialization."""

    def test_init_config_directory_creates_structure(self):
        """Test that init creates directory structure."""
        from hyperlib.config import init_config_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = init_config_directory(
                app_name="test-app",
                config_dir=tmpdir,
                create_targets=False,
                create_env=False
            )

            assert config_dir.exists()
            assert (config_dir / "config").exists()

    def test_init_config_directory_creates_targets(self):
        """Test that init creates targets.yaml template."""
        from hyperlib.config import init_config_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = init_config_directory(
                app_name="test-app",
                config_dir=tmpdir,
                create_targets=True,
                create_env=False
            )

            targets_file = config_dir / "targets.yaml"
            assert targets_file.exists()

            # Check template content
            content = targets_file.read_text()
            assert "default_target" in content
            assert "production" in content
            assert "development" in content

    def test_init_config_directory_creates_env(self):
        """Test that init creates .env template."""
        from hyperlib.config import init_config_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = init_config_directory(
                app_name="test-app",
                config_dir=tmpdir,
                create_targets=False,
                create_env=True
            )

            env_file = config_dir / ".env"
            assert env_file.exists()

            # Check template content
            content = env_file.read_text()
            assert "TARGET=" in content

    def test_init_config_directory_doesnt_overwrite(self):
        """Test that init doesn't overwrite existing files."""
        from hyperlib.config import init_config_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            # Create existing targets file
            targets_file = config_dir / "targets.yaml"
            targets_file.write_text("existing content")

            # Init should not overwrite
            init_config_directory(
                app_name="test-app",
                config_dir=tmpdir,
                create_targets=True
            )

            # Content should be unchanged
            assert targets_file.read_text() == "existing content"

    def test_init_config_directory_with_default_app_name(self):
        """Test init with APP_NAME from config."""
        from hyperlib.config import init_config_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            # Should use APP_NAME from hyperlib.config
            config_dir = init_config_directory(
                config_dir=tmpdir,
                create_targets=False,
                create_env=False
            )

            assert config_dir.exists()
