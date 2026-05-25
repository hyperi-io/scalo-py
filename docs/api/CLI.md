# CLI

Typer-based CLI framework with two entry shapes:

- **`DfeApp`** — service framework. Subclass it, get `run`, `version`,
  `config-check`, and `generate-artefacts` subcommands for free, plus
  standard flags wired into the config cascade, logger setup, and
  metrics auto-init.
- **Raw Typer** — for one-off tools and utilities. The
  `hyperi_pylib.cli` module re-exports `Typer`, `Argument`, `Option`
  plus a library of pre-built standard options and output helpers.

Use `DfeApp` for long-running services; use raw Typer for everything
else. Ships in the base package — Typer is a core dependency.

```python
from hyperi_pylib.cli import (
    Typer, Argument, Option,
    DfeApp, VersionInfo,
)
```

---

## Quick start — `DfeApp`

```python
from hyperi_pylib.cli import DfeApp, VersionInfo

class MyService(DfeApp):
    name = "my-service"
    env_prefix = "MY_SVC"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    def run_service(self, config) -> None:
        # config is the loaded Dynaconf settings object
        ...

if __name__ == "__main__":
    MyService().cli()
```

That gives you:

```bash
my-service run                  # start the service
my-service version              # print version
my-service config-check         # validate config and exit
my-service generate-artefacts   # write Dockerfile + ArgoCD manifest
my-service --help
```

---

## Quick start — raw Typer tool

```python
from pathlib import Path
from hyperi_pylib.cli import Typer, Argument, Option

app = Typer(help="My tool")

@app.command()
def process(
    file: Path = Argument(..., help="Input file"),
    verbose: bool = Option(False, "--verbose", "-v"),
):
    """Process a file."""
    ...

if __name__ == "__main__":
    app()
```

---

## `DfeApp` lifecycle

`DfeApp` is an abstract base class. Subclasses provide `name`,
`env_prefix`, `version_info()`, and either `run_service()` (sync) or
`run_service_async()` (async). The framework: builds the Typer app,
initialises the logger from `--log-level`/`--log-format`/`--verbose`,
loads configuration via the 8-layer cascade with the app's
`env_prefix`, auto-initialises `AppMetrics` if `hyperi-pylib[metrics]`
is installed (exposed at `--metrics-addr`), and dispatches to whichever
of `run_service` / `run_service_async` the subclass overrode.

```python
class MyService(DfeApp):
    name = "my-service"
    env_prefix = "MY_SVC"

    def version_info(self):
        return VersionInfo(self.name, "1.0.0", commit="abc123")

    def run_service(self, config):       # sync — config is Dynaconf settings
        ...
    # async def run_service_async(self, config): ...   # async alternative
```

---

## Standard subcommands

| Subcommand | What it does |
|------------|--------------|
| `run` (default) | Initialise logger + config + metrics, then call `run_service` / `run_service_async`. |
| `version` | Print the `VersionInfo` and exit. |
| `config-check` | Validate the cascade loads cleanly, print a key-value summary to stderr, exit. |
| `generate-artefacts` | Write `deployment-contract.json`, `container-manifest.json`, `Dockerfile.runtime`, `argocd-application.yaml` to the output dir (default `ci/`). Requires `DfeApp.deployment_contract()` to be overridden. |

Standard flags accepted by `run` and `config-check`:

| Flag | Env var | Default | Purpose |
|------|---------|---------|---------|
| `--config`, `-c` | `CLI_CONFIG` | — | Path to an extra config file added to the cascade |
| `--log-level`, `-l` | `LOG_LEVEL` | `info` | Log level |
| `--log-format` | `LOG_FORMAT` | `auto` | `json`, `text`, or `auto` (TTY-detect) |
| `--metrics-addr` | `METRICS_ADDR` | `0.0.0.0:9090` | Bind address for `/metrics` |
| `--verbose`, `-v` | — | False | Force `DEBUG` |
| `--quiet`, `-q` | — | False | Suppress non-error output |

`--verbose` and `--quiet` are mutually exclusive — passing both exits
with code 1.

---

## Custom subcommands

Override `register_commands` to add your own:

```python
def register_commands(self, app):
    @app.command()
    def migrate(target: str = "latest"):
        """Run database migrations."""
        ...
```

Custom commands sit alongside `run`, `version`, etc. on the same Typer
app.

---

## Deployment artefacts

Override `deployment_contract()` to return a
`hyperi_pylib.deployment.DeploymentContract`. `my-service
generate-artefacts -o ci/` then writes `deployment-contract.json`,
`container-manifest.json`, `Dockerfile.runtime`, and
`argocd-application.yaml`. Requires `hyperi-pylib[deployment]`. The
default `None` return prints a warning and emits nothing — services
that don't ship as containers can leave it unset.

---

## Raw Typer — `hyperi_pylib.cli` re-exports

The `cli` package re-exports Typer plus a small library of utilities:

```python
from hyperi_pylib.cli import Typer, Argument, Option
from hyperi_pylib.cli.options import VERBOSE_OPTION, CONFIG_OPTION, DRY_RUN_OPTION
from hyperi_pylib.cli.output import (
    print_success, print_error, print_warning, print_info,
    print_table, print_json,
)
from hyperi_pylib.cli.version import version_option
```

---

## Standard options

Pre-configured `Option(...)` values for any command signature:

| Name | Flag | Type | Env var |
|------|------|------|---------|
| `VERBOSE_OPTION` | `--verbose`, `-v` | `bool` | `CLI_VERBOSE` |
| `QUIET_OPTION` | `--quiet`, `-q` | `bool` | `CLI_QUIET` |
| `DEBUG_OPTION` | `--debug`, `-d` | `bool` | `CLI_DEBUG` |
| `LOG_LEVEL_OPTION` | `--log-level`, `-l` | `str` | `LOG_LEVEL` |
| `LOG_FILE_OPTION` | `--log-file` | `str \| None` | `LOG_FILE` |
| `CONFIG_OPTION` | `--config`, `-c` | `str \| None` | `CLI_CONFIG` |
| `ENV_OPTION` | `--env`, `-e` | `str` (`"dev"`) | `ENVIRONMENT` |
| `DRY_RUN_OPTION` | `--dry-run` | `bool` | `CLI_DRY_RUN` |
| `FORCE_OPTION` | `--force`, `-f` | `bool` | `CLI_FORCE` |
| `YES_OPTION` | `--yes`, `-y` | `bool` | `CLI_YES` |
| `OUTPUT_OPTION` | `--output`, `-o` | `str` (`"table"`) | `CLI_OUTPUT_FORMAT` |

`CONFIG_OPTION` is typed `str | None` (not `Path`) — convert at the
call site if you need a `Path`.

```python
@app.command()
def deploy(verbose: bool = VERBOSE_OPTION,
           config: str | None = CONFIG_OPTION,
           dry_run: bool = DRY_RUN_OPTION):
    cfg_path = Path(config) if config else None
```

`path_option(...)` and `enum_option(...)` helpers build options with
per-call validation (e.g. `exists=True`, `dir_okay=False`, enum
choices).

---

## Output helpers

```python
from hyperi_pylib.cli.output import (
    print_success, print_error, print_warning, print_info,
    print_table, print_json,
)

print_success("Deployment complete")
print_error("DB unreachable")
print_warning("Skipping signed-image check (dev mode)")
print_info("Processing 100 records")

print_table([{"name": "a", "status": "ok"}, {"name": "b", "status": "fail"}],
            title="Workers")

print_json({"host": "localhost", "port": 5432})
```

Built on `rich` — automatic colour when stdout is a TTY, plain text
in pipes and CI.

---

## Version option

```python
from hyperi_pylib.cli.version import version_option

@app.callback()
def main(
    version: bool = version_option("myapp", app_name="My Application"),
):
    """My App"""
    ...
```

Adds `--version` to the root command. Reads the installed package
version automatically.

---

## Testing CLIs

Typer ships `CliRunner` from Click:

```python
from typer.testing import CliRunner
from my_tool import app

result = CliRunner().invoke(app, ["process", "input.txt", "--verbose"])
assert result.exit_code == 0
```

For `DfeApp`, invoke via `service.cli(["version"])` — pass `args` to
skip `sys.argv`.

---

## Installing as a console script

```toml
[project.scripts]
my-service = "my_package.cli:MyService.cli"  # DfeApp
my-tool    = "my_package.cli:app"             # raw Typer
```

`pip install` (or `uv tool install`) puts the command on the user's
PATH.

---

## When to reach for which

| Building | Use |
|----------|-----|
| Long-running service (Kafka consumer, FastAPI, scheduled worker) | `DfeApp` |
| Operator tool / data-pipeline runner / one-off CLI | Raw Typer + standard options |
| Quick script bound to one function | Raw `app.command()` |
| Custom subcommands on top of `DfeApp` defaults | `register_commands` |

---

## Related

- [../INTEGRATION.md](../INTEGRATION.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
- [../core-pillars/METRICS.md](../core-pillars/METRICS.md)
- [../deployment/CONTRACT.md](../deployment/CONTRACT.md)
- [VERSION-CHECK.md](VERSION-CHECK.md)
- [HARNESS.md](HARNESS.md)
