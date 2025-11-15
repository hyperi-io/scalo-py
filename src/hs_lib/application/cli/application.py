"""
hs-lib CLI Application
Command-line interface using Typer framework (mandatory standard)
"""

from collections.abc import Callable
from typing import Any

from ...logger import logger
from ..mixins import ProfileMixin, SignalHandlerMixin


class CLIApplication(
    SignalHandlerMixin,
    ProfileMixin,
):
    """
    Command-line application using Typer (mandatory hs-lib standard).

    Provides container-native patterns out of the box:
    - Profile-based configuration (dev/docker/prod)
    - Graceful shutdown (SIGTERM/SIGINT)
    - Typer integration for type-driven CLI commands
    - Automatic help generation from docstrings and type hints
    - Subcommand support
    - Rich terminal output
    - Excellent IDE support

    Example (simple):
        from hs_lib import Application

        app = Application.cli(name="my-tool", version="1.0.0")

        @app.command()
        def sync(source: str, dest: str, verbose: bool = False):
            '''Sync files from source to dest.'''
            print(f"Syncing {source} -> {dest}")
            if verbose:
                print("Verbose mode enabled")

        @app.command()
        def process(
            file: str,
            format: str = "json"
        ):
            '''Process data file.'''
            print(f"Processing {file} as {format}")

        app.run()

    Example (production):
        # Container CMD: python -m my_cli process --file data.json --format json
        # Automatically gets: graceful shutdown, profile-based logging
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        profile: str = "dev",
        add_verbose: bool = True,
        add_quiet: bool = True,
        add_version: bool = True,
        help: str = None,
        profile_overrides: dict[str, Any] | None = None,
        **kwargs,
    ):
        """
        Initialize CLI application.

        Args:
            name: Application name (used in --help output)
            version: Application version (for --version flag)
            profile: Environment profile ("dev", "docker", "prod")
            add_verbose: Add global --verbose/-v flag (deprecated, use command-level options)
            add_quiet: Add global --quiet/-q flag (deprecated, use command-level options)
            add_version: Add global --version flag
            help: Help text for the application
            profile_overrides: Override profile settings
            **kwargs: Additional Typer options
        """
        # Store name and version (consumed here, not passed to mixins)
        self.name = name
        self.version = version

        # Initialize mixins (MRO: Signal -> Profile)
        super().__init__(
            profile=profile,
            profile_overrides=profile_overrides,
        )

        self.add_verbose = add_verbose
        self.add_quiet = add_quiet
        self.add_version = add_version

        # Create Typer app
        try:
            from typer import Typer

            # Create Typer instance
            typer_help = help or f"{name} - hs-lib CLI Application"
            self.app = Typer(
                name=name,
                help=typer_help,
                add_completion=kwargs.pop("add_completion", True),
                **kwargs,
            )

            # Store reference for convenience
            self.typer = self.app

        except ImportError:
            raise ImportError(
                "Typer is required for CLI applications (hs-lib mandatory standard). "
                "Install with: pip install hs-lib[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

        logger.info(f"CLIApplication '{name}' initialized (profile={profile})")

    def command(self, name: str | None = None, **kwargs) -> Callable:
        """
        Decorator to register CLI command.

        Args:
            name: Command name (defaults to function name)
            **kwargs: Typer command options

        Example:
            @app.command()
            def deploy(
                environment: str,
                region: str = "us-east-1",
                verbose: bool = False
            ):
                '''Deploy application to environment.'''
                print(f"Deploying to {environment} in {region}")
        """
        return self.app.command(name=name, **kwargs)

    def callback(self, **kwargs) -> Callable:
        """
        Decorator for main callback (runs before any command).

        Useful for global setup, version handling, etc.

        Example:
            @app.callback()
            def main(
                verbose: bool = False,
                version: bool = False
            ):
                '''My application'''
                if version:
                    print(f"Version: {app.version}")
                    raise typer.Exit()
        """
        return self.app.callback(**kwargs)

    def add_typer(self, typer_instance, *, name: str = None, **kwargs):
        """
        Add a sub-application (for command groups).

        Args:
            typer_instance: Typer instance to add
            name: Group name
            **kwargs: Additional options

        Example:
            # Main app
            app = Application.cli(name="myapp")

            # Sub-app for database commands
            db_app = Typer(help="Database commands")

            @db_app.command()
            def migrate():
                '''Run migrations'''
                print("Running migrations...")

            @db_app.command()
            def backup():
                '''Backup database'''
                print("Backing up...")

            # Add to main app
            app.add_typer(db_app, name="db")

            # Usage: myapp db migrate
        """
        self.app.add_typer(typer_instance, name=name, **kwargs)

    def run(self, args: list[str] | None = None):
        """
        Run the CLI application.

        Args:
            args: Optional argument list (defaults to sys.argv)

        Example:
            if __name__ == "__main__":
                app.run()
        """
        logger.info(f"Running CLI '{self.name}'")

        # Add version callback if requested
        if self.add_version:
            self._add_version_callback()

        # Run the Typer app
        try:
            if args is not None:
                # Use provided args
                self.app(args)
            else:
                # Use sys.argv (Typer default)
                self.app()
        except SystemExit:
            # Let SystemExit pass through (normal for CLI apps)
            raise
        except Exception as e:
            logger.error(f"CLI error: {e}")
            raise

    def _add_version_callback(self):
        """Add --version option to the main callback."""
        from typer import Exit, Option

        # Check if there's already a callback
        if self.app.registered_callback:
            # Callback exists, we can't easily modify it
            # User should add version handling in their callback
            logger.debug("Callback already registered, skipping auto-version")
            return

        # Add a simple version callback
        @self.app.callback(invoke_without_command=True)
        def version_callback(
            version: bool = Option(
                False,
                "--version",
                "-V",
                help="Show version and exit",
                is_flag=True,
            )
        ):
            """Main callback with version support."""
            if version:
                print(f"{self.name} version {self.version}")
                raise Exit()

    # Convenience property to access Typer directly
    @property
    def typer_app(self):
        """Get the underlying Typer instance."""
        return self.app
