# Artefact generators

These generators turn a `DeploymentContract` into the files CI builds and ships the image from. All output is f-string assembled, not templated. The identity labels match scalo-rs's byte for byte, which `tests/fixtures/contract-parity/v1-output.txt` pins, while the Dockerfiles differ because each library builds its own language.

```python
from scalo.deployment import (
    generate_dockerfile,
    generate_builder_stage,
    generate_runtime_stage,
    generate_dockerignore,
    generate_container_manifest,
    generate_compose_fragment,
    generate_argocd_app_project,
    AppProjectContract, AppProjectDestination,
    WAVE_APPS, WAVE_CRDS, WAVE_OPERATORS, WAVE_POST, WAVE_TOPICS,
)
```

scalo-py writes no Helm chart. The Kubernetes objects come from the
scalo-service library chart -- see [Kubernetes objects](#kubernetes-objects).

Every generator that emits a Dockerfile or the container manifest takes an opt-in `identity: ContractIdentity | None = None` keyword argument. See [identity.md](identity.md) for the wiring.

---

## At-a-glance

| Function | Output | Consumer | Identity-aware |
|---|---|---|---|
| `generate_dockerfile` | one-shot `Dockerfile` (string) | dev / local build | yes |
| `generate_builder_stage` | uv builder stage (string) | CI multi-stage compose | no |
| `generate_runtime_stage` | runtime stage fragment (string) | CI multi-stage compose | yes |
| `generate_dockerignore` | `.dockerignore` (string) | docker build context | no |
| `generate_container_manifest` | manifest JSON (string) | hyperi-ci build planner | yes |
| `generate_compose_fragment` | `services:` block (string) | local `docker-compose.yml` | no |
| `generate_argocd_app_project` | `AppProject` CR (string) | bootstrap repo | no |

---

## `generate_dockerfile`

One-shot Dockerfile for local development and standalone container
builds -- the convenience composition of `generate_builder_stage` +
`generate_runtime_stage`, so it is multi-stage. The build toolchain
stays in the builder and only the venv crosses into the runtime image.

A `# License` and a `# Copyright` header line appear only when `oci_labels.licenses` and `oci_labels.copyright` are set.

The runtime portion carries the standard `LABEL io.scalo.profile=...` (under `oci_labels.label_namespace`), the APT block (see [native-deps.md](native-deps.md)), an `appuser` (uid 1000) created with `useradd` and then selected with `USER 1000`, `EXPOSE` for the metrics port plus every `extra_ports` entry, and, unless `emit_healthcheck` is off, an inline `HEALTHCHECK` hitting `health.liveness_path` over `curl`.

`ENTRYPOINT` is `["<binary>"]`, and `entrypoint_args` becomes the trailing `CMD [...]` line when non-empty. Both are exec-form, so PID 1 receives `SIGTERM`.

---

## `generate_builder_stage`

The reference uv builder, emitted as `FROM <builder_image> AS builder`. It sets `UV_COMPILE_BYTECODE=1` for the stage (pay for bytecode at build rather than on first import), then installs in two phases, with `UV_NO_BUILD=1` on the dependency phase only, so no dependency is silently compiled from source while the project itself still installs:

```dockerfile
COPY pyproject.toml uv.lock ./
RUN UV_NO_BUILD=1 uv sync --frozen --no-dev --no-install-project
COPY src/ src/
RUN uv sync --frozen --no-dev
```

The split makes the dependency layer cache: with `COPY src/` before a single sync, any one-character source edit reinstalls the entire dependency graph. A single-phase sync also breaks for any package whose metadata references files outside the copied set (e.g. `project.license-files`).

It carries **no credentials**. Apps with private indexes inject them via `--build-arg` at `docker build` time.

---

## `generate_runtime_stage`

The runtime stage alone, as a multi-stage fragment starting with `FROM <base_image> AS runtime`. This is the artefact CI uses (`Dockerfile.runtime`): CI composes the full Dockerfile by prepending its own builder stage that produces `/app/.venv`.

The fragment emits the `org.opencontainers.image.*` static labels (`vendor` and `licenses` only when the contract sets them) and the four `ARG`-fed dynamic labels (`SOURCE`, `REVISION`, `VERSION`, `CREATED`) that CI populates via `--build-arg`. It then copies the uv-built virtualenv forward and puts it on `PATH`:

```dockerfile
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
```

The copy lands before `useradd`, so `/app` (and the venv in it) stays root-owned and `appuser` gets read-only access. An app that expects to write under `/app` needs a `--chown` or its own writable path.

A `HEALTHCHECK` is emitted by default. Kubernetes ignores it (it uses the pod spec's probes) but Compose honours it, so set `emit_healthcheck=False` for an image that only ever runs in a cluster. `curl` stays in the image either way, as a debug utility.

---

## `generate_dockerignore`

Writes a `.dockerignore` for the build context. The builder copies explicit paths rather than `COPY . .`, so stray files cannot land in an image layer. The file still matters for build time, because the whole context is sent to the daemon on every build and a local `.venv` or `.git` dwarfs the files copied. It also excludes `.env`, `.env.*` (but `.env.sample`), `*.pem` and `*.key`, so secrets never reach the daemon.

---

## `generate_container_manifest`

A JSON document hyperi-ci reads to plan the build. It holds the subset of the contract CI needs: no secrets, no K8s probes. Its schema version is its own, not the parent contract's `schema_version`. The keys:

```json
{
  "schema_version": "1",
  "app_name": "...",
  "binary_name": "...",
  "base_image": "python:{python_version}-slim",
  "image_registry": "registry.example.com/team",
  "image_profile": "production",
  "runtime_packages": { "apt_repos": [...], "apt_packages": [...] },
  "expose_ports": [9090, 8080],
  "healthcheck": { "path": "/livez", "port": 9090, "interval": "30s", ... },
  "entrypoint": ["..."],
  "cmd": [...],
  "user": "appuser",
  "uid": 1000,
  "labels": { "io.scalo.profile": "...", "io.scalo.app": "...", "io.scalo.metrics_port": "...", "org.opencontainers.image.*": "...", ... }
}
```

The `io.scalo.*` keys follow `oci_labels.label_namespace`, and the `vendor` and `licenses` labels appear only when the contract sets them. When `identity` is passed the three Contract Identity Annotation Scheme v1 keys (`io.scalo.contract.version`, `.source-commit`, `.image-ref`) land in the `labels` dict.

---

## `generate_compose_fragment`

A `services:\n  <app_name>:\n ...` snippet suitable for inlining into a local `docker-compose.yml`. It uses the image registry plus a `${<ENV>_VERSION:-latest}` interpolation so a developer pins a version with one env var. `depends_on` becomes `condition: service_healthy` deps. The Compose healthcheck is tighter than the Dockerfile's (10s interval, 5 retries) because compose deps wait on it.

It carries no identity labels.

---

## Kubernetes objects

The [scalo-service](https://github.com/hyperi-io/scalo-rs/blob/main/charts/scalo-service/README.md)
library chart in scalo-rs renders them from `deployment-contract.json`:
the Deployment, Services, ConfigMaps, ServiceAccount, claims, disruption
budget, KEDA ScaledObject and TriggerAuthentication, fallback HPA and
NetworkPolicy. Its README lists what each contract field and value
renders, and how to assemble the thin chart a service ships.

`generate-artefacts` writes the contract (see [../api/cli.md](../api/cli.md)), and a chart assembler turns it into that thin chart. To preview a service's chart locally, run `hyperi-ci chart assemble --image <repo>:<tag>@sha256:<digest>`, then `helm dependency build` and `helm template` on the directory it prints.

---

## `AppProjectContract` + `generate_argocd_app_project`

A separate generator for the per-team `AppProject` CR. Each consumer Application references the project in its `spec.project` field, and the project restricts which `sourceRepos`, `destinations` and resource kinds it may use.

```python
@dataclass
class AppProjectContract:
    name: str = ""
    argocd_namespace: str = "argocd"
    description: str = ""
    source_repos: list[str] = ["*"]
    destinations: list[AppProjectDestination] = [<default svc>/*]
    cluster_resource_allow: list[str] = ["*:*"]
    namespace_resource_allow: list[str] = ["*:*"]
```

`AppProjectDestination(server, namespace)`. Resource entries are `"<group>:<kind>"` (e.g. `"kafka.strimzi.io:KafkaTopic"`), and `"*:*"` means unrestricted. The YAML carries no identity stamp, because a project is not one contract's artefact.

---

## Sync-wave constants

Lower wave runs first. The gaps leave room for custom waves between the bands.

| Constant | Value | Use for |
|---|---|---|
| `WAVE_OPERATORS` | `-20` | Operators (Strimzi, ESO) whose CRDs others need |
| `WAVE_CRDS` | `-10` | Standalone CRDs that aren't operator-shipped |
| `WAVE_TOPICS` | `-5` | KafkaTopic, KafkaUser, cross-app topology |
| `WAVE_APPS` | `0` | Application services -- the default |
| `WAVE_POST` | `10` | Smoke tests, webhook registrations, alerts |

Values mirror scalo-rs's `scalo::deployment::waves` numerically.

---

## Identity opt-in

The generators that take `identity` default it to `None`. Pass `ContractIdentity.detect(image_ref=...)`, or a constructed instance, to stamp the three `io.scalo.contract.*` keys. See [identity.md](identity.md).

---

## Errors

The generators here return strings, so none of them raises a file error. The deployment error types mirror scalo-rs's `DeploymentError`, and all subclass `DeploymentError`:

- `CreateDirError(path, OSError)`, `WriteFileError(path, OSError)`, `ReadFileError(path, OSError)`, `NotFoundError(path)` -- for code that writes or reads artefact files
- `IdentityError` -- a `ContractIdentity` field failed validation

`ContractMismatch` is not an exception: it is one drift finding in the
list `validate_dockerfile` returns.

Catch `DeploymentError` for the broad case, or a subclass for one failure.

---

## Related

- [contract.md](contract.md)
- [identity.md](identity.md)
- [native-deps.md](native-deps.md)
- [keda.md](keda.md)
- [test-support.md](test-support.md)
- [../integration.md](../integration.md)
