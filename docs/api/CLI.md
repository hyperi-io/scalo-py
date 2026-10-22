# CLI

Typer-based CLI framework with two entry shapes:

- **`ServiceApp`** — service framework. Subclass it, get `run`, `version`,
  `config-check`, and `generate-artefacts` subcommands for free, plus
  standard flags wired into the config cascade, logger setup, and
  metrics auto-init.
- **Raw Typer** — for one-off tools and utilities. The
  `scalo.cli` module re-exports `Typer`, `Argument`, `Option`
  plus a library of pre-built standard options and output helpers.

Use `ServiceApp` for long-running services; use raw Typer for everything
else. Ships in the base package — Typer is a core dependency.

```python
from scalo.cli import (
    Typer, Argument, Option,
    ServiceApp, VersionInfo,
)
```

---

## Quick start — `ServiceApp`

```python
from scalo.cli import ServiceApp, VersionInfo

class MyService(ServiceApp):
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
my-service generate-artefacts   # write the contract JSON + runtime Dockerfile
my-service --help
```

---

## Quick start — raw Typer tool

```python
from pathlib import Path
from scalo.cli import Typer, Argument, Option

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

## `ServiceApp` lifecycle

`ServiceApp` is an abstract base class. Subclasses provide `name`,
`env_prefix`, `version_info()`, and either `run_service()` (sync) or
`run_service_async()` (async). The framework: builds the Typer app,
initialises the logger from `--log-level`/`--log-format`/`--verbose`,
loads configuration via the 7-layer cascade with the app's
`env_prefix`, auto-initialises `AppMetrics` if `scalo[metrics]`
is installed (exposed at `--metrics-addr`), and dispatches to whichever
of `run_service` / `run_service_async` the subclass overrode.

```python
class MyService(ServiceApp):
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
| `generate-artefacts` | Write `deployment-contract.json`, `container-manifest.json`, `Dockerfile.runtime` and `.dockerignore` to the output dir (default `ci/`). Requires `ServiceApp.deployment_contract()` to be overridden. |

Standard flags accepted by `run` and `config-check`:

| Flag | Env var | Default | Purpose |
|------|---------|---------|---------|
| `--config`, `-c` | `CLI_CONFIG` | — | Path to an extra config file added to the cascade |
| `--log-level`, `-l` | `LOG_LEVEL` | `info` | Log level |
| `--log-format` | `LOG_FORMAT` | config, else `auto` | `json`, `text` or `auto` (JSON unless stderr is a TTY); see [LOGGING.md](../core-pillars/LOGGING.md#format-selection) |
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
`scalo.deployment.DeploymentContract`. `my-service
generate-artefacts -o ci/` then writes `deployment-contract.json`,
`container-manifest.json`, `Dockerfile.runtime` and `.dockerignore`.
Requires `scalo[deployment]`. The
default `None` return prints a warning and emits nothing -- services
that don't ship as containers can leave it unset.

A chart assembler turns `deployment-contract.json` into a thin chart on
the scalo-service library chart, which renders the Kubernetes objects.
See [../deployment/ARTEFACTS.md](../deployment/ARTEFACTS.md#kubernetes-objects).

---

## Raw Typer — `scalo.cli` re-exports

The `cli` package re-exports Typer plus a small library of utilities:

```python
from scalo.cli import Typer, Argument, Option
from scalo.cli.options import VERBOSE_OPTION, CONFIG_OPTION, DRY_RUN_OPTION
from scalo.cli.output import (
    print_success, print_error, print_warning, print_info,
    print_table, print_json,
)
from scalo.cli.version import version_option
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
from scalo.cli.output import (
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
from scalo.cli.version import version_option

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

For `ServiceApp`, invoke via `service.cli(["version"])` — pass `args` to
skip `sys.argv`.

---

## Installing as a console script

```toml
[project.scripts]
my-service = "my_package.cli:MyService.cli"  # ServiceApp
my-tool    = "my_package.cli:app"             # raw Typer
```

`pip install` (or `uv tool install`) puts the command on the user's
PATH.

---

## Generated from an OpenAPI spec

`scalo.cli.openapi` turns an OpenAPI spec into a whole CLI, after the AWS CLI's model-driven commands. The spec is the only input, a file or a server's `/openapi.json`, so the CLI installs without FastAPI, uvicorn or mcp. It needs the `cli` extra (`typer`, `jmespath`).

```python
from scalo.cli.openapi import SpecCli, invocation, load_spec

cli = SpecCli(load_spec("openapi.json"), name="svc", version="1.2.3")

@cli.command("auth", "whoami")                  # hand-written, beside the generated commands
def whoami(ctx: typer.Context) -> None:
    run = invocation(ctx)
    run.emit(run.client().send("GET", "/api/v1/auth/me").json())

def main() -> None:
    cli.main()
```

The tree is the spec's resource hierarchy, read from the `x-scalo` extension `scalo.api` writes: a group per resource, a command per verb.

```bash
svc sources rules list --source syslog -o table
svc sources apply --source syslog --body file://source.yaml --if-none-match '*' --dry-run
svc sources apply --generate-cli-skeleton -o yaml > input.yaml
svc sources apply --cli-input-yaml file://input.yaml
```

Without `x-scalo` a dotted `operationId` (`sources.rules.list`) places the command, else its path (`GET /sources/{source}/rules`). Names are lower kebab-case. `x-scalo.cli` hides an operation, adds hidden aliases, and makes parameters positional. Only the branch of the tree an invocation names is built: for a 307-operation spec that took 4 ms, against about 400 ms for the whole tree.

| Option | What it does |
|---|---|
| `--<parameter>` | One per path, query and header parameter, and per top-level writable body field, kebab-case. A name taken twice goes to the later one as `--<location>-<name>`. `readOnly` properties and the headers a client or proxy sets (`Authorization`, `Host`, `X-Forwarded-*`, `X-Oidc-*` and the like) get none |
| `--body` | The whole JSON body as JSON, YAML or `file://<path>`, sent as written. Field options override its fields |
| `--cli-input-json`, `--cli-input-yaml` | Every input as one document with `path`, `query`, `header` and `body` sections. Flags win over it |
| `--generate-cli-skeleton` | Print that document with `null` for every value, JSON or with `-o yaml` YAML, and send nothing |
| `--dry-run`, `-n` | On every operation that declares `dry_run` |
| `--max-items`, `--starting-token`, `--page-size`, `--no-paginate` | On a list that answers `scalo.api`'s page: follow `next_page_token` to the end, cut at `--max-items` and resume mid-page |
| `-o`, `--output` | `json`, `yaml`, `table` or `text`. Default: JSON off a terminal, else YAML for `get`, a table for `list` |
| `--query` | JMESPath, applied before formatting |
| `--endpoint-url`, `--profile` | Where to call and with which stored credential |
| `-y`, `--yes` | Skip the confirmation a delete asks for. Off a terminal a delete without it is refused |
| `--no-input` | Never prompt: a delete without `--yes` is refused even at a terminal |
| `-v`, `--verbose` | Each request and its answer's status on stderr. Credentials are never printed |
| `-q`, `--quiet` | No warnings, and a value or list of values printed bare, one per line, for piping |
| `-d`, `--debug` | Tracebacks instead of one-line errors |

The global options go before any command, or after a generated one. In an input document a `null` counts as not given at any depth, and so does an empty parameter, so a filled-in skeleton sends only what was filled in. An object or list emptied that way is dropped, while one written as `{}` or `[]` is sent. To send an explicit `null`, as a merge patch does to remove a field, use `--body`. A YAML date or timestamp in a body is sent as its ISO 8601 text, and a value JSON has no form for, such as `!!binary`, is refused as bad input.

A list stops following pages at an empty page that still names a next one, and after `max_pages` pages (`SpecCli(max_pages=...)`, 10,000 by default). Either way it warns and prints the `next_page_token` to resume from. A table prints that token on a last line, `next_page_token: <token>`.

The endpoint comes from `--endpoint-url`, then `<PREFIX>_API_URL`, then the profile. The credential comes from `<PREFIX>_API_KEY` (sent as `X-API-Key`), then `<PREFIX>_API_TOKEN` (a bearer token), then the profile's stored credential. Profiles live under `~/.config/<name>`, moved by `<PREFIX>_CONFIG_HOME`. `Store` reads and writes them, and `Credential` is what it stores, for a login command. The credential file is replaced whole on every save, and one that does not parse is a configuration error rather than an empty store, so a save never drops accounts it could not read. A save or delete holds an advisory lock on `.credentials.lock` beside it, `fcntl` on POSIX and `msvcrt` on Windows, so two CLI processes saving at once keep both accounts.

Exit codes come from the problem+json status. A failed command prints its report on stderr: a JSON object when the output format is JSON, otherwise lines for a person. Both name the input that failed and, where the CLI can tell, a suggestion:

```json
{"error_type": "source_not_found", "message": "no source 'nope'", "input": {"source": "nope"},
 "suggestion": "run 'svc sources list' to see what exists", "retryable": false, "status": 404}
```

| Code | When |
|---|---|
| 0 | Success |
| 1 | 5xx, 429, an unreachable API |
| 2 | Bad flags or input, or a 400, 422 or 428 |
| 3 | 404 or 410 |
| 4 | 401 or 403 |
| 5 | 409 or 412 |

`UrllibTransport` sends requests by default, stdlib only and with scalo's TLS posture, never carrying credentials to a redirect target. `ScaloHttpTransport` sends through `scalo.http`, retrying GET and HEAD, for a consumer with the `http` extra. Any object with the `Transport` method serves, such as one over an in-process ASGI app in tests: it returns a `Response`, and raises `TransportError` when no answer arrived.

`SpecCli.command(*path)` registers a Typer function at a path and `SpecCli.add_typer(app, *path)` mounts a Typer app. Both refuse a taken path unless `replace=True`. `invocation(ctx)` hands a hand-written command the run's `Invocation`: the same endpoint, credential, output and error handling the generated ones use. `load_spec` raises `SpecError` for a document it cannot read. Those twelve names are the package's exports.

---

## When to reach for which

| Building | Use |
|----------|-----|
| Long-running service (Kafka consumer, FastAPI, scheduled worker) | `ServiceApp` |
| Operator tool / data-pipeline runner / one-off CLI | Raw Typer + standard options |
| CLI for a service that publishes an OpenAPI spec | `scalo.cli.openapi.SpecCli` |
| Quick script bound to one function | Raw `app.command()` |
| Custom subcommands on top of `ServiceApp` defaults | `register_commands` |

---

## Related

- [../INTEGRATION.md](../INTEGRATION.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
- [../core-pillars/METRICS.md](../core-pillars/METRICS.md)
- [../deployment/CONTRACT.md](../deployment/CONTRACT.md)
- [VERSION-CHECK.md](VERSION-CHECK.md)
