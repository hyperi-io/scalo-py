# Artefact generators

Six generator entrypoints turn a `DeploymentContract` into the files
CI commits to the gitops repo. All output is f-string assembled (not
templated) so it stays byte-equivalent with rustlib's `format!()`
output across the two implementations.

```python
from scalo.deployment import (
    generate_dockerfile,
    generate_runtime_stage,
    generate_container_manifest,
    generate_compose_fragment,
    generate_chart,
    generate_argocd_application,
    generate_argocd_app_project,
    ArgocdConfig, AppProjectContract, AppProjectDestination,
    WAVE_APPS, WAVE_CRDS, WAVE_OPERATORS, WAVE_POST, WAVE_TOPICS,
)
```

Every generator that emits a Dockerfile, Chart.yaml, or Application CR
takes an opt-in `identity: ContractIdentity | None = None` kwarg --
see [IDENTITY.md](IDENTITY.md) for the wiring.

---

## At-a-glance

| Function | Output | Consumer | Identity-aware |
|---|---|---|---|
| `generate_dockerfile` | one-shot `Dockerfile` (string) | dev / local build | yes |
| `generate_runtime_stage` | runtime stage fragment (string) | CI multi-stage compose | yes |
| `generate_container_manifest` | manifest JSON (string) | hyperi-ci build planner | yes |
| `generate_compose_fragment` | `services:` block (string) | local `docker-compose.yml` | no |
| `generate_chart` | writes `Chart.yaml`, `values.yaml`, `templates/` | gitops repo | yes (on Chart.yaml) |
| `generate_argocd_application` | `Application` CR (string) | gitops repo | yes |
| `generate_argocd_app_project` | `AppProject` CR (string) | bootstrap repo | no |

---

## `generate_dockerfile`

One-shot Dockerfile for local development and standalone container
builds -- the convenience composition of `generate_builder_stage` +
`generate_runtime_stage`, so it is multi-stage. The build toolchain
stays in the builder and only the venv crosses into the runtime image.

The runtime portion carries the standard `LABEL io.hyperi.profile=...`,
the APT block (see [NATIVE-DEPS.md](NATIVE-DEPS.md)), an `appuser`
(uid 1000) created with `useradd` and then selected with `USER`,
`EXPOSE` for the metrics port plus every `extra_ports` entry, and an
inline `HEALTHCHECK` hitting `health.liveness_path` over `curl`.

`ENTRYPOINT` is `["<binary>"]`; `entrypoint_args` becomes the trailing
`CMD [...]` line when non-empty. Both are exec-form, so PID 1 receives
`SIGTERM`.

---

## `generate_builder_stage`

The reference uv builder, emitted as `FROM <builder_image> AS builder`.
It sets `UV_NO_BUILD=1` (never silently compile a dependency from
source) and `UV_COMPILE_BYTECODE=1` (pay for bytecode at build rather
than on first import), then installs in two phases:

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
RUN uv sync --frozen --no-dev
```

The split is what makes the dependency layer cache: with `COPY src/`
sitting before a single sync, any one-character source edit reinstalls
the entire dependency graph. It also sidesteps a real failure mode --
a single-phase sync breaks for any package whose metadata references
files outside the copied set (e.g. `project.license-files`).

It carries **no credentials**; apps with private indexes inject them
via `--build-arg` at `docker build` time.

---

## `generate_runtime_stage`

The runtime stage alone, as a multi-stage fragment starting with
`FROM <base_image> AS runtime`. This is the canonical artefact scalo-py
owns -- CI composes the full Dockerfile by prepending its own builder
stage that produces `/app/.venv`.

The fragment emits all four `org.opencontainers.image.*` static labels
and the four `ARG`-fed dynamic labels (`SOURCE`, `REVISION`, `VERSION`,
`CREATED`) that CI populates via `--build-arg`. It then copies the
uv-built virtualenv forward and puts it on `PATH`:

```dockerfile
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
```

The copy lands before `useradd`, so `/app` (and the venv in it) stays
root-owned and `appuser` gets read-only access. That is the right
default for a venv, but an app that expects to write under `/app`
needs a `--chown` or its own writable path.

A `HEALTHCHECK` is emitted by default. Kubernetes ignores it entirely
(it uses the pod spec's probes) but Compose honours it, so it is gated
on the contract rather than dropped: set `emit_healthcheck=False` for
an image that only ever runs in a cluster. `curl` stays in the image
either way -- it earns its place as a debug utility.

---

## `generate_dockerignore`

Writes a `.dockerignore` for the build context. Less critical here
than usual, because the builder uses explicit `COPY` paths rather than
`COPY . .`, so stray files cannot land in an image layer by accident.
It still matters for build time: the whole context is sent to the
daemon on every build, and a local `.venv` or `.git` dwarfs the handful
of files actually copied. It also excludes `.env` and key material, so
secrets are not shipped to the daemon at all.

---

## `generate_container_manifest`

A JSON document hyperi-ci reads to plan the build. It contains the
minimal subset of the contract CI needs -- no secrets, no K8s probes,
no `entrypoint_args` interpretation. Schema is its own (currently
string `"1"`), not the parent contract's `schema_version`.

Shape:

```json
{
  "schema_version": "1",
  "app_name": "...",
  "binary_name": "...",
  "base_image": "python:{python_version}-slim",
  "image_registry": "ghcr.io/hyperi-io",
  "image_profile": "production",
  "runtime_packages": { "apt_repos": [...], "apt_packages": [...] },
  "expose_ports": [9090, 8080],
  "healthcheck": { "path": "/livez", "port": 9090, "interval": "30s", ... },
  "entrypoint": ["..."],
  "cmd": [...],
  "user": "appuser",
  "uid": 1000,
  "labels": { "io.hyperi.profile": "...", "io.hyperi.app": "...", "org.opencontainers.image.*": "...", ... }
}
```

When `identity` is passed the three Contract Identity Annotation
Scheme v1 keys (`io.hyperi.contract.version`,
`.source-commit`, `.image-ref`) land in the `labels` dict.

---

## `generate_compose_fragment`

A `services:\n  <app_name>:\n ...` snippet suitable for inlining into
a local `docker-compose.yml`. Uses the image registry plus a
`${<ENV>_VERSION:-latest}` interpolation so devs can pin a specific
version with one env var. `depends_on` becomes
`condition: service_healthy` deps. The Compose healthcheck is tighter
than the Dockerfile's (10s interval, 5 retries) because compose
deps stack on it.

Compose-only; no identity labels (Compose has no equivalent annotation
surface for container provenance).

---

## `generate_chart`

Writes a complete Helm chart directory tree. Pass either a `Path` or a
string for `output_dir`:

```
<output_dir>/
  Chart.yaml
  values.yaml
  templates/
    _helpers.tpl
    deployment.yaml
    service.yaml
    serviceaccount.yaml
    configmap.yaml
    secret.yaml
    hpa.yaml
    keda-scaledobject.yaml         # when contract.keda is set
    keda-triggerauth.yaml          # when contract.keda is set
    NOTES.txt
```

Key behaviours:

- `Chart.yaml` carries identity annotations when `identity` is passed.
- `values.yaml` always emits a `prometheus.io/scrape` pod annotation
  pinned to `metrics_port` and `health.metrics_path`.
- `_helpers.tpl` adds a `<group>SecretName` helper per
  `SecretGroupContract` -- camel-cased via `to_camel_suffix` so
  `dlq-kafka` becomes `dlqKafkaSecretName`.
- `deployment.yaml` wires `livenessProbe`, `readinessProbe`, AND a
  `startupProbe`, all pointed at `health.liveness_path` over the
  `metrics` named port.
- `deployment.yaml` emits a pod-level and a container-level
  `securityContext`, both wired to values so an operator can tune (or
  empty the map to opt out). `values.yaml` ships the non-root floor on
  by default: `podSecurityContext` = `runAsNonRoot` / `runAsUser 1000` /
  `fsGroup 1000`, and `securityContext` = `allowPrivilegeEscalation:
  false` + `capabilities.drop: [ALL]`. A restricted-PodSecurity
  namespace rejects the pod without these. `readOnlyRootFilesystem` is
  deliberately NOT set -- a service that mints a key or writes a cache
  to the image rootfs needs a writable FS, so it is an opt-in once that
  state lives on a mount.
- `secret.yaml` is one `Secret` per group, gated by
  `{{- if not .Values.<group>.existingSecret }}` so users can BYO.
- `hpa.yaml` only renders when both `autoscaling.enabled` and NOT
  `keda.enabled`. KEDA wins when both are set.
- `default_config` (if set) is embedded under `config:` in
  `values.yaml` via lazy-imported `yaml.safe_dump`. If pyyaml is
  missing AND you have a `default_config`, generation raises
  `WriteFileError`.
- Errors mkdir/write through `CreateDirError` / `WriteFileError`.

---

## `generate_argocd_application` + `ArgocdConfig`

Emits an `argoproj.io/v1alpha1 Application` pointing at a Helm chart
in a git repo (typically the chart `generate_chart` just wrote).

```python
@dataclass
class ArgocdConfig:
    argocd_namespace: str = "argocd"
    dest_namespace: str = "dfe"
    dest_server: str = "https://kubernetes.default.svc"
    repo_url: str = ""         # required
    target_revision: str = "main"
    chart_path: str = "chart"
    project: str = "default"
    sync_wave: int = WAVE_APPS
    extra_ignore_differences: list[str] = field(default_factory=list)
```

The generated CR carries `metadata.annotations.argocd.argoproj.io/sync-wave`
set from `ArgocdConfig.sync_wave`; identity annotations land in the
same block when passed.

`syncPolicy.automated` defaults: `prune=true`, `selfHeal=true`,
`allowEmpty=false`. Sync options include `CreateNamespace=true` and
`ServerSideApply=true`. Retry is 5x with 5s -> 3m backoff.

Canonical `ignoreDifferences` (always emitted):

- `apps/Deployment` -> `/spec/replicas` (HPA / KEDA mutates)
- `""/Service` -> `/spec/clusterIP`, `/spec/clusterIPs` (cluster-assigned)
- `admissionregistration.k8s.io/ValidatingWebhookConfiguration` ->
  `.webhooks[].clientConfig.caBundle` (cert-manager injects)

`extra_ignore_differences` is the consumer extension point: each entry
is a raw YAML fragment matching the ArgoCD shape, with two-space
internal indentation. The generator indents your entries by four
spaces so they land directly under `ignoreDifferences:`.

---

## `AppProjectContract` + `generate_argocd_app_project`

A separate generator for the per-team `AppProject` CR. Each consumer
Application references the project via its `spec.project` field; the
project restricts which `sourceRepos`, `destinations`, and resource
kinds the project may use.

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

`AppProjectDestination(server, namespace)`. Resource entries are
`"<group>:<kind>"` (e.g. `"kafka.strimzi.io:KafkaTopic"`); `"*:*"`
means unrestricted (avoid in enterprise). Generated YAML is plain
string assembly -- no identity stamp (the project predates individual
contract instances).

---

## Sync-wave constants

Lower wave runs first. Values are gaps wide enough for in-band custom
waves; pick a canonical band where possible.

| Constant | Value | Use for |
|---|---|---|
| `WAVE_OPERATORS` | `-20` | Operators (Strimzi, ESO) whose CRDs others need |
| `WAVE_CRDS` | `-10` | Standalone CRDs that aren't operator-shipped |
| `WAVE_TOPICS` | `-5` | KafkaTopic, KafkaUser, cross-app topology |
| `WAVE_APPS` | `0` | DFE apps -- the default |
| `WAVE_POST` | `10` | Smoke tests, webhook registrations, alerts |

Values mirror rustlib's `hyperi_rustlib::deployment::waves` numerically.

---

## Identity opt-in (Phase 1)

The generators that take `identity` default it to `None` so
existing CI doesn't break on upgrade. Pass an explicit
`ContractIdentity.detect(image_ref=...)` (or constructed instance) to
stamp the three `io.hyperi.contract.*` keys. Phase 2 will require
identity at the call sites; Phase 3 drops the wrapper entirely. See
[IDENTITY.md](IDENTITY.md).

---

## Errors

All file-writing generators raise specific subclasses of
`DeploymentError`:

- `CreateDirError(path, OSError)` -- mkdir failed
- `WriteFileError(path, OSError)` -- write failed
- `ContractMismatch` -- validation comparison failure (validation
  helpers, not the generators here)
- `ParseYamlError`, `ReadFileError`, `NotFoundError` -- consumer-side
  loader errors

Catch `DeploymentError` for the broad case; subclasses are exposed for
fine-grained handling.

---

## Related

- [CONTRACT.md](CONTRACT.md)
- [IDENTITY.md](IDENTITY.md)
- [NATIVE-DEPS.md](NATIVE-DEPS.md)
- [KEDA.md](KEDA.md)
- [TEST-SUPPORT.md](TEST-SUPPORT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
