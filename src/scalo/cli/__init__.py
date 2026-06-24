"""
scalo CLI framework -- Typer-based command-line interface for services.

Two levels of usage:

**ServiceApp framework** (recommended; ``DfeApp`` is a deprecated alias)::

    from scalo.cli import ServiceApp, VersionInfo

    class MyService(ServiceApp):
        name = "my-service"
        env_prefix = "MYAPP"

        def version_info(self) -> VersionInfo:
            return VersionInfo(self.name, "1.0.0")

        def run_service(self, config) -> None:
            ...

    if __name__ == "__main__":
        MyService().cli()

**Standalone Typer utilities** (for custom CLIs)::

    from scalo.cli import Typer, Option
    from scalo.cli.output import print_success
    from scalo.cli.options import VERBOSE_OPTION

Modules:
    - scalo.cli.app - ServiceApp framework (ServiceApp, CommonArgs, run_app; DfeApp deprecated alias)
    - scalo.cli.error - CLI error types
    - scalo.cli.version_info - Structured version metadata
    - scalo.cli.output - Output formatting utilities
    - scalo.cli.options - Reusable CLI options
    - scalo.cli.version - Version handling (legacy, use version_info for new code)
"""

__all__ = [
    "HAS_TYPER",
    "Argument",
    "CliError",
    "CliRunner",
    # ServiceApp framework
    "CommonArgs",
    "ConfigError",
    "Context",
    "DfeApp",
    "Exit",
    "InvalidArgumentError",
    "LoggerError",
    "Option",
    "ServiceApp",
    "ServiceError",
    # Core Typer exports
    "Typer",
    "VersionInfo",
    "options",
    # Submodules (import explicitly)
    "output",
    "run_app",
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
                "Install with: pip install scalo[cli]\n"
                "Documentation: https://typer.tiangolo.com/"
            )

        def __call__(self, *args, **kwargs):
            raise ImportError(
                "Typer is not installed. "
                "Install with: pip install scalo[cli]\n"
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

# ServiceApp framework (always available -- errors are clear if Typer missing)
from .app import CommonArgs, DfeApp, ServiceApp, run_app
from .error import CliError, ConfigError, InvalidArgumentError, LoggerError, ServiceError
from .version_info import VersionInfo
