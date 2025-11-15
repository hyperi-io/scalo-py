"""
hs-lib CLI utilities - Typer-based command-line interface framework.

This module provides CLI utilities and standards for hs-lib applications.
Typer is the mandatory standard for all CLI applications.

Installation:
    pip install hs-lib[cli]

Basic Usage:
    from hs_lib.cli import Typer, Option, Argument
    from hs_lib.cli.output import print_success, print_table
    from hs_lib.cli.options import VERBOSE_OPTION
    from hs_lib.cli.version import version_option

    app = Typer(help="My application CLI")

    @app.callback()
    def main(version: bool = version_option("myapp")):
        '''My application'''
        pass

    @app.command()
    def deploy(
        environment: str,
        verbose: bool = VERBOSE_OPTION
    ):
        '''Deploy application'''
        print_success(f"Deployed to {environment}")

    if __name__ == "__main__":
        app()

Features:
    - Type-hint driven argument/option parsing
    - Automatic help generation from docstrings
    - Rich terminal output (colors, tables, progress bars)
    - Reusable CLI options (verbose, config, dry-run, etc.)
    - Version handling utilities
    - Beautiful output formatting helpers
    - Excellent IDE support (autocomplete, type checking)
    - Test-friendly (CliRunner for testing)

Standards:
    - Use type hints for all parameters
    - Add help text to all options/arguments
    - Use docstrings for command descriptions
    - Prefer clarity over cleverness (see PYTHON-STANDARDS.md)

Modules:
    - hs_lib.cli.output - Output formatting utilities
    - hs_lib.cli.options - Reusable CLI options
    - hs_lib.cli.version - Version handling
    - hs_lib.cli.examples - Complete usage examples

Examples:
    See hs_lib/cli/examples.py and docs/CLI-STANDARDS.md for complete examples.
"""

__all__ = [
    # Core Typer exports
    "Typer",
    "Option",
    "Argument",
    "Context",
    "Exit",
    "CliRunner",
    "HAS_TYPER",
    # Submodules (import explicitly)
    "output",
    "options",
    "version",
]

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
                "Install with: pip install hs-lib[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

        def __call__(self, *args, **kwargs):
            raise ImportError(
                "Typer is not installed. "
                "Install with: pip install hs-lib[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

    # Replace all exports with error placeholder
    Typer = _TyperNotInstalled
    Option = _TyperNotInstalled
    Argument = _TyperNotInstalled
    Context = _TyperNotInstalled
    Exit = _TyperNotInstalled
    CliRunner = _TyperNotInstalled

# Import submodules (always available, gracefully handle missing Typer)
from . import options, output, version

# Version info
__version__ = "1.0.0"
