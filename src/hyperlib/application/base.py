"""
HyperLib Application Factory
Main entry point for creating applications
"""

from pathlib import Path
from typing import Any, Callable

from ..container import MountConfig


class Application:
    """
    Application factory for all deployment types.

    Usage:
        # API service
        app = Application.api(name="my-service", port=8000)

        # Daemon worker
        app = Application.daemon(name="my-worker")

        # CLI tool
        app = Application.cli(name="my-tool")

        # One-shot task
        app = Application.oneshot(name="my-task")
    """

    @staticmethod
    def api(
        name: str,
        port: int = 8000,
        metrics_port: int = 8080,
        mounts: MountConfig | None = None,
        **kwargs,
    ) -> "APIApplication":
        """
        Create REST API service application.

        Args:
            name: Application name
            port: API server port (default: 8000)
            metrics_port: Prometheus metrics port (default: 8080)
            mounts: Container mount configuration
            **kwargs: Additional ContainerConfig options

        Returns:
            APIApplication instance

        Example:
            app = Application.api(name="my-service", port=8000)

            @app.route("/")
            def root():
                return {"message": "Hello"}

            app.run()
        """
        from .api import APIApplication

        if mounts is None:
            mounts = MountConfig(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
            )

        return APIApplication(name=name, port=port, metrics_port=metrics_port, mounts=mounts, **kwargs)

    @staticmethod
    def daemon(
        name: str,
        business_logic: Any | None = None,
        mounts: MountConfig | None = None,
        **kwargs,
    ) -> "DaemonApplication":
        """
        Create long-running daemon application.

        Args:
            name: Application name
            business_logic: Optional business logic object with run_daemon() method
            mounts: Container mount configuration
            **kwargs: Additional ContainerConfig options

        Returns:
            DaemonApplication instance

        Example:
            app = Application.daemon(name="my-worker")

            @app.scheduled(interval=60)
            async def process_queue():
                # Background task every 60 seconds
                pass

            app.run()
        """
        from .daemon import DaemonApplication

        if mounts is None:
            mounts = MountConfig(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
            )

        return DaemonApplication(name=name, business_logic=business_logic, mounts=mounts, **kwargs)

    @staticmethod
    def cli(name: str, **kwargs) -> "CLIApplication":
        """
        Create command-line application.

        Args:
            name: Application name
            **kwargs: Additional configuration options

        Returns:
            CLIApplication instance

        Example:
            app = Application.cli(name="my-tool")

            @app.command()
            def sync(source: str, dest: str):
                '''Sync files from source to dest.'''
                click.echo(f"Syncing {source} -> {dest}")

            app.run()
        """
        from .cli import CLIApplication

        return CLIApplication(name=name, **kwargs)

    @staticmethod
    def oneshot(
        name: str,
        task_func: Callable | None = None,
        mounts: MountConfig | None = None,
        **kwargs,
    ) -> "OneshotApplication":
        """
        Create one-shot task application.

        Args:
            name: Application name
            task_func: Optional task function to execute
            mounts: Container mount configuration
            **kwargs: Additional ContainerConfig options

        Returns:
            OneshotApplication instance

        Example:
            app = Application.oneshot(name="my-task")

            @app.task
            def process_data():
                # One-time processing
                return "result"

            result = app.run()
        """
        from .oneshot import OneshotApplication

        if mounts is None:
            mounts = MountConfig(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
            )

        return OneshotApplication(name=name, task_func=task_func, mounts=mounts, **kwargs)
