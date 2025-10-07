"""
HyperLib CLI Application
Command-line interface using Click framework
"""

from collections.abc import Callable

from ..logger import logger


class CLIApplication:
    """
    Command-line application using Click.

    Provides:
    - Click integration for CLI commands
    - Subcommand support (groups)
    - Automatic --help generation
    - Option/argument parsing

    Example:
        app = Application.cli(name="my-tool")

        @app.command()
        def sync(source: str, dest: str):
            '''Sync files from source to dest.'''
            click.echo(f"Syncing {source} -> {dest}")

        @app.command()
        @app.option('--verbose', is_flag=True)
        def process(verbose: bool):
            '''Process data with optional verbose output.'''
            if verbose:
                click.echo("Verbose mode enabled")

        app.run()
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        add_verbose: bool = True,
        add_quiet: bool = True,
        add_version: bool = True,
        **kwargs,
    ):
        """
        Initialize CLI application.

        Args:
            name: Application name (used in --help output)
            version: Application version (for --version flag)
            add_verbose: Add global --verbose/-v flag
            add_quiet: Add global --quiet/-q flag
            add_version: Add global --version flag
            **kwargs: Additional Click group options
        """
        self.name = name
        self.version = version

        # Create Click group
        try:
            import sys

            import click

            self.click = click
            self.sys = sys

            # Create context settings for passing state
            ctx_settings = kwargs.pop("context_settings", {})
            ctx_settings["obj"] = ctx_settings.get("obj", {})

            self.group = click.Group(name=name, context_settings=ctx_settings, **kwargs)

            # Add global options if requested
            if add_verbose or add_quiet:
                self._add_logging_options(add_verbose, add_quiet)

            if add_version:
                self._add_version_option()

        except ImportError:
            raise ImportError("Click is required for CLI applications. " "Install it with: pip install click")

        logger.info(f"🖥️  CLIApplication '{name}' initialized")

    def _add_logging_options(self, add_verbose: bool, add_quiet: bool):
        """Add global verbose and quiet logging options."""
        original_callback = self.group.callback

        @self.click.pass_context
        def logging_callback(ctx, verbose=None, quiet=None, **kwargs):
            """Configure logging based on verbose/quiet flags."""
            import sys

            # Store in context
            ctx.ensure_object(dict)
            ctx.obj["verbose"] = verbose
            ctx.obj["quiet"] = quiet

            # Configure logging (safely handle test environments)
            try:
                if quiet:
                    logger.remove()
                    logger.add(sys.stderr, level="ERROR")
                elif verbose:
                    logger.remove()
                    logger.add(sys.stderr, level="DEBUG")
                    logger.debug(f"{self.name} v{self.version} - Verbose mode enabled")
                else:
                    logger.remove()
                    logger.add(sys.stderr, level="INFO")
            except (ValueError, OSError):
                # Logging reconfiguration failed (e.g., in test environment)
                # Continue without logging changes
                pass

            # Call original callback if it exists
            if original_callback:
                original_callback(ctx, **kwargs)

        # Add options to callback
        if add_verbose:
            logging_callback = self.click.option(
                "-v", "--verbose", is_flag=True, help="Enable verbose output"
            )(logging_callback)

        if add_quiet:
            logging_callback = self.click.option(
                "-q", "--quiet", is_flag=True, help="Suppress non-error output"
            )(logging_callback)

        # Set as group callback
        self.group.callback = logging_callback

    def _add_version_option(self):
        """Add --version flag to CLI group."""
        # Click's version_option decorator
        self.group = self.click.version_option(version=self.version, prog_name=self.name)(self.group)

    def command(self, name: str | None = None, **kwargs) -> Callable:
        """
        Decorator to register CLI command.

        Args:
            name: Command name (defaults to function name)
            **kwargs: Click command options

        Example:
            @app.command()
            def sync(source: str, dest: str):
                '''Sync files from source to destination.'''
                click.echo(f"Syncing {source} -> {dest}")
        """
        return self.group.command(name=name, **kwargs)

    def option(self, *param_decls, **kwargs) -> Callable:
        """
        Decorator to add option to command.

        Args:
            param_decls: Option declarations (e.g., '--verbose', '-v')
            **kwargs: Click option parameters

        Example:
            @app.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
            def mycommand(verbose: bool):
                if verbose:
                    click.echo("Verbose mode")
        """
        return self.click.option(*param_decls, **kwargs)

    def argument(self, *param_decls, **kwargs) -> Callable:
        """
        Decorator to add argument to command.

        Args:
            param_decls: Argument declarations
            **kwargs: Click argument parameters

        Example:
            @app.argument('filename')
            def process(filename: str):
                click.echo(f"Processing {filename}")
        """
        return self.click.argument(*param_decls, **kwargs)

    def group_command(self, name: str | None = None, **kwargs) -> Callable:
        """
        Decorator to create command group (for subcommands).

        Args:
            name: Group name
            **kwargs: Click group options

        Example:
            @app.group_command()
            def database():
                '''Database management commands.'''
                pass

            @database.command()
            def migrate():
                '''Run database migrations.'''
                click.echo("Running migrations...")
        """

        def decorator(func: Callable) -> Callable:
            subgroup = self.click.Group(name=name or func.__name__, help=func.__doc__, **kwargs)

            # Add subgroup to main group
            self.group.add_command(subgroup, name=name or func.__name__)

            # Return subgroup so user can add commands to it
            return subgroup

        return decorator

    def add_command(self, func: Callable, name: str | None = None, **kwargs):
        """
        Programmatically add command to CLI.

        Args:
            func: Command function
            name: Command name (defaults to function name)
            **kwargs: Click command options

        Example:
            def my_command():
                click.echo("Hello")

            app.add_command(my_command, name="hello")
        """
        cmd = self.click.command(name=name, **kwargs)(func)
        self.group.add_command(cmd, name=name or func.__name__)

    def run(self, args=None):
        """
        Run the CLI application.

        Args:
            args: Optional argument list (defaults to sys.argv)

        Example:
            if __name__ == "__main__":
                app.run()
        """
        logger.info(f"Running CLI '{self.name}'")
        self.group(args=args)
