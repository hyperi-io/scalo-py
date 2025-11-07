# CLI Development Standards for HyperLib

**Mandatory standard for all HyperLib CLI applications**

---

## Overview

**Typer is the mandatory CLI framework** for all HyperSec Python CLI applications. Typer provides:
- Type-hint driven interface (like FastAPI for CLIs)
- Automatic validation and help generation
- Excellent IDE support and type checking
- Rich terminal output capabilities
- Easy testing with CliRunner

**Repository:** https://github.com/fastapi/typer
**Documentation:** https://typer.tiangolo.com/
**Stars:** 18k+

---

## Installation

```bash
# Install hyperlib with CLI support
pip install hyperlib[cli]

# For development (includes all dependencies)
pip install hyperlib[dev,cli]
```

---

## HyperLib CLI Utilities

HyperLib provides ready-to-use utilities to accelerate CLI development:

### Output Formatting (`hyperlib.cli.output`)

```python
from hyperlib.cli.output import print_success, print_error, print_table, print_json

# Status messages with colors
print_success("Deployment completed!")
print_error("Failed to connect to database")
print_warning("This may take a while")
print_info("Processing 100 records")

# Formatted tables
data = [
    {"name": "Alice", "role": "Admin", "status": "active"},
    {"name": "Bob", "role": "User", "status": "inactive"}
]
print_table(data, title="Users")

# Syntax-highlighted JSON
config = {"host": "localhost", "port": 8000}
print_json(config)
```

### Reusable Options (`hyperlib.cli.options`)

```python
from hyperlib.cli import Typer
from hyperlib.cli.options import VERBOSE_OPTION, CONFIG_OPTION, DRY_RUN_OPTION

app = Typer()

@app.command()
def deploy(
    verbose: bool = VERBOSE_OPTION,      # --verbose, -v
    config: str = CONFIG_OPTION,         # --config, -c
    dry_run: bool = DRY_RUN_OPTION,      # --dry-run
):
    """Deploy application with standard options."""
    if verbose:
        print("Verbose mode enabled")
```

**Available standard options:**
- `VERBOSE_OPTION` - Verbose output (--verbose, -v)
- `QUIET_OPTION` - Suppress output (--quiet, -q)
- `DEBUG_OPTION` - Debug mode (--debug, -d)
- `CONFIG_OPTION` - Config file (--config, -c)
- `ENV_OPTION` - Environment selection (--env, -e)
- `DRY_RUN_OPTION` - Dry run mode (--dry-run)
- `FORCE_OPTION` - Force operation (--force, -f)
- `YES_OPTION` - Auto-confirm (--yes, -y)
- `OUTPUT_OPTION` - Output format (--output, -o)
- `LOG_LEVEL_OPTION` - Log level (--log-level, -l)
- `LOG_FILE_OPTION` - Log file (--log-file)

### Version Handling (`hyperlib.cli.version`)

```python
from hyperlib.cli import Typer
from hyperlib.cli.version import version_option

app = Typer()

@app.callback()
def main(
    version: bool = version_option("myapp", app_name="My Application")
):
    """My Application CLI"""
    pass

# Usage: myapp --version
# Output: My Application version 1.2.3
```

---

## Basic Usage

### Simple Single-Command CLI

```python
# my_tool.py
from hyperlib.cli import Typer, Argument, Option

app = Typer(help="My awesome CLI tool")

@app.command()
def process(
    file: str = Argument(..., help="Input file to process"),
    output: str = Option(None, help="Output file"),
    verbose: bool = Option(False, "--verbose", "-v", help="Verbose output")
):
    """Process input file and generate output."""
    print(f"Processing {file}...")
    if output:
        print(f"Writing to {output}")
    if verbose:
        print("  [Verbose mode enabled]")

if __name__ == "__main__":
    app()
```

**Run it:**
```bash
python my_tool.py input.txt --output out.txt -v
python my_tool.py --help
```

---

### Multi-Command CLI (like git)

```python
# data_tool.py
from pathlib import Path
from hyperlib.cli import Typer, Argument, Option

app = Typer(help="Data processing toolkit")

@app.command()
def extract(
    source: Path = Argument(..., help="Source file"),
    format: str = Option("csv", help="Input format")
):
    """Extract data from source."""
    print(f"Extracting from {source} ({format})")

@app.command()
def transform(
    input: Path = Argument(..., help="Input file"),
    output: Path = Argument(..., help="Output file")
):
    """Transform data."""
    print(f"Transforming {input} → {output}")

@app.command()
def load(
    data: Path = Argument(..., help="Data file"),
    target: str = Option(..., help="Target database")
):
    """Load data to target."""
    print(f"Loading {data} to {target}")

if __name__ == "__main__":
    app()
```

**Run it:**
```bash
python data_tool.py extract data.csv --format csv
python data_tool.py transform input.csv output.json
python data_tool.py load output.json --target postgresql://...
```

---

## Standards and Best Practices

### 1. Type Hints are MANDATORY

**✅ Good:**
```python
def backup(
    source: Path = Argument(...),
    count: int = Option(1),
    verbose: bool = Option(False)
):
    """Backup files."""
    pass
```

**❌ Bad:**
```python
def backup(source, count=1, verbose=False):  # No type hints!
    pass
```

### 2. Add Help Text to ALL Parameters

**✅ Good:**
```python
def deploy(
    env: str = Option(..., help="Environment: dev/staging/prod"),
    force: bool = Option(False, help="Skip safety checks")
):
    """Deploy application."""
    pass
```

**❌ Bad:**
```python
def deploy(
    env: str = Option(...),  # No help text!
    force: bool = Option(False)
):
    pass
```

### 3. Use Docstrings for Command Descriptions

**✅ Good:**
```python
@app.command()
def validate(file: Path):
    """
    Validate data file against schema.

    This command checks the data file for format errors
    and validates against the specified schema.
    """
    pass
```

**❌ Bad:**
```python
@app.command()
def validate(file: Path):  # No docstring!
    pass
```

### 4. Use Path for File Arguments

**✅ Good:**
```python
from pathlib import Path

def process(input: Path = Argument(...)):
    """Process file."""
    if not input.exists():
        raise FileNotFoundError(f"{input} not found")
```

**❌ Bad:**
```python
def process(input: str = Argument(...)):  # Use Path, not str!
    pass
```

### 5. Provide Sensible Defaults

**✅ Good:**
```python
def backup(
    source: Path,
    compress: bool = Option(False, help="Compress backup"),  # Default False
    format: str = Option("tar.gz", help="Archive format")   # Default tar.gz
):
    pass
```

**❌ Bad:**
```python
def backup(
    source: Path,
    compress: bool = Option(..., help="Compress?"),  # No default!
    format: str = Option(..., help="Format?")        # No default!
):
    pass
```

### 6. Use Enums for Fixed Choices

**✅ Good:**
```python
from enum import Enum

class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

def run(log_level: LogLevel = Option(LogLevel.INFO)):
    """Run with specified log level."""
    print(f"Log level: {log_level.value}")
```

**❌ Bad:**
```python
def run(log_level: str = Option("info")):  # Use Enum for validation!
    if log_level not in ["debug", "info", "warning", "error"]:
        raise ValueError("Invalid log level")
```

### 7. Follow "Clarity Over Cleverness" Code Style

See [PYTHON-STANDARDS.md](../ci/docs/standards/PYTHON-STANDARDS.md) for complete code style standards.

**✅ Good:**
```python
def process(files: list[Path]):
    """Process multiple files."""
    # Clear, step-by-step processing
    successful = []
    failed = []

    for file in files:
        try:
            result = validate_and_process(file)
            successful.append(file)
        except Exception as e:
            failed.append((file, str(e)))

    # Report results
    print(f"Processed: {len(successful)}")
    print(f"Failed: {len(failed)}")
```

**❌ Bad:**
```python
def process(files: list[Path]):
    # Dense, hard to follow
    results = [(f, validate_and_process(f)) for f in files if not (lambda x: x.catch(Exception))(f)]
```

---

## Testing CLI Applications

Typer provides excellent testing support:

```python
# test_my_tool.py
from typer.testing import CliRunner
from my_tool import app

runner = CliRunner()

def test_process_command():
    result = runner.invoke(app, ["process", "input.txt", "--verbose"])
    assert result.exit_code == 0
    assert "Processing input.txt" in result.output

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "My awesome CLI tool" in result.output
```

---

## Integration with HyperLib

### Using hyperlib.config

```python
from hyperlib.cli import Typer, Option
from hyperlib.config import get_config

app = Typer()

@app.command()
def deploy(env: str = Option(...)):
    """Deploy using hyperlib config."""
    config = get_config()
    app_name = config.get("app_name")
    print(f"Deploying {app_name} to {env}")
```

### Using hyperlib.logger

```python
from hyperlib.cli import Typer
from hyperlib.logger import get_logger

app = Typer()
logger = get_logger(__name__)

@app.command()
def process():
    """Process with logging."""
    logger.info("Starting process")
    # Your logic
    logger.info("Process complete")
```

---

## Rich Output (Optional)

Typer includes Rich for beautiful terminal output:

```python
from hyperlib.cli import Typer
from rich.console import Console
from rich.table import Table

app = Typer()
console = Console()

@app.command()
def status():
    """Show colorful status."""
    console.print("[bold blue]System Status[/bold blue]")

    table = Table(title="Services")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="magenta")

    table.add_row("API", "✓ Running")
    table.add_row("Database", "✓ Running")

    console.print(table)
```

---

## Why Typer? (vs Alternatives)

### Typer vs argparse

| Feature | Typer | argparse |
|---------|-------|----------|
| Type hints | ✅ Yes | ❌ No |
| Stdlib | ❌ No | ✅ Yes |
| Boilerplate | Minimal | Heavy |
| IDE support | Excellent | Poor |
| Rich output | Built-in | Manual |

**When to use argparse:** Stdlib-only security requirement

### Typer vs Click

| Feature | Typer | Click |
|---------|-------|-------|
| Type hints | ✅ Yes | ❌ No |
| Learning curve | Low | Medium |
| Built on | Click | - |
| Control | High-level | Low-level |

**When to use Click:** Need maximum control over CLI behavior

### Typer vs Fire

| Feature | Typer | Fire |
|---------|-------|------|
| Type hints | ✅ Yes | ✅ Yes |
| Explicit | ✅ Yes | ❌ No (too magical) |
| Production | ✅ Yes | ⚠️ Prototyping |
| Help generation | Excellent | Basic |

**When to use Fire:** Rapid prototyping only

---

## FAQ

**Q: Do I need FastAPI to use Typer?**
A: No! Typer has zero FastAPI dependency. It's completely standalone.

**Q: Can I use async functions with Typer?**
A: Yes! Typer supports async commands out of the box.

**Q: How do I install a Typer CLI as a command?**
A: Use pyproject.toml scripts:
```toml
[project.scripts]
mytool = "mypackage.cli:app"
```

**Q: What if I need more control than Typer provides?**
A: Typer is built on Click. You can drop down to Click for advanced features.

---

## Complete Example: Production CLI App

```python
from pathlib import Path
from hyperlib.cli import Typer
from hyperlib.cli.options import VERBOSE_OPTION, CONFIG_OPTION, DRY_RUN_OPTION
from hyperlib.cli.output import print_success, print_error, print_table
from hyperlib.cli.version import version_option

app = Typer(help="My Production Application")

@app.callback()
def main(
    version: bool = version_option("myapp", app_name="MyApp")
):
    """MyApp - Production-ready CLI application"""
    pass

@app.command()
def deploy(
    environment: str,
    verbose: bool = VERBOSE_OPTION,
    config: Path = CONFIG_OPTION,
    dry_run: bool = DRY_RUN_OPTION,
):
    """Deploy application to environment."""
    try:
        if dry_run:
            print_warning("DRY RUN MODE - No changes will be made")

        if verbose:
            print_info(f"Deploying to {environment}")
            if config:
                print_info(f"Using config: {config}")

        # Deployment logic here
        result = {"service": "api", "status": "deployed", "instances": 3}

        print_success(f"Deployment to {environment} completed!")
        print_table([result], title="Deployment Summary")

    except Exception as e:
        print_error(f"Deployment failed: {e}")
        raise

if __name__ == "__main__":
    app()
```

**Usage:**
```bash
# Show version
myapp --version

# Deploy with all options
myapp deploy production --verbose --dry-run --config prod.yaml

# Get help
myapp --help
myapp deploy --help
```

---

## Examples

Complete examples are available in:
- [hyperlib/cli/examples.py](../src/hyperlib/cli/examples.py)
- [hyperlib/cli/output.py](../src/hyperlib/cli/output.py) - Output utilities
- [hyperlib/cli/options.py](../src/hyperlib/cli/options.py) - Reusable options
- [hyperlib/cli/version.py](../src/hyperlib/cli/version.py) - Version handling
- [Typer documentation](https://typer.tiangolo.com/tutorial/)

---

## Summary

✅ **DO:**
- Use type hints for all parameters
- Add help text to all options/arguments
- Use docstrings for command descriptions
- Use Path for file arguments
- Provide sensible defaults
- Use Enums for fixed choices
- Follow "Clarity Over Cleverness"
- Test with CliRunner

❌ **DON'T:**
- Skip type hints
- Skip help text
- Use str for file paths (use Path)
- Make all options required (provide defaults)
- Write dense, clever code

---

**Last Updated:** 2025-11-07
**Version:** 1.0.0
**Status:** Mandatory for all HyperLib CLI applications
