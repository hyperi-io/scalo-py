# scalo

<!-- BADGES:START -->
<!-- Build Status badge omitted: the repo is private, so GitHub's Actions
     badge SVG 404s for anonymous PyPI viewers (shields.io can't read a
     private repo's status either). Re-add at the public-visibility flip:
     [![Build Status](https://github.com/hyperi-io/scalo-py/actions/workflows/ci.yml/badge.svg)](https://github.com/hyperi-io/scalo-py/actions) -->

| | |
| --- | --- |
| Package | [![PyPI](https://img.shields.io/pypi/v/scalo?logo=pypi)](https://pypi.org/project/scalo/) [![Python Version](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/) |
| Meta | [![License](https://img.shields.io/badge/license-Apache--2.0-green)](https://www.apache.org/licenses/LICENSE-2.0) |
<!-- BADGES:END -->

An integrated runtime for control-plane services. Attach and 'enterprise-up' your application.

## Key features

- configuration cascade for local test through at scale k8s deployments (env, config, cli)
- automatically configured and integrated logger (line and json) for enterprise deployments
- auto enabled Otel and Prometheus metrics in expected forms and buckets for cloud and k8s deployments
- secrets management integration
- authentication and secrets integration for most common deployments and services
- deployment contracts, your code automatically generates docker, and k8s artefacts for deployment consumption

## Install

```bash
uv add scalo                                    # core
uv add "scalo[http,metrics,kafka]"              # common extras
uv add "scalo[http,metrics,expression,kafka,opentelemetry,secrets,deployment]"
```

`scalo` on PyPI, `scalo` for imports. Extras and their install sizes are in
[docs/EXTRAS-FLAGS.md](docs/EXTRAS-FLAGS.md) -- `secrets-aws` alone is ~100 MB, so
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
| `logger` | Structured JSON logging, PII masked, secrets filtered, container-aware | loguru |
| `config` | 7-layer cascade (CLI -> ENV -> .env -> YAML -> defaults) | dynaconf, pyyaml, python-dotenv, mergedeep, tomli-w, dulwich |
| `runtime` | Detects K8s / Docker / local, resolves config and data paths | stdlib only |
| `cli` | `ServiceApp` -- subclass for `run` / `version` / `config-check` | typer |
| `version-check` | Optional startup check for a newer release | httpx (lazy) |

By extra: `http` (retry with jitter), `metrics` (Prometheus + process and container
gauges), `expression` (CEL), `kafka` (produce, consume, schema inference),
`opentelemetry` (OTLP traces and metrics), `secrets` (OpenBao/Vault, AWS, GCP,
Azure), `deployment` (Dockerfile, Helm, Argo, compose generators).

Wired together already, which is the part you would otherwise build: config,
logging and metrics are global singletons with no init dance; the cascade feeds the
CLI so `run`, `version` and `config-check` work without you parsing an argument;
the metrics and health wiring feeds the Kubernetes probes; the deployment contract
writes your chart, Dockerfile and Argo manifests from the config the app already
declares.

## Documentation

[docs/README.md](docs/README.md) is the index. The ones you want first:

| Topic | Doc |
|---|---|
| Config cascade | [core-pillars/CONFIG.md](docs/core-pillars/CONFIG.md) |
| Logging and PII scrubbing | [core-pillars/LOGGING.md](docs/core-pillars/LOGGING.md) |
| Metrics | [core-pillars/METRICS.md](docs/core-pillars/METRICS.md) |
| Health, and the observability port | [core-pillars/HEALTH.md](docs/core-pillars/HEALTH.md) |
| `ServiceApp` and the CLI | [api/CLI.md](docs/api/CLI.md) |
| Secrets backends | [api/SECRETS.md](docs/api/SECRETS.md) |
| Kafka | [transport/KAFKA.md](docs/transport/KAFKA.md) |
| Path resolution | [runtime/RUNTIME-CONTEXT.md](docs/runtime/RUNTIME-CONTEXT.md) |
| Deployment contract | [deployment/CONTRACT.md](docs/deployment/CONTRACT.md) |
| What wires itself | [AUTO-WIRING.md](docs/AUTO-WIRING.md) |
| Layering and the module graph | [architecture.md](docs/architecture.md) |

Two things worth reading before you deploy: `/livez` and `/readyz` are the whole
health surface and there are no aliases, and the observability port is separate
from your application's on purpose -- exposing user traffic must never expose the
operator surface. Both are in [HEALTH.md](docs/core-pillars/HEALTH.md).

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
- **[Migrating from hyperi-pylib](docs/MIGRATING-FROM-HYPERI-PYLIB.md)** -- `scalo`
  is the renamed, Apache-2.0 continuation of `hyperi-pylib`; this guide covers the
  mechanical changes.

## Context

### What this is

HyperI's shared Python library -- config cascade, logging, metrics, health,
secrets, Kafka and the deployment-contract generators -- published as `scalo` on
PyPI under Apache-2.0.

It is scalo-rs's SISTER, not its twin: same conventions, DIFFERENT API, separate
repo. Never assume parity. The divergence is recorded rather than theoretical --
`src/scalo/data/masking-patterns.yaml` names the sensitive fields each side knows
and the other does not, and the two match differently, so the corpus holds only
cases inside the overlap.

### Where things live

| Path | What it holds |
|------|---------------|
| `src/scalo/<module>/` | One directory per module: `config`, `logger`, `metrics`, `health`, `http`, `kafka`, `secrets`, `deployment`, `cli` |
| `src/scalo/data/` | Vendored corpora and rule files, landed by `tools/vendor_patterns.sh` |
| `templates/helm/scalo-app/` | The chart the deployment generators render against |
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
