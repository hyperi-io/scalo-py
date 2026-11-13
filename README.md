# scalo

<!-- BADGES:START -->
| | |
| --- | --- |
| Build | [![Build Status](https://github.com/hyperi-io/scalo-py/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/scalo-py/actions) |
| Package | [![PyPI](https://img.shields.io/pypi/v/scalo?logo=pypi)](https://pypi.org/project/scalo/) [![Python Version](https://img.shields.io/python/required-version-toml?tomlFilePath=https://raw.githubusercontent.com/hyperi-io/scalo-py/main/pyproject.toml)](pyproject.toml) |
| Meta | [![License](https://img.shields.io/badge/license-Apache--2.0-green)](https://www.apache.org/licenses/LICENSE-2.0) |
<!-- BADGES:END -->

The runtime layer for Python control-plane services: config, logging, metrics, health probes, secrets and a service CLI, already wired together. In a DFE deployment dfe-engine is built on it, with the same config and logging conventions scalo-rs gives the Rust services.

## What it gives you

- A seven-layer config cascade, from CLI flags and env vars down to YAML and defaults, that reads the same in a laptop shell and a Kubernetes pod.
- Structured logs, JSON in a container and readable text at a terminal, with secrets, credential fields and validated PII values redacted at every level but TRACE, which the scrubber skips by default.
- `ServiceApp`: subclass it and get `run`, `version`, `config-check` and `generate-artefacts`, with config and logging started for you.
- `/livez` and `/readyz` on an observability port kept apart from your application's own.
- Prometheus and OpenTelemetry metrics with the `metrics` extra, scraped from `/metrics` on the same port. Without a metrics manager that path answers 404.
- Secrets from OpenBao or Vault, AWS, GCP, Azure, and Kubernetes, one extra per backend.
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
scalo-py is fast enough for control plane and integration, and scalo-rs is fast enough
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
CLI so `run`, `version` and `config-check` work without you parsing an argument.
The metrics and health wiring feeds the Kubernetes probes. The deployment contract,
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

## Related

- **[scalo-rs](https://github.com/hyperi-io/scalo-rs)** -- sister library for Rust
  services. Same opinions, same patterns, native Rust performance for hot-path
  workloads.
- **[Migrating from hyperi-pylib](docs/migrating-from-hyperi-pylib.md)** -- `scalo`
  is the renamed, Apache-2.0 continuation of `hyperi-pylib`, and this guide covers the
  mechanical changes.

## Help and contributing

How to work in this repo, the commands that prove a change and what tends to bite are in [CONTRIBUTING.md](CONTRIBUTING.md). A question that is not a bug goes in a new issue.

Open bugs: [this repo](https://github.com/hyperi-io/scalo-py/issues?q=is%3Aopen+is%3Aissue+type%3ABug+-label%3Abacklog+-label%3Anext-minor) | [whole DFE suite](https://github.com/search?type=issues&q=is%3Aopen+is%3Aissue+type%3ABug+-label%3Abacklog+-label%3Anext-minor+repo%3Ahyperi-io%2Fdfe-infra+repo%3Ahyperi-io%2Fdfe-docker+repo%3Ahyperi-io%2Fdfe-deploy+repo%3Ahyperi-io%2Fdfe-engine+repo%3Ahyperi-io%2Fdfe-loader+repo%3Ahyperi-io%2Fdfe-receiver+repo%3Ahyperi-io%2Fdfe-fetcher+repo%3Ahyperi-io%2Fdfe-archiver+repo%3Ahyperi-io%2Fdfe-transform-vrl+repo%3Ahyperi-io%2Fdfe-transform-vector+repo%3Ahyperi-io%2Fdfe-transform-elastic+repo%3Ahyperi-io%2Fdfe-ui+repo%3Ahyperi-io%2Fdfe-hyperdx+repo%3Ahyperi-io%2Fscalo-rs+repo%3Ahyperi-io%2Fscalo-py+repo%3Ahyperi-io%2Flogreducer+repo%3Ahyperi-io%2Fdfe-schemas+repo%3Ahyperi-io%2Fvector-vrl+repo%3Ahyperi-io%2Fculvert+repo%3Ahyperi-io%2Fdfe-clickhouse-rs+repo%3Ahyperi-io%2Ffactbook-rs)

## License

[Apache-2.0](LICENSE). Third-party attributions are recorded in [NOTICE](NOTICE).
