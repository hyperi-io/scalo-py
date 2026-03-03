"""
hyperi-pylib CLI framework — Typer-based command-line interface for DFE services.

Two levels of usage:

**DfeApp framework** (recommended for DFE services)::

    from hyperi_pylib.cli import DfeApp, VersionInfo

    class MyService(DfeApp):
        name = "dfe-loader"
        env_prefix = "DFE_LOADER"

        def version_info(self) -> VersionInfo:
            return VersionInfo(self.name, "1.0.0")

        def run_service(self, config) -> None:
            ...

    if __name__ == "__main__":
        MyService().cli()

**Standalone Typer utilities** (for custom CLIs)::

    from hyperi_pylib.cli import Typer, Option
    from hyperi_pylib.cli.output import print_success
    from hyperi_pylib.cli.options import VERBOSE_OPTION

Modules:
    - hyperi_pylib.cli.app - DfeApp framework (DfeApp, CommonArgs, run_app)
    - hyperi_pylib.cli.error - CLI error types
    - hyperi_pylib.cli.version_info - Structured version metadata
    - hyperi_pylib.cli.output - Output formatting utilities
    - hyperi_pylib.cli.options - Reusable CLI options
    - hyperi_pylib.cli.version - Version handling (legacy, use version_info for new code)
"""

__all__ = [
    # DfeApp framework
    "CommonArgs",
    "CliError",
    "ConfigError",
    "DfeApp",
    "InvalidArgumentError",
    "LoggerError",
    "ServiceError",
    "VersionInfo",
    "run_app",
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
                "Install with: pip install hyperi-pylib[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

        def __call__(self, *args, **kwargs):
            raise ImportError(
                "Typer is not installed. "
                "Install with: pip install hyperi-pylib[cli]\n"
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

# DfeApp framework (always available — errors are clear if Typer missing)
from .app import CommonArgs, DfeApp, run_app
from .error import CliError, ConfigError, InvalidArgumentError, LoggerError, ServiceError
from .version_info import VersionInfo
