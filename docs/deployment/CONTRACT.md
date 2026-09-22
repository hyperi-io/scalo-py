# DeploymentContract

The Pydantic model an app builds once from its `Config.default()`. CI
validates Helm charts and Dockerfiles against the contract; generators
emit deployment artefacts from it. Field shape mirrors
`scalo::deployment::contract` exactly -- the JSON form
round-trips between the two implementations.

Import surface (gated on the `[deployment]` extra; importing without
`pydantic>=2.13` defers and raises `ProviderNotAvailableError`):

```python
from scalo.deployment import (
    DeploymentContract, HealthContract, OciLabels,
    PortContract, SecretGroupContract, SecretEnvContract,
    ImageProfile,
)
```

---

## Top-level fields

| Field | Type | Default | Purpose |
|---|---|---|---|
| `schema_version` | `int` | `2` (`DEFAULT_SCHEMA_VERSION`) | CI rejects above `MAX_SUPPORTED_SCHEMA_VERSION` |
| `app_name` | `str` | required | Matches `Chart.yaml` `name`; image repo segment |
| `binary_name` | `str` | `""` -> falls back to `app_name` via `.binary()` |
| `description` | `str` | `""` | Chart description |
| `metrics_port` | `int` (1..65535) | required | Metrics + health listen port |
| `health` | `HealthContract` | factory | Probe paths -- see below |
| `env_prefix` | `str` | required | Dynaconf prefix; `__` is the nesting separator |
| `metric_prefix` | `str` | required | Prometheus namespace |
| `config_mount_path` | `str` | required | E.g. `/etc/event-loader/config.yaml` |
| `image_registry` | `str` | `ghcr.io/hyperi-io` | Container registry base |
| `extra_ports` | `list[PortContract]` | `[]` | HTTP / gRPC / data ports beyond metrics |
| `entrypoint_args` | `list[str]` | `[]` | Default `CMD` args |
| `secrets` | `list[SecretGroupContract]` | `[]` | K8s secret groups |
| `default_config` | `Any \| None` | `None` | Embedded `values.yaml` `config:` block |
| `depends_on` | `list[str]` | `[]` | Compose-only service deps |
| `keda` | `KedaContract \| None` | `None` | See [KEDA.md](KEDA.md) |
| `base_image` | `str` | `""` -> `python:{python_version}-slim` | Runtime base for Dockerfile; read via `effective_base_image()` |
| `builder_image` | `str` | `""` -> uv image for `python_version` | Builder stage; read via `effective_builder_image()` |
| `python_version` | `str` | `3.14` | Drives BOTH default images |
| `native_deps` | `NativeDepsContract` | factory | See [NATIVE-DEPS.md](NATIVE-DEPS.md) |
| `image_profile` | `ImageProfile` | `PRODUCTION` | See below |
| `oci_labels` | `OciLabels` | factory | Static OCI labels |

`base_image` and `builder_image` both default to empty and resolve
through their accessors, so `python_version` is the single knob: bump it
and both images move together. Set either field to override (a digest
pin belongs here).

The two ends sit on different Debian releases deliberately. The runtime
is `python:{python_version}-slim` (Debian 13 trixie); the builder is
held on `-bookworm-slim` (Debian 12). The rule is
`glibc(runtime) >= glibc(build)` -- a binary built against older glibc
runs on newer, never the reverse. If that ever inverts, the failure is
`version 'GLIBC_x.yz' not found` at container exec, in the target
environment rather than at build time.

### Pin a digest for anything you ship

Bare tags are fine while iterating. Anything shipped should pin a
digest, because a tag is a moving pointer -- `python:3.14-slim` is
rebuilt regularly, so the "same" contract can produce a different image
tomorrow, and a build you cannot reproduce is a build you cannot
bisect.

Both fields take a digest-suffixed reference:

```python
DeploymentContract(
    ...,
    base_image="python:3.14-slim@sha256:<digest>",
    builder_image="ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:<digest>",
)
```

Renovate updates digest pins the same way it updates versions, so this
costs nothing ongoing. Note that pinning `base_image` opts out of the
`python_version` derivation -- pin both ends or neither, or a
`python_version` bump will move only the unpinned one.

`model_config = ConfigDict(extra="forbid")` on every nested model --
typos fail at construction, not at deploy.

---

## `ImageProfile`

`StrEnum` with two members. Both profiles share the same dynamic
linking strategy; the difference is debug tooling and tag suffix.

| Profile | Tag suffix | Adds these APT packages |
|---|---|---|
| `PRODUCTION` | none -- `:1.15.0`, `:latest` | none beyond base |
| `DEVELOPMENT` | `-dev` -- `:1.15.0-dev`, `:latest-dev` | `bash strace tcpdump procps dnsutils net-tools less jq` |

`with_dev_profile()` returns a deep-copied clone flipped to
`DEVELOPMENT`. Use it in CI matrix expansions to emit both image
variants from one contract.

---

## `OciLabels`

| Field | Default | Notes |
|---|---|---|
| `title` | `""` -> falls back to `app_name` in generators |
| `description` | `""` |
| `vendor` | `"HYPERI PTY LIMITED"` (`DEFAULT_VENDOR`) |
| `licenses` | `"Apache-2.0"` (`DEFAULT_LICENSE`) |

Dynamic labels (`org.opencontainers.image.source`, `revision`,
`version`, `created`) are CI-injected via `--build-arg`; the static
labels listed here come from the contract.

---

## `HealthContract`

| Field | Default | Purpose |
|---|---|---|
| `liveness_path` | `/livez` | Used by Dockerfile `HEALTHCHECK` and Helm `livenessProbe` |
| `readiness_path` | `/readyz` | Helm `readinessProbe` |
| `metrics_path` | `/metrics` | Prometheus scrape annotation in `values.yaml` |

The Helm `startupProbe` also points at `liveness_path`. There is no separate
startup field and no `/startupz`: Kubernetes suspends liveness until the
startup probe passes, so one path gives both a generous boot budget and a
tight liveness period without the two drifting apart.

These three paths are the whole surface. There are no aliases -- a retired
path returns 404, deliberately, because an alias that keeps answering 200
hides a probe still aimed at the old name.

---

## `PortContract` / `SecretGroupContract` / `SecretEnvContract`

`PortContract` -- additional container port beyond `metrics_port`.
`name` (e.g. `http`), `port` (1..65535), `protocol` (default `TCP`).
Generators emit one `containerPort` per entry plus a matching Service
`port` entry.

`SecretEnvContract` -- one env var fed from a K8s Secret:

- `env_var` -- full env-var name (e.g. `EVENT_LOADER__KAFKA__PASSWORD`)
- `key_name` -- key in `values.yaml` `secretKeys`
- `secret_key` -- default K8s Secret key (e.g. `kafka-password`)

`SecretGroupContract` -- a group of secrets from the same K8s Secret.
`group_name` becomes the `values.yaml` section name and the
`{group}SecretName` helper. Generators emit one `Secret` template per
group plus a KEDA `TriggerAuthentication` automatically when the group
is named `kafka`.

---

## Convenience accessors

- `binary()` -- effective binary name (`binary_name` or `app_name`).
- `config_filename()` -- basename of `config_mount_path`
  (e.g. `loader.yaml`).
- `config_dir()` -- parent directory (e.g. `/etc/event-loader`). Used for the
  K8s `volumeMounts.mountPath`.
- `to_json()` -- pretty-printed JSON; the wire format for
  `--emit-contract` CLI commands.
- `from_json(raw)` -- inverse. Round-trips losslessly.
- `with_dev_profile()` -- deep-copied clone with development profile.

---

## Schema versioning

```python
DEFAULT_SCHEMA_VERSION = 2
MAX_SUPPORTED_SCHEMA_VERSION = 2
```

Bumping the schema is a coordinated scalo-rs + scalo-py change. CI parses
`schema_version` first and fails fast when a consumer writes a contract
above the version scalo-py supports -- forward-compat is intentional and
only one step deep. When you add a field, bump
`MAX_SUPPORTED_SCHEMA_VERSION` on both sides AND mirror the field in
scalo-rs in the same change set.

---

## Round-trip

```python
contract = DeploymentContract(
    app_name="event-loader",
    metrics_port=9090,
    env_prefix="EVENT_LOADER",
    metric_prefix="loader",
    config_mount_path="/etc/event-loader/config.yaml",
)
raw = contract.to_json()
restored = DeploymentContract.from_json(raw)
assert restored == contract
```

`exclude_none=False` so a parsed contract round-trips byte-equal to the
emitted JSON. CI uses this to diff a freshly emitted contract against
the one committed in the repo.

---

## Building a contract from your `Config`

The opinionated path: have your app's `Config.default()` build a
`DeploymentContract` rather than building artefacts ad-hoc. CI invokes
`<your-binary> emit-contract` to produce the JSON, then feeds that into
the generators in this package -- so the same defaults flow into both
the running app and the deployment artefacts.

```python
def deployment_contract(cfg: AppConfig) -> DeploymentContract:
    return DeploymentContract(
        app_name="event-loader",
        metrics_port=cfg.metrics.port,
        env_prefix="EVENT_LOADER",
        metric_prefix="loader",
        config_mount_path=cfg.config_path,
        secrets=[
            SecretGroupContract(
                group_name="kafka",
                env_vars=[
                    SecretEnvContract(
                        env_var="EVENT_LOADER__KAFKA__USERNAME",
                        key_name="username",
                        secret_key="kafka-username",
                    ),
                    SecretEnvContract(
                        env_var="EVENT_LOADER__KAFKA__PASSWORD",
                        key_name="password",
                        secret_key="kafka-password",
                    ),
                ],
            ),
        ],
        keda=KedaContract.from_config(cfg.keda),
        native_deps=NativeDepsContract.for_scalo_extras(
            ["kafka", "metrics", "opentelemetry", "secrets-vault"],
            base_image="python:{python_version}-slim",
        ),
    )
```

---

## Topology

The `deployment.topology` submodule (`model.py` + `loader.py`) loads a
YAML manifest describing cross-app deployment topology -- shared
operators, AppProjects, sync-wave bands. It's a separate concern from
the per-app contract documented here. Topology configs are consumed by
`hyperi-ci` and the gitops bootstrap path, not by app code; see the
`AppProjectContract` reference in [ARTEFACTS.md](ARTEFACTS.md) for the
intersection point.

---

## Related

- [ARTEFACTS.md](ARTEFACTS.md)
- [NATIVE-DEPS.md](NATIVE-DEPS.md)
- [KEDA.md](KEDA.md)
- [IDENTITY.md](IDENTITY.md)
- [TEST-SUPPORT.md](TEST-SUPPORT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
