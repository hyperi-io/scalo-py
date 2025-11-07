"""
HyperLib CLI utilities - Typer-based command-line interface framework.

This module provides CLI utilities and standards for hyperlib applications.
Typer is the mandatory standard for all CLI applications.

Installation:
    pip install hyperlib[cli]

Basic Usage:
    from hyperlib.cli import Typer, Option, Argument

    app = Typer(help="My application CLI")

    @app.command()
    def hello(name: str = Argument(..., help="Name to greet")):
        '''Say hello'''
        print(f"Hello, {name}!")

    if __name__ == "__main__":
        app()

Features:
    - Type-hint driven argument/option parsing
    - Automatic help generation from docstrings
    - Rich terminal output (colors, tables, progress bars)
    - Excellent IDE support (autocomplete, type checking)
    - Test-friendly (CliRunner for testing)

Standards:
    - Use type hints for all parameters
    - Add help text to all options/arguments
    - Use docstrings for command descriptions
    - Prefer clarity over cleverness (see PYTHON-STANDARDS.md)

Examples:
    See hyperlib/cli/examples/ for complete examples.
"""

__all__ = ["Typer", "Option", "Argument", "Context", "Exit", "CliRunner", "HAS_TYPER"]

# Attempt to import Typer
try:
    from typer import Argument, Context, Exit, Option, Typer
    from typer.testing import CliRunner

    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False

    # Provide helpful error message if Typer not installed
    class _TyperNotInstalled:
        """Placeholder for when Typer is not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Typer is not installed. "
                "Install with: pip install hyperlib[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

        def __call__(self, *args, **kwargs):
            raise ImportError(
                "Typer is not installed. "
                "Install with: pip install hyperlib[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

    # Replace all exports with error placeholder
    Typer = _TyperNotInstalled
    Option = _TyperNotInstalled
    Argument = _TyperNotInstalled
    Context = _TyperNotInstalled
    Exit = _TyperNotInstalled
    CliRunner = _TyperNotInstalled


# Version info
__version__ = "1.0.0"
