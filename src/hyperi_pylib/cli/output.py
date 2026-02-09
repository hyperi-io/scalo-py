"""
CLI output formatting utilities using Rich.

Provides common output patterns for CLI applications with beautiful formatting,
colors, and tables. All functions gracefully degrade if Rich is not available.

Basic Usage:
    from hyperi_pylib.cli.output import print_success, print_error, print_table

    print_success("Operation completed!")
    print_error("Something went wrong")

    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
    ]
    print_table(data, title="Users")

Features:
    - Automatic Rich detection (graceful fallback to plain text)
    - Consistent color scheme across CLI apps
    - Table auto-formatting from dicts or lists
    - JSON syntax highlighting
    - Progress bars and spinners
"""

import json
import sys
from typing import Any

__all__ = [
    "console",
    "stderr_console",
    "print_success",
    "print_error",
    "print_warning",
    "print_info",
    "print_table",
    "print_json",
    "print_dict",
    "HAS_RICH",
]

# Try to import Rich
try:
    from rich.console import Console
    from rich.json import JSON
    from rich.panel import Panel  # noqa: F401
    from rich.table import Table

    HAS_RICH = True
    console = Console()
    stderr_console = Console(stderr=True)
except ImportError:
    HAS_RICH = False
    console = None
    stderr_console = None


# Output helpers with Rich fallback
def print_success(message: str, **kwargs):
    """
    Print success message with green checkmark.

    Args:
        message: Success message to display
        **kwargs: Additional arguments passed to rich.print or print

    Example:
        print_success("File saved successfully!")
        # Output: ✓ File saved successfully! (in green)
    """
    if HAS_RICH and console:
        console.print(f"[green]✓[/green] {message}", **kwargs)
    else:
        print(f"✓ {message}", **kwargs)


def print_error(message: str, **kwargs):
    """
    Print error message with red X to stderr.

    Args:
        message: Error message to display
        **kwargs: Additional arguments passed to rich.print or print

    Example:
        print_error("File not found!")
        # Output: ✗ File not found! (in red)
    """
    if HAS_RICH and stderr_console:
        stderr_console.print(f"[red]✗[/red] {message}", **kwargs)
    else:
        print(f"✗ {message}", **kwargs, file=sys.stderr)


def print_warning(message: str, **kwargs):
    """
    Print warning message with yellow warning symbol.

    Args:
        message: Warning message to display
        **kwargs: Additional arguments passed to rich.print or print

    Example:
        print_warning("This operation may take a while")
        # Output: ⚠ This operation may take a while (in yellow)
    """
    if HAS_RICH and console:
        console.print(f"[yellow]⚠[/yellow] {message}", **kwargs)
    else:
        print(f"⚠ {message}", **kwargs)


def print_info(message: str, **kwargs):
    """
    Print info message with blue info symbol.

    Args:
        message: Info message to display
        **kwargs: Additional arguments passed to rich.print or print

    Example:
        print_info("Processing 100 records")
        # Output: ℹ Processing 100 records (in blue)
    """
    if HAS_RICH and console:
        console.print(f"[blue]ℹ[/blue] {message}", **kwargs)
    else:
        print(f"ℹ {message}", **kwargs)


def print_table(
    data: list[dict] | list[list],
    title: str | None = None,
    headers: list[str] | None = None,
    **kwargs,
):
    """
    Print formatted table with auto-detection of columns.

    Args:
        data: List of dicts (keys become headers) or list of lists
        title: Optional table title
        headers: Optional explicit headers (for list of lists)
        **kwargs: Additional arguments passed to rich.table.Table

    Example:
        # From list of dicts
        data = [
            {"name": "Alice", "age": 30, "city": "NYC"},
            {"name": "Bob", "age": 25, "city": "LA"}
        ]
        print_table(data, title="Users")

        # From list of lists with headers
        data = [["Alice", 30, "NYC"], ["Bob", 25, "LA"]]
        print_table(data, headers=["Name", "Age", "City"])
    """
    if not data:
        print_warning("No data to display")
        return

    if HAS_RICH and console:
        table = Table(title=title, **kwargs)

        # Auto-detect columns from first row
        if isinstance(data[0], dict):
            # List of dicts - keys are headers
            headers = list(data[0].keys())
            for header in headers:
                table.add_column(header.replace("_", " ").title(), style="cyan")

            for row in data:
                table.add_row(*[str(row.get(h, "")) for h in headers])
        else:
            # List of lists - use provided headers or generic
            if not headers:
                headers = [f"Column {i + 1}" for i in range(len(data[0]))]

            for header in headers:
                table.add_column(header, style="cyan")

            for row in data:
                table.add_row(*[str(v) for v in row])

        console.print(table)
    else:
        # Fallback to simple text table
        if title:
            print(f"\n{title}")
            print("=" * len(title))

        if isinstance(data[0], dict):
            headers = list(data[0].keys())
            print(" | ".join(headers))
            print("-" * (sum(len(h) for h in headers) + len(headers) * 3))
            for row in data:
                print(" | ".join(str(row.get(h, "")) for h in headers))
        else:
            if headers:
                print(" | ".join(headers))
                print("-" * (sum(len(h) for h in headers) + len(headers) * 3))
            for row in data:
                print(" | ".join(str(v) for v in row))


def print_json(data: Any, pretty: bool = True, **kwargs):
    """
    Print JSON with syntax highlighting (if Rich available).

    Args:
        data: Data to print as JSON (dict, list, etc.)
        pretty: Pretty-print with indentation
        **kwargs: Additional arguments

    Example:
        config = {"host": "localhost", "port": 8000}
        print_json(config)
    """
    if HAS_RICH and console:
        if isinstance(data, str):
            # Already JSON string
            console.print(JSON(data), **kwargs)
        else:
            # Convert to JSON
            json_str = json.dumps(data, indent=2 if pretty else None)
            console.print(JSON(json_str), **kwargs)
    else:
        # Fallback to standard json.dumps
        if isinstance(data, str):
            print(data, **kwargs)
        else:
            print(json.dumps(data, indent=2 if pretty else None), **kwargs)


def print_dict(data: dict, title: str | None = None, **kwargs):
    """
    Print dictionary as formatted key-value pairs.

    Args:
        data: Dictionary to display
        title: Optional title
        **kwargs: Additional arguments

    Example:
        config = {"host": "localhost", "port": 8000, "debug": True}
        print_dict(config, title="Configuration")
    """
    if HAS_RICH and console:
        if title:
            console.print(f"\n[bold]{title}[/bold]")

        for key, value in data.items():
            console.print(f"  [cyan]{key}[/cyan]: {value}", **kwargs)
    else:
        if title:
            print(f"\n{title}")
            print("-" * len(title))

        for key, value in data.items():
            print(f"  {key}: {value}", **kwargs)
