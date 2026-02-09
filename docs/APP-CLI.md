# CLI Applications

Command-line tools using Typer framework (mandatory hyperi-pylib standard).

## Quick Start

```python
from hyperi_pylib import Application

app = Application.cli(name="my-tool", version="1.0.0")

@app.command()
def sync(source: str, dest: str, verbose: bool = False):
    """Sync files from source to dest."""
    print(f"Syncing {source} -> {dest}")
    if verbose:
        print("Verbose mode enabled")

@app.command()
def process(file: str, format: str = "json"):
    """Process data file."""
    print(f"Processing {file} as {format}")

app.run()
```

Usage:
```bash
my-tool sync /src /dest --verbose
my-tool process data.json --format csv
my-tool --version
my-tool --help
```

## Features

- **Type-driven**: Automatic arg parsing from type hints
- **Auto-help**: Generated from docstrings and signatures
- **Subcommands**: Organize commands into groups
- **Rich output**: Color terminal output via Rich
- **Profile support**: Environment-based config (dev/docker/prod)

## Command Groups

```python
from typer import Typer

app = Application.cli(name="myapp")

# Create sub-app for database commands
db_app = Typer(help="Database commands")

@db_app.command()
def migrate():
    """Run migrations."""
    print("Running migrations...")

@db_app.command()
def backup():
    """Backup database."""
    print("Backing up...")

# Add to main app
app.add_typer(db_app, name="db")
```

Usage:
```bash
myapp db migrate
myapp db backup
```

## Global Options

```python
@app.callback()
def main(
    verbose: bool = False,
    config: str = "config.yaml"
):
    """My application."""
    if verbose:
        logger.setLevel("DEBUG")
    load_config(config)
```

All commands inherit callback settings:
```bash
myapp --verbose sync /src /dest
myapp --config prod.yaml process data.json
```

## Profiles

CLI apps support profile-based configuration:

```python
app = Application.cli(
    name="my-tool",
    profile="prod",  # dev/docker/prod
    profile_overrides={"logging": {"level": "INFO"}}
)
```

## Example: Data Processing Tool

```python
from hyperi_pylib import Application, logger
from pathlib import Path

app = Application.cli(
    name="data-tool",
    version="2.1.0",
    profile="prod"
)

@app.command()
def extract(
    source: Path,
    output: Path,
    format: str = "json"
):
    """Extract data from source file."""
    logger.info(f"Extracting {source} to {output}")
    data = load_data(source)
    save_data(output, data, format)
    logger.success(f"Extracted {len(data)} records")

@app.command()
def transform(
    input: Path,
    output: Path,
    rules: Path
):
    """Transform data using rules file."""
    logger.info("Loading transformation rules...")
    rules = load_rules(rules)
    data = load_data(input)

    transformed = apply_rules(data, rules)
    save_data(output, transformed)
    logger.success("Transformation complete")

@app.command()
def validate(file: Path, schema: Path):
    """Validate data against schema."""
    data = load_data(file)
    schema_obj = load_schema(schema)

    errors = validate_schema(data, schema_obj)
    if errors:
        logger.error(f"Validation failed: {len(errors)} errors")
        for error in errors:
            logger.error(f"  - {error}")
        raise typer.Exit(1)

    logger.success("Validation passed")

if __name__ == "__main__":
    app.run()
```

## Container Usage

CLI apps work in containers:

```dockerfile
CMD ["python", "-m", "my_tool", "extract", "/data/input", "/data/output"]
```

```bash
docker run my-tool extract /data/input /data/output --format csv
```

## Testing

```python
from typer.testing import CliRunner

runner = CliRunner()
result = runner.invoke(app.app, ["sync", "/src", "/dest"])
assert result.exit_code == 0
```

## Why Typer (Not Click)?

Typer is the **mandatory standard** for hyperi-pylib CLI apps:

- Better type hints (uses Python 3.10+ syntax)
- Automatic validation
- Rich terminal output by default
- Simpler decorator syntax
- Maintained by FastAPI author (same ecosystem)

Migration from Click is straightforward - see [CLI-STANDARDS.md](CLI-STANDARDS.md) for details.
