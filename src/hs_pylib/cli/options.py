"""
Reusable CLI options and arguments for Typer applications.

Provides pre-configured, commonly used options to ensure consistency
across CLI applications and reduce boilerplate code.

Basic Usage:
    from hs_pylib.cli import Typer
    from hs_pylib.cli.options import VERBOSE_OPTION, CONFIG_OPTION

    app = Typer()

    @app.command()
    def deploy(
        verbose: bool = VERBOSE_OPTION,
        config: str = CONFIG_OPTION,
    ):
        if verbose:
            print("Verbose mode enabled")

Features:
    - Standard option definitions (verbose, quiet, config, etc.)
    - Consistent help text and flags across apps
    - Validated option types
    - Environment variable integration
"""

from pathlib import Path

try:
    from typer import Option

    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False
    # Fallback - will error if used without Typer installed
    Option = None

__all__ = [
    "VERBOSE_OPTION",
    "QUIET_OPTION",
    "DEBUG_OPTION",
    "CONFIG_OPTION",
    "ENV_OPTION",
    "DRY_RUN_OPTION",
    "FORCE_OPTION",
    "YES_OPTION",
    "OUTPUT_OPTION",
    "LOG_LEVEL_OPTION",
    "LOG_FILE_OPTION",
]

# Standard CLI Options
# These are pre-configured Option() calls that can be used in Typer commands

if HAS_TYPER:
    # Logging and verbosity
    VERBOSE_OPTION = Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output with detailed information",
        envvar="CLI_VERBOSE",
    )

    QUIET_OPTION = Option(
        False,
        "--quiet",
        "-q",
        help="Suppress all non-error output",
        envvar="CLI_QUIET",
    )

    DEBUG_OPTION = Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode with maximum verbosity",
        envvar="CLI_DEBUG",
    )

    LOG_LEVEL_OPTION = Option(
        "INFO",
        "--log-level",
        "-l",
        help="Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        envvar="LOG_LEVEL",
    )

    LOG_FILE_OPTION = Option(
        None,
        "--log-file",
        help="Write logs to file",
        envvar="LOG_FILE",
    )

    # Configuration
    CONFIG_OPTION = Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file (YAML or JSON)",
        envvar="CLI_CONFIG",
    )

    ENV_OPTION = Option(
        "dev",
        "--env",
        "-e",
        help="Environment: dev, staging, prod",
        envvar="ENVIRONMENT",
    )

    # Execution control
    DRY_RUN_OPTION = Option(
        False,
        "--dry-run",
        help="Preview actions without making changes",
        envvar="CLI_DRY_RUN",
    )

    FORCE_OPTION = Option(
        False,
        "--force",
        "-f",
        help="Force operation without confirmation prompts",
        envvar="CLI_FORCE",
    )

    YES_OPTION = Option(
        False,
        "--yes",
        "-y",
        help="Automatically answer yes to all prompts",
        envvar="CLI_YES",
    )

    # Output formatting
    OUTPUT_OPTION = Option(
        "table",
        "--output",
        "-o",
        help="Output format: table, json, yaml, csv",
        envvar="CLI_OUTPUT_FORMAT",
    )

else:
    # Placeholders when Typer not installed
    VERBOSE_OPTION = None
    QUIET_OPTION = None
    DEBUG_OPTION = None
    LOG_LEVEL_OPTION = None
    LOG_FILE_OPTION = None
    CONFIG_OPTION = None
    ENV_OPTION = None
    DRY_RUN_OPTION = None
    FORCE_OPTION = None
    YES_OPTION = None
    OUTPUT_OPTION = None


# Helper function for custom Path options
def path_option(
    default: Path | None = None,
    *param_decls: str,
    help: str = "Path to file or directory",
    exists: bool = False,
    file_okay: bool = True,
    dir_okay: bool = True,
    **kwargs,
) -> Path | None:
    """
    Create a Path-typed option with validation.

    Args:
        default: Default path value
        *param_decls: Option flags (e.g., "--input", "-i")
        help: Help text
        exists: Require path to exist
        file_okay: Allow files
        dir_okay: Allow directories
        **kwargs: Additional Option arguments

    Returns:
        Configured Option for Path type

    Example:
        INPUT_FILE = path_option(
            None, "--input", "-i",
            help="Input file path",
            exists=True,
            dir_okay=False
        )
    """
    if not HAS_TYPER:
        raise ImportError("Typer not installed. Install with: pip install hs-pylib[cli]")

    return Option(
        default,
        *param_decls,
        help=help,
        exists=exists,
        file_okay=file_okay,
        dir_okay=dir_okay,
        **kwargs,
    )


# Helper function for custom Enum options
def enum_option(  # noqa: ARG001
    enum_class,
    default,
    *param_decls: str,
    help: str = "Select option",
    case_sensitive: bool = False,
    **kwargs,
):
    """
    Create an Enum-typed option with validation.

    Args:
        enum_class: Enum class to use
        default: Default enum value
        *param_decls: Option flags
        help: Help text
        case_sensitive: Case-sensitive enum matching
        **kwargs: Additional Option arguments

    Returns:
        Configured Option for Enum type

    Example:
        from enum import Enum

        class Environment(str, Enum):
            DEV = "dev"
            STAGING = "staging"
            PROD = "prod"

        ENV = enum_option(
            Environment, Environment.DEV,
            "--env", "-e",
            help="Deployment environment"
        )
    """
    if not HAS_TYPER:
        raise ImportError("Typer not installed. Install with: pip install hs-pylib[cli]")

    return Option(
        default,
        *param_decls,
        help=help,
        case_sensitive=case_sensitive,
        **kwargs,
    )
