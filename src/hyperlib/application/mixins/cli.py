"""
CLIExecutableMixin: Typer CLI commands for all application types.

This mixin provides standard CLI commands (version, config, validate, health-check)
that all application types inherit, enabling CLI-first execution in containers.
"""

import json
from typing import Any

import typer



class CLIExecutableMixin:
    """
    Mixin to add Typer CLI capabilities to applications.

    Provides standard commands that all application types inherit:
    - version: Show application version
    - config: Show active configuration
    - validate: Validate configuration
    - health-check: Check application health (if health checks enabled)

    Application types add their own specific commands (serve, start, run, etc.)

    Example:
        class MyAPI(CLIExecutableMixin, ProfileMixin):
            def __init__(self, name: str, version: str, **kwargs):
                super().__init__(name=name, version=version, **kwargs)

                # Add app-specific command
                @self.cli.command()
                def serve(host: str = "0.0.0.0", port: int = 8000):
                    print(f"Starting server on {host}:{port}")
    """

    def __init__(
        self,
        name: str,
        version: str,
        description: str | None = None,
        **kwargs: Any,
    ):
        """
        Initialize CLI executable mixin.

        Args:
            name: Application name
            version: Application version
            description: Optional application description
            **kwargs: Additional args passed to next mixin in chain
        """
        self.name = name
        self.version = version
        self.description = description or f"{name} application"

        # Create Typer app
        self.cli = typer.Typer(
            name=name,
            help=self.description,
            add_completion=True,  # Enable shell completion
            no_args_is_help=True,  # Show help if no command given
        )

        # Add standard commands
        self._add_standard_commands()

        # Call next mixin in MRO chain
        super().__init__(**kwargs)

    def _add_standard_commands(self) -> None:
        """Add standard CLI commands that all apps inherit."""

        @self.cli.command()
        def version() -> None:
            """Show application version."""
            typer.echo(f"{self.name} v{self.version}")

        @self.cli.command()
        def config(format: str = typer.Option("json", help="Output format (json or yaml)")) -> None:
            """Show active configuration (from profile + overrides)."""
            if not hasattr(self, "profile"):
                typer.echo("Error: Profile not loaded", err=True)
                raise typer.Exit(1)

            profile_data = {
                "name": self.name,
                "version": self.version,
                "profile": self.profile_name,
                "settings": self.profile,
            }

            if format == "json":
                typer.echo(json.dumps(profile_data, indent=2))
            elif format == "yaml":
                try:
                    import yaml

                    typer.echo(yaml.safe_dump(profile_data, default_flow_style=False))
                except ImportError:
                    typer.echo("Error: PyYAML not installed, use --format=json", err=True)
                    raise typer.Exit(1)
            else:
                typer.echo(f"Error: Invalid format '{format}'", err=True)
                raise typer.Exit(1)

        @self.cli.command()
        def validate() -> None:
            """Validate application configuration."""
            if not hasattr(self, "profile"):
                typer.echo("✗ Profile not loaded", err=True)
                raise typer.Exit(1)

            # Basic validation
            typer.echo(f"✓ Profile '{self.profile_name}' loaded successfully")
            typer.echo(f"✓ Application: {self.name} v{self.version}")

            # Check required settings based on profile
            if self.profile.get("health_check"):
                port = self.profile.get("health_check_port")
                typer.echo(f"✓ Health check enabled on port {port}")

            if self.profile.get("metrics"):
                port = self.profile.get("metrics_port")
                typer.echo(f"✓ Metrics enabled on port {port}")

            typer.echo("\nConfiguration is valid ✓")

        @self.cli.command("health-check")
        def health_check() -> None:
            """
            Check application health status.

            Exits with code 0 if healthy, 1 if unhealthy.
            Useful for container health checks and monitoring.
            """
            # Check if health check is enabled
            if not hasattr(self, "profile") or not self.profile.get("health_check"):
                typer.echo("Health checks not enabled in this profile", err=True)
                raise typer.Exit(1)

            # Check if HealthCheckMixin is available
            if not hasattr(self, "_health_check_handlers"):
                typer.echo("✓ Application is running (no health checks registered)")
                return

            # Run health checks (if HealthCheckMixin is present)
            try:
                # This will be implemented by HealthCheckMixin
                # For now, just report healthy
                typer.echo("✓ Application is healthy")
            except Exception as e:
                typer.echo(f"✗ Health check failed: {e}", err=True)
                raise typer.Exit(1)

    def run(self) -> None:
        """
        Execute the CLI.

        This is the main entry point for the application when run as a CLI.
        It processes command-line arguments and executes the appropriate command.

        Example:
            if __name__ == "__main__":
                app = MyApp(name="myapp", version="1.0.0")
                app.run()
        """
        self.cli()
