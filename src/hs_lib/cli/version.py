"""
Version handling utilities for CLI applications.

Provides automatic version detection and display for Typer CLI apps.
Reads version from package metadata, avoiding hardcoded version strings.

Basic Usage:
    from hs_lib.cli import Typer
    from hs_lib.cli.version import version_option

    app = Typer()

    # Add --version option to main app
    @app.callback()
    def main(version: bool = version_option("mypackage")):
        pass

    # Or use as standalone
    @app.command()
    def info():
        from hs_lib.cli.version import get_version
        print(f"Version: {get_version('mypackage')}")

Features:
    - Auto-detects version from package metadata
    - Standard --version/-V flags
    - Graceful fallback when version not found
    - Works with all Python packaging standards
"""

import sys
from importlib.metadata import PackageNotFoundError, version

try:
    from typer import Exit, Option

    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False
    Option = None
    Exit = None

__all__ = [
    "get_version",
    "version_option",
    "print_version",
]


def get_version(package_name: str, fallback: str = "unknown") -> str:
    """
    Get package version from metadata.

    Args:
        package_name: Name of the package (e.g., "hyperlib", "myapp")
        fallback: Fallback version if not found

    Returns:
        Version string (e.g., "1.2.3") or fallback

    Example:
        version = get_version("hyperlib")
        print(f"HyperLib version: {version}")
    """
    try:
        return version(package_name)
    except PackageNotFoundError:
        return fallback


def print_version(package_name: str, app_name: str | None = None, python_version: bool = False):
    """
    Print version information and exit.

    Args:
        package_name: Name of the package
        app_name: Display name (defaults to package_name)
        python_version: Include Python version in output

    Example:
        print_version("hyperlib", app_name="HyperLib CLI")
        # Output: HyperLib CLI version 2.7.3
    """
    if app_name is None:
        app_name = package_name

    ver = get_version(package_name)
    print(f"{app_name} version {ver}")

    if python_version:
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"Python {py_ver}")

    if HAS_TYPER:
        raise Exit(0)
    else:
        sys.exit(0)


def version_option(
    package_name: str,
    app_name: str | None = None,
    python_version: bool = False,
    param_decls: tuple[str, ...] = ("--version", "-V"),
):
    """
    Create a --version option for Typer CLI.

    This creates a Typer Option that displays version and exits.
    Use in the main app callback function.

    Args:
        package_name: Name of the package to get version from
        app_name: Display name (defaults to package_name)
        python_version: Include Python version in output
        param_decls: Option flags (default: --version, -V)

    Returns:
        Typer Option configured for version display

    Example:
        from hs_lib.cli import Typer
        from hs_lib.cli.version import version_option

        app = Typer()

        @app.callback()
        def main(
            version: bool = version_option("myapp", app_name="My Application")
        ):
            '''My Application CLI'''
            pass

        # Usage: myapp --version
        # Output: My Application version 1.2.3
    """
    if not HAS_TYPER:
        raise ImportError("Typer not installed. Install with: pip install hyperlib[cli]")

    def version_callback(value: bool):
        if value:
            print_version(package_name, app_name, python_version)

    return Option(
        None,
        *param_decls,
        callback=version_callback,
        is_eager=True,
        help=f"Show {app_name or package_name} version and exit",
    )


# Pre-configured version option for hyperlib itself
HYPERLIB_VERSION_OPTION = version_option("hyperlib", app_name="HyperLib", python_version=True) if HAS_TYPER else None
