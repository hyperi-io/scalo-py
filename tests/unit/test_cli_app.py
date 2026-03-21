# Project:   hyperi-pylib
# File:      tests/unit/test_cli_app.py
# Purpose:   Unit tests for DfeApp CLI framework
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for the DfeApp CLI framework.

Tests CommonArgs, VersionInfo, error types, and DfeApp lifecycle
using Typer's CliRunner for CLI integration testing.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from hyperi_pylib.cli.app import CommonArgs, DfeApp, _build_typer_app, _is_async_overridden
from hyperi_pylib.cli.error import (
    CliError,
    ConfigError,
    InvalidArgumentError,
    LoggerError,
    ServiceError,
)
from hyperi_pylib.cli.version_info import VersionInfo

runner = CliRunner()


# --- CommonArgs tests ---


class TestCommonArgs:
    def test_effective_log_level_default(self):
        args = CommonArgs()
        assert args.effective_log_level() == "INFO"

    def test_effective_log_level_verbose(self):
        args = CommonArgs(verbose=True)
        assert args.effective_log_level() == "DEBUG"

    def test_effective_log_level_quiet(self):
        args = CommonArgs(quiet=True)
        assert args.effective_log_level() == "ERROR"

    def test_effective_log_level_custom(self):
        args = CommonArgs(log_level="warning")
        assert args.effective_log_level() == "WARNING"

    def test_verbose_takes_precedence_over_log_level(self):
        args = CommonArgs(log_level="error", verbose=True)
        assert args.effective_log_level() == "DEBUG"

    def test_quiet_takes_precedence_over_log_level(self):
        args = CommonArgs(log_level="debug", quiet=True)
        assert args.effective_log_level() == "ERROR"

    def test_defaults(self):
        args = CommonArgs()
        assert args.config is None
        assert args.log_level == "info"
        assert args.log_format == "auto"
        assert args.metrics_addr == "0.0.0.0:9090"
        assert args.verbose is False
        assert args.quiet is False


# --- VersionInfo tests ---


class TestVersionInfo:
    def test_new(self):
        v = VersionInfo("dfe-loader", "1.9.7")
        assert v.name == "dfe-loader"
        assert v.version == "1.9.7"
        assert v.commit is None
        assert v.build_date is None
        assert v.python_version is None
        assert v.platform is None
        assert isinstance(v.pylib_version, str)

    def test_builder_with_commit(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_commit("abc1234")
        assert v.commit == "abc1234"

    def test_builder_with_build_date(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_build_date("2026-03-04")
        assert v.build_date == "2026-03-04"

    def test_builder_with_python_version(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_python_version("3.12.1")
        assert v.python_version == "3.12.1"

    def test_builder_with_python_version_auto(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_python_version()
        assert v.python_version is not None
        assert "." in v.python_version

    def test_builder_with_platform(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_platform("Linux-6.1")
        assert v.platform == "Linux-6.1"

    def test_builder_with_platform_auto(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_platform()
        assert v.platform is not None

    def test_builder_chaining(self):
        v = (
            VersionInfo("dfe-loader", "1.9.7")
            .with_commit("abc1234")
            .with_build_date("2026-03-04")
            .with_python_version("3.12.1")
            .with_platform("Linux-6.1")
        )
        assert v.commit == "abc1234"
        assert v.build_date == "2026-03-04"
        assert v.python_version == "3.12.1"
        assert v.platform == "Linux-6.1"

    def test_short_with_commit(self):
        v = VersionInfo("dfe-loader", "1.9.7").with_commit("abc1234")
        assert v.short() == "dfe-loader 1.9.7 (abc1234)"

    def test_short_without_commit(self):
        v = VersionInfo("dfe-loader", "1.9.7")
        assert v.short() == "dfe-loader 1.9.7"

    def test_display_minimal(self):
        v = VersionInfo("dfe-loader", "1.9.7")
        output = str(v)
        assert "dfe-loader 1.9.7" in output
        assert "pylib:" in output

    def test_display_full(self):
        v = (
            VersionInfo("dfe-loader", "1.9.7")
            .with_commit("abc1234")
            .with_build_date("2026-03-04")
            .with_python_version("3.12.1")
            .with_platform("Linux-6.1")
        )
        output = str(v)
        assert "dfe-loader 1.9.7" in output
        assert "commit:  abc1234" in output
        assert "built:   2026-03-04" in output
        assert "python:  3.12.1" in output
        assert "target:  Linux-6.1" in output
        assert "pylib:" in output


# --- Error type tests ---


class TestCliErrors:
    def test_cli_error_is_exception(self):
        assert issubclass(CliError, Exception)

    def test_config_error_is_cli_error(self):
        assert issubclass(ConfigError, CliError)

    def test_logger_error_is_cli_error(self):
        assert issubclass(LoggerError, CliError)

    def test_service_error_is_cli_error(self):
        assert issubclass(ServiceError, CliError)

    def test_invalid_argument_error_is_cli_error(self):
        assert issubclass(InvalidArgumentError, CliError)

    def test_error_message(self):
        err = ConfigError("missing database.host")
        assert str(err) == "missing database.host"

    def test_catch_cli_error_catches_subtypes(self):
        with pytest.raises(CliError):
            raise ServiceError("boom")


# --- DfeApp tests ---


class _SyncApp(DfeApp):
    """Test app with sync run_service."""

    name = "test-sync"
    env_prefix = "TEST_SYNC"

    def __init__(self):
        super().__init__()
        self.ran = False
        self.received_config = None

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.1.0").with_commit("test123")

    def run_service(self, config: Any) -> None:
        self.ran = True
        self.received_config = config


class _AsyncApp(DfeApp):
    """Test app with async run_service_async."""

    name = "test-async"
    env_prefix = "TEST_ASYNC"

    def __init__(self):
        super().__init__()
        self.ran_async = False

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.2.0")

    def run_service(self, config: Any) -> None:
        pass

    async def run_service_async(self, config: Any) -> None:
        self.ran_async = True


class _CustomCommandApp(DfeApp):
    """Test app with custom subcommands."""

    name = "test-custom"
    env_prefix = "TEST_CUSTOM"

    def __init__(self):
        super().__init__()
        self.custom_ran = False

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.3.0")

    def run_service(self, config: Any) -> None:
        pass

    def register_commands(self, app: Any) -> None:
        from typer import Argument

        @app.command()
        def greet(name: str = Argument("world", help="Name to greet")):
            """Say hello."""
            print(f"hello {name}")
            self.custom_ran = True


class TestDfeApp:
    def test_subclass_requires_name(self):
        with pytest.raises(TypeError, match="must define 'name'"):

            class _BadApp(DfeApp):
                env_prefix = "BAD"

                def version_info(self):
                    return VersionInfo("bad", "0.0.0")

                def run_service(self, config):
                    pass

    def test_subclass_requires_env_prefix(self):
        with pytest.raises(TypeError, match="must define 'env_prefix'"):

            class _BadApp(DfeApp):
                name = "bad"

                def version_info(self):
                    return VersionInfo("bad", "0.0.0")

                def run_service(self, config):
                    pass

    def test_version_command(self):
        app = _SyncApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, ["version"])
        assert result.exit_code == 0
        assert "test-sync 0.1.0" in result.output
        assert "commit:  test123" in result.output
        assert "pylib:" in result.output

    def test_help_shows_subcommands(self):
        app = _SyncApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "version" in result.output
        assert "config-check" in result.output

    def test_no_args_shows_help(self):
        app = _SyncApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, [])
        assert result.exit_code == 2
        assert "run" in result.output

    def test_verbose_and_quiet_mutually_exclusive(self):
        app = _SyncApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, ["run", "--verbose", "--quiet"])
        assert result.exit_code == 1

    def test_custom_subcommands(self):
        app = _CustomCommandApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, ["greet", "derek"])
        assert result.exit_code == 0
        assert "hello derek" in result.output

    def test_is_async_overridden_sync_app(self):
        app = _SyncApp()
        assert _is_async_overridden(app) is False

    def test_is_async_overridden_async_app(self):
        app = _AsyncApp()
        assert _is_async_overridden(app) is True

    def test_metrics_attributes_initialised_on_dfeapp(self):
        """DfeApp.__init__ sets _metrics and _app_metrics to None."""
        app = _SyncApp()
        assert app._metrics is None
        assert app._app_metrics is None

    def test_metrics_auto_init_after_run(self):
        """After run, _metrics and _app_metrics are set when metrics extra is available."""
        pytest.importorskip("hyperi_pylib.metrics", reason="metrics extra not installed")

        app = _SyncApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, ["run"])
        assert result.exit_code == 0
        assert app._metrics is not None
        assert app._app_metrics is not None

    def test_metrics_init_failure_does_not_crash_service(self, monkeypatch):
        """Metrics init failure is non-fatal — service still runs."""
        import sys
        import types

        # Inject a broken create_metrics into the metrics module namespace
        # so the import succeeds but the call raises
        fake_metrics = types.ModuleType("hyperi_pylib.metrics")

        def broken_create_metrics(*args, **kwargs):
            raise RuntimeError("simulated metrics failure")

        fake_metrics.create_metrics = broken_create_metrics
        monkeypatch.setitem(sys.modules, "hyperi_pylib.metrics", fake_metrics)

        # Also ensure AppMetrics import succeeds from dfe_groups
        fake_dfe_groups = types.ModuleType("hyperi_pylib.metrics.dfe_groups")

        class _FakeAppMetrics:
            def __init__(self, *args, **kwargs):
                pass

        fake_dfe_groups.AppMetrics = _FakeAppMetrics
        monkeypatch.setitem(sys.modules, "hyperi_pylib.metrics.dfe_groups", fake_dfe_groups)

        app = _SyncApp()
        typer_app = _build_typer_app(app)
        result = runner.invoke(typer_app, ["run"])

        # Service must still run — metrics failure is non-fatal
        assert result.exit_code == 0
        assert app.ran is True
        assert app._metrics is None
        assert app._app_metrics is None
