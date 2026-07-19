# Project:   scalo
# File:      cli/app.py
# Purpose:   ServiceApp application framework and lifecycle runner
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""service application framework.

Provides the standard CLI lifecycle for Python services, mirroring
hyperi-rustlib's cli::app module. Apps subclass ``ServiceApp`` and get standard
subcommands (``run``, ``version``, ``config-check``) and common flags
(``--config``, ``--log-level``, ``--verbose``, ``--quiet``) for free.

**No ``top`` subcommand** -- Python services are never on the hot path;
performance-critical data plane work is handled by Rust services. A TUI
metrics dashboard adds no value for Python control-plane services.

Example::

    from scalo.cli import ServiceApp, VersionInfo

    class MyService(ServiceApp):
        name = "control-plane"
        env_prefix = "MYAPP"

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
    "ServiceApp",
    "run_app",
]


@dataclass
class CommonArgs:
    """Standard CLI arguments for services.

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
        """Initialise the scalo logger with resolved settings.

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

            from scalo.logger import setup

            setup()
        except Exception as exc:
            raise LoggerError(str(exc)) from exc

    def load_config(self, env_prefix: str) -> Any:
        """Load configuration via the scalo config cascade.

        Uses ``get_config()`` with the app's env prefix and optional
        config file path from ``--config``.

        Args:
            env_prefix: Environment variable prefix (e.g. "MYAPP").

        Returns:
            Dynaconf settings object.

        Raises:
            ConfigError: If configuration cannot be loaded.
        """
        try:
            from scalo._env_compat import set_env_prefix

            set_env_prefix(env_prefix)

            from scalo.config import get_config

            additional_files = [self.config] if self.config else None
            return get_config(
                additional_files=additional_files,
                env_prefix=env_prefix,
            )
        except Exception as exc:
            raise ConfigError(str(exc)) from exc


class ServiceApp(ABC):
    """Base class for service CLI applications.

    Subclass this to get the standard CLI lifecycle for free. The framework
    provides ``run``, ``version``, and ``config-check`` subcommands, plus
    common flags (``--config``, ``--log-level``, ``--verbose``, ``--quiet``).

    Apps provide the 20%: service name, env prefix, version info, and the
    ``run_service()`` implementation.

    Example::

        class MyService(ServiceApp):
            name = "my-loader"
            env_prefix = "MYAPP"

            def version_info(self) -> VersionInfo:
                return VersionInfo(self.name, "1.0.0")

            def run_service(self, config) -> None:
                # Sync service logic
                ...

        if __name__ == "__main__":
            MyService().cli()
    """

    name: str
    """Service name (e.g. 'control-plane')."""

    env_prefix: str
    """Environment variable prefix for config cascade (e.g. 'MYAPP')."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "name", None) and cls is not ServiceApp:
            msg = f"{cls.__name__} must define 'name' class attribute"
            raise TypeError(msg)
        if not getattr(cls, "env_prefix", None) and cls is not ServiceApp:
            msg = f"{cls.__name__} must define 'env_prefix' class attribute"
            raise TypeError(msg)

    serve_observability: bool = True
    """Serve health probes + metrics on ``--metrics-addr`` during ``run``.

    Set False only for a service that genuinely has no business binding an
    observability port (a one-shot CLI, say). Leaving it on is what makes
    the advertised address real.
    """

    def __init__(self) -> None:
        self._common_args = CommonArgs()
        self._metrics: Any = None
        """MetricsManager instance, set automatically by _handle_run() if metrics extra is installed."""
        self._app_metrics: Any = None
        """AppMetrics instance, set automatically by _handle_run() if metrics extra is installed."""
        self._health: Any = None
        """HealthManager backing the observability port. Use health() to reach it."""
        self._observability: Any = None
        """ObservabilityServer bound to --metrics-addr, set by _handle_run()."""

    def health(self) -> Any:
        """The ``HealthManager`` served on the observability port.

        Created on first use so it is available to ``run_service`` /
        ``run_service_async`` overrides. Register checks and flip readiness
        on THIS instance -- a separate manager would leave ``/readyz``
        reporting something the service does not mean::

            def run_service(self, config):
                self.health().register_ready_check("db", db.is_connected)
                self.health().set_ready()
        """
        if self._health is None:
            from scalo.health import HealthManager

            self._health = HealthManager()
        return self._health

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

    def deployment_contract(self) -> Any:
        """Return the app's ``DeploymentContract`` for ``generate-artefacts``.

        Override to return a ``scalo.deployment.DeploymentContract``
        instance; ``generate-artefacts`` will then emit Dockerfile,
        container-manifest.json, argocd-application.yaml, etc. into the
        output directory.

        Default returns ``None`` -- the subcommand then prints a warning and
        emits nothing. Apps that don't ship as containers can leave it as
        None.

        Mirrors rustlib's ``ServiceApp::deployment_contract()`` trait hook.
        """
        return None

    def cli(self, args: list[str] | None = None) -> None:
        """Build and run the Typer CLI application.

        This is the main entrypoint. Call from ``if __name__ == "__main__"``.

        Args:
            args: CLI arguments (defaults to sys.argv). Pass explicitly for testing.
        """
        typer_app = _build_typer_app(self)
        typer_app(args, standalone_mode=True)


def run_app(app: ServiceApp, args: list[str] | None = None) -> None:
    """Drive the standard service lifecycle.

    Convenience function equivalent to ``app.cli(args)``.

    Args:
        app: ServiceApp instance.
        args: CLI arguments (defaults to sys.argv).
    """
    app.cli(args)


def _build_typer_app(service_app: ServiceApp) -> Any:
    """Construct the Typer app with standard subcommands and callback."""
    from typer import Exit, Option, Typer

    app = Typer(
        name=service_app.name,
        help=f"{service_app.name} -- service",
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
        service_app._common_args = args
        _handle_run(service_app, args)

    @app.command()
    def version() -> None:
        """Print version information and exit."""
        info = service_app.version_info()
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
        service_app._common_args = args
        _handle_config_check(service_app, args)

    @app.command(name="generate-artefacts")
    def generate_artefacts(
        output_dir: str = Option("ci", "--output-dir", "-o", help="Output directory for generated artefacts"),
    ) -> None:
        """Generate deployment artefacts (contract JSON, container manifest, runtime Dockerfile, ArgoCD app) from contract."""
        _handle_generate_artefacts(service_app, output_dir)

    # Let app register custom subcommands
    service_app.register_commands(app)

    return app


def _handle_run(service_app: ServiceApp, args: CommonArgs) -> None:
    """Handle the 'run' subcommand lifecycle."""
    from typer import Exit

    try:
        args.init_logger()

        from scalo.logger import logger

        info = service_app.version_info()
        logger.info("starting service", service=service_app.name, version=info.version)

        config = args.load_config(service_app.env_prefix)
        logger.debug("configuration loaded")

        # Auto-init metrics if available (metrics extra installed)
        try:
            from scalo.metrics import create_metrics
            from scalo.metrics.groups import AppMetrics

            ns = service_app.name.replace("-", "_")
            # Honour the documented backend knob. It used to be hardcoded to
            # "prometheus" here, which silently beat both METRICS_BACKEND and
            # settings.metrics.backend -- an explicit argument wins the
            # cascade, so the knob did nothing on the ServiceApp path.
            # The fallback stays "prometheus" rather than create_metrics'
            # own "opentelemetry" default, so honouring the knob does not
            # also change the backend for every existing service.
            from scalo._env_compat import control_var

            backend = control_var("METRICS_BACKEND")
            if backend is None:
                try:
                    backend = config.get("metrics", {}).get("backend")
                except Exception:
                    backend = None
            metrics_manager = create_metrics(ns, backend=backend or "prometheus")
            app_metrics = AppMetrics(metrics_manager, info.version, info.commit or "unknown")
            service_app._metrics = metrics_manager
            service_app._app_metrics = app_metrics
            logger.debug("metrics auto-initialised", namespace=ns)
        except ImportError:
            service_app._metrics = None
            service_app._app_metrics = None
            logger.debug("metrics not available (install scalo[metrics])")
        except Exception as e:
            service_app._metrics = None
            service_app._app_metrics = None
            logger.warning("metrics initialisation failed", error=str(e))

        # Bind the observability port BEFORE the service starts, so a probe
        # arriving during startup gets an honest 503 rather than a refused
        # connection. A bind failure is fatal by design: the alternative is
        # a service that reports healthy on a port nobody is listening to.
        if service_app.serve_observability:
            from scalo.health import serve_observability as _serve_observability

            service_app._observability = _serve_observability(
                health=service_app.health(),
                metrics=service_app._metrics,
                addr=args.metrics_addr,
            )
            bound = service_app._observability.bound_address
            logger.info(
                "observability listening",
                addr=f"{bound[0]}:{bound[1]}" if bound else args.metrics_addr,
                paths="/metrics /healthz /readyz",
            )

        service_app.health().set_started()

        # Check if run_service_async is overridden (not the default delegation)
        uses_async = _is_async_overridden(service_app)

        if uses_async:
            asyncio.run(service_app.run_service_async(config))
        else:
            service_app.run_service(config)

    except CliError as exc:
        print_error(str(exc))
        raise Exit(1) from exc
    except KeyboardInterrupt:
        print_info("shutting down")
        raise Exit(0) from None
    except Exception as exc:
        print_error(f"fatal: {exc}")
        raise Exit(1) from exc
    finally:
        # Release the port on every exit path, or a restart in the same
        # process (tests, supervisors) hits "address already in use".
        if service_app._observability is not None:
            service_app._observability.stop()
            service_app._observability = None


def _handle_config_check(service_app: ServiceApp, args: CommonArgs) -> None:
    """Handle the 'config-check' subcommand."""
    from typer import Exit

    try:
        args.init_logger()
        args.load_config(service_app.env_prefix)

        print_success("configuration is valid")

        if not args.quiet:
            config_path = args.config or "(defaults)"
            print()
            # Key-value summary to stderr (matching rustlib format)
            _print_kv("service", service_app.name)
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


def _handle_generate_artefacts(service_app: ServiceApp, output_dir: str) -> None:
    """Handle the 'generate-artefacts' subcommand.

    Mirrors rustlib's ``generate_artefacts`` CLI command: writes
    ``deployment-contract.json``, ``container-manifest.json``,
    ``Dockerfile.runtime``, and ``argocd-application.yaml`` into ``output_dir``
    based on the app's ``deployment_contract()`` return value.
    """
    from pathlib import Path

    from typer import Exit

    contract = service_app.deployment_contract()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if contract is None:
        print_error(
            f"[warn] {type(service_app).__name__}.deployment_contract() returned None for "
            f"`{service_app.name}` -- no deployment artefacts emitted. Override the method "
            f"to emit deployment-contract.json, container-manifest.json, "
            f"Dockerfile.runtime, and argocd-application.yaml."
        )
        return

    try:
        from scalo.deployment import (
            ArgocdConfig,
            argocd_repo_url_from_cascade,
            generate_argocd_application,
            generate_container_manifest,
            generate_dockerignore,
            generate_runtime_stage,
        )
    except Exception as exc:
        print_error("deployment subsystem unavailable -- install with: pip install 'scalo[deployment]'")
        raise Exit(1) from exc

    (out / "deployment-contract.json").write_text(contract.to_json(), encoding="utf-8", newline="\n")
    (out / "container-manifest.json").write_text(generate_container_manifest(contract), encoding="utf-8", newline="\n")
    (out / "Dockerfile.runtime").write_text(generate_runtime_stage(contract), encoding="utf-8", newline="\n")
    (out / ".dockerignore").write_text(generate_dockerignore(contract), encoding="utf-8", newline="\n")

    argo = ArgocdConfig(repo_url=argocd_repo_url_from_cascade(contract.app_name))
    (out / "argocd-application.yaml").write_text(
        generate_argocd_application(contract, argo), encoding="utf-8", newline="\n"
    )

    print_success(f"deployment artefacts written to {out}/")
    if not service_app._common_args.quiet:
        for filename in (
            "deployment-contract.json",
            "container-manifest.json",
            "Dockerfile.runtime",
            ".dockerignore",
            "argocd-application.yaml",
        ):
            print(f"  {filename}", file=sys.stderr)


def _is_async_overridden(service_app: ServiceApp) -> bool:
    """Check if run_service_async is overridden from the base ServiceApp default."""
    # If the method's defining class is not ServiceApp, it's been overridden
    method = type(service_app).run_service_async
    return method is not ServiceApp.run_service_async


def _print_kv(key: str, value: str) -> None:
    """Print a key-value pair in rustlib format."""
    print(f"  {key:<16} {value}", file=sys.stderr)


# Deprecated alias -- prefer ServiceApp. Kept so existing
# `class X(DfeApp)` services import unchanged during migration.
DfeApp = ServiceApp
