"""
HyperLib CLI Application
Command-line interface using Click framework
"""

from typing import Callable

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

    def __init__(self, name: str, **kwargs):
        """
        Initialize CLI application.

        Args:
            name: Application name (used in --help output)
            **kwargs: Additional Click group options
        """
        self.name = name

        # Create Click group
        try:
            import click

            self.click = click
            self.group = click.Group(name=name, **kwargs)

        except ImportError:
            raise ImportError("Click is required for CLI applications. " "Install it with: pip install click")

        logger.info(f"🖥️  CLIApplication '{name}' initialized")

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
