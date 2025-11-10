"""
Example CLI applications using Typer with hyperlib.

These examples demonstrate best practices for CLI development.
"""

from pathlib import Path
from typing import Optional

from hyperlib.cli import Argument, Option, Typer

# Example 1: Simple single-command CLI
simple_app = Typer(help="Simple backup utility")


@simple_app.command()
def backup(
    source: Path = Argument(..., help="Source directory to backup"),
    dest: Path = Argument(..., help="Destination for backup"),
    compress: bool = Option(False, help="Compress the backup"),
    verbose: bool = Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Backup files from source to destination."""
    print(f"Backing up {source} → {dest}")
    if compress:
        print("  [Compressing...]")
    if verbose:
        print("  [Verbose mode enabled]")


# Example 2: Multi-command CLI (like git)
data_app = Typer(help="Data processing CLI")


@data_app.command()
def validate(
    file: Path = Argument(..., help="Data file to validate"),
    schema: Path | None = Option(None, help="JSON schema file"),
    strict: bool = Option(False, help="Strict validation mode"),
):
    """Validate data file against schema."""
    print(f"Validating {file}")
    if schema:
        print(f"  Using schema: {schema}")
    if strict:
        print("  [Strict mode]")


@data_app.command()
def convert(
    input_file: Path = Argument(..., help="Input file"),
    output: Path = Argument(..., help="Output file"),
    format: str = Option("json", help="Output format: json, parquet, csv"),
):
    """Convert data between formats."""
    print(f"Converting {input_file} → {output} ({format})")


@data_app.command()
def stats(file: Path = Argument(..., help="Data file")):
    """Show statistics about data file."""
    print(f"Statistics for {file}:")
    print("  Rows: 1000")
    print("  Columns: 10")


# Example 3: CLI with rich output
rich_app = Typer(help="CLI with rich formatting")


@rich_app.command()
def status():
    """Show colorful status."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        # Title
        console.print("[bold blue]System Status[/bold blue]")

        # Table
        table = Table(title="Services")
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="magenta")

        table.add_row("API", "✓ Running")
        table.add_row("Database", "✓ Running")
        table.add_row("Cache", "⚠ Degraded")

        console.print(table)
    except ImportError:
        # Fallback if rich not available
        print("System Status")
        print("Services:")
        print("  API: Running")
        print("  Database: Running")
        print("  Cache: Degraded")


# Example 4: CLI with environment config integration
config_app = Typer(help="CLI with hyperlib config integration")


@config_app.command()
def deploy(
    env: str = Option(..., help="Environment: dev/staging/prod"),
    force: bool = Option(False, help="Skip safety checks"),
):
    """Deploy application to environment."""
    # Integration with hyperlib.config
    try:
        from hyperlib.config import get_config

        config = get_config()
        print(f"Deploying to {env}")
        print(f"  Config: {config.get('app_name', 'unknown')}")
    except ImportError:
        print(f"Deploying to {env}")

    if force:
        print("  [Force mode - skipping safety checks]")


if __name__ == "__main__":
    # Run examples (you'd normally pick one)
    print("=== Example 1: Simple CLI ===")
    simple_app(["backup", "/src", "/dest", "--compress"], standalone_mode=False)

    print("\n=== Example 2: Multi-command CLI ===")
    data_app(["validate", "data.json"], standalone_mode=False)

    print("\n=== Example 3: Rich output ===")
    rich_app(["status"], standalone_mode=False)

    print("\n=== Example 4: Config integration ===")
    config_app(["deploy", "--env", "staging"], standalone_mode=False)
