# scalo

The runtime layer for Python control-plane services: config, logging, metrics, health probes, secrets and a service CLI, already wired together. Subclass one class and your service reads its config, logs in the right format for where it runs, and serves its health probes.

It is built for APIs, orchestrators, CLI tools and integration glue. For the hot path there is a Rust sister library, [scalo-rs](https://github.com/hyperi-io/scalo-rs), with the same conventions and a different API.

## What it gives you

- A seven-layer config cascade, from CLI flags and env vars down to YAML and defaults, that reads the same in a laptop shell and a Kubernetes pod.
- Structured logs, JSON in a container and readable text at a terminal. Credentials, tokens and keys are masked, and so are cards, IBANs, emails, phone numbers and Australian ABN, ACN, TFN and Medicare numbers.
- `ServiceApp`: subclass it and get `run`, `version`, `config-check` and `generate-artefacts`, with config and logging started for you, and metrics too once `scalo[metrics]` is installed.
- `/metrics`, `/livez` and `/readyz` on an observability port kept apart from your application's own.
- With the `metrics` extra, Prometheus and OpenTelemetry metrics, process and container gauges included.
- Secrets from OpenBao or Vault, AWS, GCP, Azure, Kubernetes and Ansible Vault, one extra per backend.
- A deployment contract: return one from `deployment_contract()` and `generate-artefacts` writes your runtime Dockerfile and the contract the scalo-service Helm chart renders from.
- Kafka, CEL expressions and an HTTP client with jittered retry, each behind its own extra.

## Example

```console
uv add scalo
```

```python
from scalo.cli import ServiceApp, VersionInfo
from scalo.logger import logger


class Greeter(ServiceApp):
    name = "greeter"
    env_prefix = "GREETER"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    def run_service(self, config) -> None:
        logger.info("hello", target=config.get("target", "world"))


if __name__ == "__main__":
    Greeter().cli()
```

`GREETER_TARGET=team python greeter.py run` logs `hello` with `target=team`, and `python greeter.py config-check` validates the config without starting anything.

## Extras

| Extra | Adds |
|---|---|
| `api` | FastAPI conventions: operation ids, ETag and If-Match, problem+json errors, pagination |
| `cli` | A whole CLI generated from an OpenAPI spec |
| `mcp` | MCP tools generated from a `scalo.api` app's spec, served on the same app |
| `http` | An httpx client with jittered retry |
| `metrics` | Prometheus and OTLP export, process and container gauges |
| `opentelemetry` | The OpenTelemetry half of `metrics` on its own |
| `expression` | CEL expressions |
| `kafka` | Produce, consume and schema inference |
| `deployment` | The deployment contract and its Dockerfile and manifest generators |
| `secrets-vault`, `secrets-aws`, `secrets-gcp`, `secrets-azure`, `secrets-kubernetes`, `secrets-ansible-vault` | One secrets backend each |
| `secrets` | Every secrets backend |

Pick the secrets backend you use rather than `secrets`, since each backend brings its own cloud SDK.

Docs and source are at <https://github.com/hyperi-io/scalo-py>. Requires Python 3.14 or later. Licensed Apache-2.0: <https://github.com/hyperi-io/scalo-py/blob/main/LICENSE>.
