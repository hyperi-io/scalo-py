# Project:   hyperi-pylib
# File:      cli/app.py
# Purpose:   DfeApp application framework and lifecycle runner
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""DFE service application framework.

Provides the standard CLI lifecycle for Python DFE services, mirroring
hyperi-rustlib's cli::app module. Apps subclass ``DfeApp`` and get standard
subcommands (``run``, ``version``, ``config-check``) and common flags
(``--config``, ``--log-level``, ``--verbose``, ``--quiet``) for free.

**No ``top`` subcommand** — Python services are never on the hot path;
performance-critical data plane work is handled by Rust services. A TUI
metrics dashboard adds no value for Python control-plane services.

Example::

    from hyperi_pylib.cli import DfeApp, VersionInfo

    class MyService(DfeApp):
        name = "dfe-control-plane"
        env_prefix = "DFE_CP"

        def version_info(self) -> VersionInfo:
            return VersionInfo(self.name, "1.0.0")

        def run_service(self, config) -> None:
            print("running")

    if __name__ == "__main__":
        MyService().cli()
"""

from __future__ import annotations

import asyncio
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .error import CliError, ConfigError, LoggerError
from .output import print_error, print_info, print_success
from .version_info import VersionInfo

__all__ = [
    "CommonArgs",
    "DfeApp",
    "run_app",
]


@dataclass
class CommonArgs:
    """Standard CLI arguments for DFE services.

    Mirrors rustlib's ``CommonArgs`` struct. Populated from Typer callback
    parameters and provides integration methods for logger and config setup.
    """

    config: str | None = None
    """Path to configuration file."""

    log_level: str = "info"
    """Log level (debug, info, warning, error, critical)."""

    log_format: str = "auto"
    """Log output format (json, text, auto)."""

    metrics_addr: str = "0.0.0.0:9090"
    """Metrics server bind address."""

    verbose: bool = False
    """Enable verbose output (sets log level to debug)."""

    quiet: bool = False
    """Suppress all output except errors."""

    def effective_log_level(self) -> str:
        """Resolve the effective log level, accounting for --verbose and --quiet."""
        if self.verbose:
            return "DEBUG"
        if self.quiet:
            return "ERROR"
        return self.log_level.upper()

    def init_logger(self) -> None:
        """Initialise the hyperi-pylib logger with resolved settings.

        Sets the ``LOG_LEVEL`` and ``LOG_FORMAT`` environment variables
        before calling ``logger.setup()``, so the logger's own env-based
        detection picks up CLI overrides.

        Raises:
            LoggerError: If logger initialisation fails.
        """
        try:
            os.environ["LOG_LEVEL"] = self.effective_log_level()
            if self.log_format != "auto":
                os.environ["LOG_FORMAT"] = self.log_format

            from hyperi_pylib.logger import setup

            setup()
        except Exception as exc:
            raise LoggerError(str(exc)) from exc

    def load_config(self, env_prefix: str) -> Any:
        """Load configuration via the hyperi-pylib config cascade.

        Uses ``get_config()`` with the app's env prefix and optional
        config file path from ``--config``.

        Args:
            env_prefix: Environment variable prefix (e.g. "DFE_CP").

        Returns:
            Dynaconf settings object.

        Raises:
            ConfigError: If configuration cannot be loaded.
        """
        try:
            os.environ["HYPERI_LIB_ENV_PREFIX"] = env_prefix

            from hyperi_pylib.config import get_config

            additional_files = [self.config] if self.config else None
            return get_config(
                additional_files=additional_files,
                env_prefix=env_prefix,
            )
        except Exception as exc:
            raise ConfigError(str(exc)) from exc


class DfeApp(ABC):
    """Base class for DFE service CLI applications.

    Subclass this to get the standard CLI lifecycle for free. The framework
    provides ``run``, ``version``, and ``config-check`` subcommands, plus
    common flags (``--config``, ``--log-level``, ``--verbose``, ``--quiet``).

    Apps provide the 20%: service name, env prefix, version info, and the
    ``run_service()`` implementation.

    Example::

        class MyService(DfeApp):
            name = "dfe-loader"
            env_prefix = "DFE_LOADER"

            def version_info(self) -> VersionInfo:
                return VersionInfo(self.name, "1.0.0")

            def run_service(self, config) -> None:
                # Sync service logic
                ...

        if __name__ == "__main__":
            MyService().cli()
    """

    name: str
    """Service name (e.g. 'dfe-control-plane')."""

    env_prefix: str
    """Environment variable prefix for config cascade (e.g. 'DFE_CP')."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "name", None) and cls is not DfeApp:
            msg = f"{cls.__name__} must define 'name' class attribute"
            raise TypeError(msg)
        if not getattr(cls, "env_prefix", None) and cls is not DfeApp:
            msg = f"{cls.__name__} must define 'env_prefix' class attribute"
            raise TypeError(msg)

    def __init__(self) -> None:
        self._common_args = CommonArgs()

    @abstractmethod
    def version_info(self) -> VersionInfo:
        """Return version information for this service."""
        ...

    @abstractmethod
    def run_service(self, config: Any) -> None:
        """Run the main service (sync).

        Override this for synchronous services. For async services,
        override ``run_service_async()`` instead.

        Args:
            config: Dynaconf settings object loaded via the config cascade.
        """
        ...

    async def run_service_async(self, config: Any) -> None:
        """Run the main service (async).

        Override this for asynchronous services (FastAPI, httpx, etc.).
        The default implementation delegates to ``run_service()``.

        Args:
            config: Dynaconf settings object loaded via the config cascade.
        """
        self.run_service(config)

    def register_commands(self, app: Any) -> None:  # noqa: B027
        """Register additional app-specific subcommands.

        Override this to add custom subcommands beyond the standard
        ``run``, ``version``, and ``config-check``. Not abstract because
        custom subcommands are optional.

        Args:
            app: The Typer application instance.

        Example::

            def register_commands(self, app):
                @app.command()
                def migrate(target: str = "latest"):
                    '''Run database migrations.'''
                    ...
        """

    def cli(self, args: list[str] | None = None) -> None:
        """Build and run the Typer CLI application.

        This is the main entrypoint. Call from ``if __name__ == "__main__"``.

        Args:
            args: CLI arguments (defaults to sys.argv). Pass explicitly for testing.
        """
        typer_app = _build_typer_app(self)
        typer_app(args, standalone_mode=True)


def run_app(app: DfeApp, args: list[str] | None = None) -> None:
    """Drive the standard DFE service lifecycle.

    Convenience function equivalent to ``app.cli(args)``.

    Args:
        app: DfeApp instance.
        args: CLI arguments (defaults to sys.argv).
    """
    app.cli(args)


def _build_typer_app(dfe_app: DfeApp) -> Any:
    """Construct the Typer app with standard subcommands and callback."""
    from typer import Exit, Option, Typer

    app = Typer(
        name=dfe_app.name,
        help=f"{dfe_app.name} — DFE service",
        add_completion=False,
        no_args_is_help=True,
    )

    # Standard subcommands
    @app.command()
    def run(
        config: str | None = Option(None, "--config", "-c", help="Path to configuration file", envvar="CLI_CONFIG"),
        log_level: str = Option(
            "info", "--log-level", "-l", help="Log level (debug, info, warning, error)", envvar="LOG_LEVEL"
        ),
        log_format: str = Option("auto", "--log-format", help="Log format (json, text, auto)", envvar="LOG_FORMAT"),
        metrics_addr: str = Option(
            "0.0.0.0:9090", "--metrics-addr", help="Metrics server bind address", envvar="METRICS_ADDR"
        ),
        verbose: bool = Option(False, "--verbose", "-v", help="Enable debug logging"),
        quiet: bool = Option(False, "--quiet", "-q", help="Suppress non-error output"),
    ) -> None:
        """Start the service (default)."""
        if verbose and quiet:
            print_error("--verbose and --quiet are mutually exclusive")
            raise Exit(1)

        args = CommonArgs(
            config=config,
            log_level=log_level,
            log_format=log_format,
            metrics_addr=metrics_addr,
            verbose=verbose,
            quiet=quiet,
        )
        dfe_app._common_args = args
        _handle_run(dfe_app, args)

    @app.command()
    def version() -> None:
        """Print version information and exit."""
        info = dfe_app.version_info()
        print(info)

    @app.command(name="config-check")
    def config_check(
        config: str | None = Option(None, "--config", "-c", help="Path to configuration file", envvar="CLI_CONFIG"),
        log_level: str = Option("info", "--log-level", "-l", help="Log level", envvar="LOG_LEVEL"),
        verbose: bool = Option(False, "--verbose", "-v", help="Enable debug logging"),
        quiet: bool = Option(False, "--quiet", "-q", help="Suppress non-error output"),
    ) -> None:
        """Validate configuration and exit."""
        args = CommonArgs(config=config, log_level=log_level, verbose=verbose, quiet=quiet)
        dfe_app._common_args = args
        _handle_config_check(dfe_app, args)

    # Let app register custom subcommands
    dfe_app.register_commands(app)

    return app


def _handle_run(dfe_app: DfeApp, args: CommonArgs) -> None:
    """Handle the 'run' subcommand lifecycle."""
    from typer import Exit

    try:
        args.init_logger()

        from hyperi_pylib.logger import logger

        info = dfe_app.version_info()
        logger.info("starting service", service=dfe_app.name, version=info.version)

        config = args.load_config(dfe_app.env_prefix)
        logger.debug("configuration loaded")

        # Check if run_service_async is overridden (not the default delegation)
        uses_async = _is_async_overridden(dfe_app)

        if uses_async:
            asyncio.run(dfe_app.run_service_async(config))
        else:
            dfe_app.run_service(config)

    except CliError as exc:
        print_error(str(exc))
        raise Exit(1) from exc
    except KeyboardInterrupt:
        print_info("shutting down")
        raise Exit(0) from None
    except Exception as exc:
        print_error(f"fatal: {exc}")
        raise Exit(1) from exc


def _handle_config_check(dfe_app: DfeApp, args: CommonArgs) -> None:
    """Handle the 'config-check' subcommand."""
    from typer import Exit

    try:
        args.init_logger()
        args.load_config(dfe_app.env_prefix)

        print_success("configuration is valid")

        if not args.quiet:
            config_path = args.config or "(defaults)"
            print()
            # Key-value summary to stderr (matching rustlib format)
            _print_kv("service", dfe_app.name)
            _print_kv("config", config_path)
            _print_kv("log_level", args.effective_log_level())
            _print_kv("log_format", args.log_format)
            _print_kv("metrics_addr", args.metrics_addr)

    except CliError as exc:
        print_error(f"configuration invalid: {exc}")
        raise Exit(1) from exc
    except Exception as exc:
        print_error(f"configuration invalid: {exc}")
        raise Exit(1) from exc


def _is_async_overridden(dfe_app: DfeApp) -> bool:
    """Check if run_service_async is overridden from the base DfeApp default."""
    # If the method's defining class is not DfeApp, it's been overridden
    method = type(dfe_app).run_service_async
    return method is not DfeApp.run_service_async


def _print_kv(key: str, value: str) -> None:
    """Print a key-value pair in rustlib format."""
    print(f"  {key:<16} {value}", file=sys.stderr)
