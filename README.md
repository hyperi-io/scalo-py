# scalo

<!-- BADGES:START -->
| | |
| --- | --- |
| Build | [![Build Status](https://github.com/hyperi-io/scalo-py/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/scalo-py/actions) |
| Package | [![PyPI](https://img.shields.io/pypi/v/scalo?logo=pypi)](https://pypi.org/project/scalo/) [![Python Version](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/) |
| Meta | [![License](https://img.shields.io/badge/license-Apache--2.0-green)](https://www.apache.org/licenses/LICENSE-2.0) |
<!-- BADGES:END -->

The runtime layer for Python control-plane services: config, logging, metrics, health probes, secrets and a service CLI, already wired together. In a DFE deployment dfe-engine is built on it, with the same config and logging conventions scalo-rs gives the Rust services.

## What it gives you

- A seven-layer config cascade, from CLI flags and env vars down to YAML and defaults, that reads the same in a laptop shell and a Kubernetes pod.
- Structured logs, JSON in a container and readable text at a terminal, with secrets, credential fields and validated PII values redacted at every level but TRACE, which the scrubber skips by default.
- `ServiceApp`: subclass it and get `run`, `version`, `config-check` and `generate-artefacts`, with config and logging started for you.
- `/livez` and `/readyz` on an observability port kept apart from your application's own.
- Prometheus and OpenTelemetry metrics with the `metrics` extra, scraped from `/metrics` on the same port. Without a metrics manager that path answers 404.
- Secrets from OpenBao or Vault, AWS, GCP, Azure, Kubernetes and Ansible Vault, one extra per backend.
- A deployment contract that writes your runtime Dockerfile and the input the scalo-service Helm chart renders from.

## Install

```bash
uv add scalo                                    # core
uv add "scalo[http,metrics,kafka]"              # common extras
uv add "scalo[http,metrics,expression,kafka,opentelemetry,secrets,deployment]"
```

`scalo` on PyPI, `scalo` for imports. Extras and their install sizes are in
[docs/extras-flags.md](docs/extras-flags.md) -- `secrets-aws` alone is ~100 MB, so
pick the backend you use rather than `secrets`.

## What it is for

Control-plane APIs, UI backends, orchestrators, CLI tools, integration glue, batch
workloads, configuration management.

Not the hot path. Processing millions of messages a second belongs in Rust --
[scalo-rs](https://github.com/hyperi-io/scalo-rs) is the sister library for that.
scalo-py is fast enough for control plane and integration; scalo-rs is fast enough
for the hot path. So scalo-py leans to stability, expressiveness and integration:
readable abstractions over inlined ones, heavier deps where they earn their keep,
no agonising over async dispatch overhead.

Same conventions, DIFFERENT API, separate repo. Never assume parity.

This module exists because of this -- but for the backend:
<https://www.youtube.com/watch?v=xE9W9Ghe4Jk>

## What is in the box

Core, always installed:

| Module | What it does | Deps |
|---|---|---|
| `logger` | Structured logging, JSON in a container. Redacts gitleaks secret patterns, credential field names, card numbers (Luhn-checked), IBANs, emails and phone numbers, and AU ABN, ACN, TFN and Medicare numbers where a keyword names them. TRACE records skip the scrubber by default (`logging.scrub.log_levels.trace`) | loguru |
| `config` | 7-layer cascade (CLI -> ENV -> .env -> YAML -> defaults) | dynaconf, pyyaml, python-dotenv, mergedeep, tomli-w, dulwich |
| `runtime` | Detects K8s / Docker / local, resolves config and data paths | stdlib only |
| `cli` | `ServiceApp` -- subclass for `run` / `version` / `config-check` | typer |
| `version-check` | Optional startup check for a newer release | httpx (lazy) |

By extra: `api` (FastAPI conventions: operation ids, ETag/If-Match, problem+json,
pagination, a conformance check), `cli` (a whole CLI generated from an OpenAPI spec alone),
`http` (retry with jitter), `metrics` (Prometheus + process and container
gauges), `expression` (CEL), `kafka` (produce, consume, schema inference),
`opentelemetry` (OTLP traces and metrics), `secrets` (OpenBao/Vault, AWS, GCP,
Azure, Kubernetes Secret), `deployment` (Dockerfile, container manifest, compose generators).

Wired together already, which is the part you would otherwise build: config,
logging and metrics are global singletons with no init dance beyond the logger's one
`setup()`, which `ServiceApp` runs for you. The cascade feeds the
CLI so `run`, `version` and `config-check` work without you parsing an argument;
the metrics and health wiring feeds the Kubernetes probes; the deployment contract,
built from the config the app already declares, writes your Dockerfile and drives
the scalo-service chart that renders your Kubernetes objects.

## Documentation

[docs/README.md](docs/README.md) is the index. The ones you want first:

| Topic | Doc |
|---|---|
| Config cascade | [core-pillars/config.md](docs/core-pillars/config.md) |
| Logging and PII scrubbing | [core-pillars/logging.md](docs/core-pillars/logging.md) |
| Metrics | [core-pillars/metrics.md](docs/core-pillars/metrics.md) |
| Health, and the observability port | [core-pillars/health.md](docs/core-pillars/health.md) |
| `ServiceApp` and the CLI | [api/cli.md](docs/api/cli.md) |
| Secrets backends | [api/secrets.md](docs/api/secrets.md) |
| Kafka | [transport/kafka.md](docs/transport/kafka.md) |
| Path resolution | [runtime/runtime-context.md](docs/runtime/runtime-context.md) |
| Deployment contract | [deployment/contract.md](docs/deployment/contract.md) |
| What wires itself | [auto-wiring.md](docs/auto-wiring.md) |
| Layering and the module graph | [architecture.md](docs/architecture.md) |

Two things worth reading before you deploy: `/livez` and `/readyz` are the whole
health surface and there are no aliases, and the observability port is separate
from your application's on purpose -- exposing user traffic must never expose the
operator surface. Both are in [health.md](docs/core-pillars/health.md).

## Development

```bash
make quality   # lint, type-check, security audit
make test      # run test suite
make build     # build wheel
```

## License

[Apache-2.0](LICENSE). Third-party attributions are recorded in [NOTICE](NOTICE).

## Related

- **[scalo-rs](https://github.com/hyperi-io/scalo-rs)** -- sister library for Rust
  services. Same opinions, same patterns, native Rust performance for hot-path
  workloads.
- **[Migrating from hyperi-pylib](docs/migrating-from-hyperi-pylib.md)** -- `scalo`
  is the renamed, Apache-2.0 continuation of `hyperi-pylib`; this guide covers the
  mechanical changes.

## Context

### What this is

HyperI's shared Python library -- config cascade, logging, metrics, health,
secrets, Kafka and the deployment-contract generators -- published as `scalo` on
PyPI under Apache-2.0.

It is scalo-rs's SISTER, not its twin: same conventions, DIFFERENT API, separate repo. Never assume parity. Where the two must agree, a shared corpus vendored from scalo-rs says so: credential masking is checked against `tests/fixtures/patterns/credential_masking_parity.json`, and the rules engine against `tests/fixtures/rules_corpus.json`.

### Where things live

| Path | What it holds |
|------|---------------|
| `src/scalo/<module>/` | One directory per module: `config`, `logger`, `metrics`, `health`, `http`, `kafka`, `secrets`, `deployment`, `cli` |
| `src/scalo/data/` | Vendored corpora and rule files, landed by `tools/vendor_patterns.sh` |
| `tests/{unit,integration,e2e,smoke}/` | Split by what each needs in order to run |
| `docs/architecture.md` | Layering, the module dependency graph, and what scalo-rs has that this does not |

### Commands that prove a change

```bash
make quality   # lint, type-check, security audit
make test      # the suite
make build     # the wheel
```

`addopts` deselects no markers, so `make test` runs integration and e2e as well,
and on a developer box that is not green. This run was 9 failed, 2552 passed, 31
skipped in 7m01s -- 6 GCP secrets tests wanting `gcloud auth
application-default login`, 2 CLI tests binding a fixed `0.0.0.0:9090`, and one
Dockerfile build. Read the per-job CI result, never a local summary. Coverage is
gated in `.hyperi-ci.yaml`.

### What tends to bite

| Don't | Do | Why |
|-------|----|-----|
| Read a skip as a pass | Make a guard fail when what it guards is absent | Both parity modules read fixtures from a `scalo-spec` checkout that never existed, so every case skipped everywhere including CI -- and the canary was itself `skipif(not path.exists())`, its skip condition being its own assertion negated. Tightening the import guards then caught `test_import_http` importing `create_client`, which does not exist (`2ca8329`) |
| Copy an API name or an env var out of the docs | Check the `control_var` call sites and the module | The docs named `for_pylib_extras` and `for_rustlib_features`, really `for_scalo_extras` and `for_scalo_features`, plus eight `HYPERI_*` variables removed with no fallback (`da005a0`) |
| Assume a config key you added is read | Follow it to its reader | `enable_sighup` was honoured only when `poll_interval > 0`, so "reload on SIGHUP, never poll" registered no handler. A duplicate `status` key in the OTel label map exported every HTTP metric as `task.status` (`6a2b21b`) |

### Where this sits

Generated from `dfe-infra/suite.yaml` via `dfe-stack suite`. Nothing in the suite
feeds this repo -- it declares no inbound edges.

| Repo | Kind | Mechanism, outbound |
|------|------|---------------------|
| dfe-engine | `python-dep`, potential | Declares `scalo` by range in `pyproject.toml`, no upper bound |
| dfe-engine | `contract-guard`, lockstep | It overrides our runtime base image with its own literal, and its own test fails when its committed Dockerfile stops matching. The validator is ours, `scalo.deployment.validate_dockerfile` |
| culvert | `python-dep`, potential | Declares `scalo` by range. A second range, for the deployment-contract generators, is dev-only |
| vector-vrl | `python-dep`, potential | Build system only, not the published wheel |

## Issues

Open bugs: [this repo](https://github.com/hyperi-io/scalo-py/issues?q=is%3Aopen+is%3Aissue+type%3ABug+-label%3Abacklog+-label%3Anext-minor) | [whole DFE suite](https://github.com/search?type=issues&q=is%3Aopen+is%3Aissue+type%3ABug+-label%3Abacklog+-label%3Anext-minor+repo%3Ahyperi-io%2Fdfe-infra+repo%3Ahyperi-io%2Fdfe-docker+repo%3Ahyperi-io%2Fdfe-deploy+repo%3Ahyperi-io%2Fdfe-engine+repo%3Ahyperi-io%2Fdfe-loader+repo%3Ahyperi-io%2Fdfe-receiver+repo%3Ahyperi-io%2Fdfe-fetcher+repo%3Ahyperi-io%2Fdfe-archiver+repo%3Ahyperi-io%2Fdfe-transform-vrl+repo%3Ahyperi-io%2Fdfe-transform-vector+repo%3Ahyperi-io%2Fdfe-transform-elastic+repo%3Ahyperi-io%2Fdfe-ui+repo%3Ahyperi-io%2Fdfe-hyperdx+repo%3Ahyperi-io%2Fscalo-rs+repo%3Ahyperi-io%2Fscalo-py+repo%3Ahyperi-io%2Flogreducer+repo%3Ahyperi-io%2Fdfe-schemas+repo%3Ahyperi-io%2Fvector-vrl+repo%3Ahyperi-io%2Fculvert+repo%3Ahyperi-io%2Fdfe-clickhouse-rs+repo%3Ahyperi-io%2Ffactbook-rs)
