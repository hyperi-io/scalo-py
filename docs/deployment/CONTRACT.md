# DeploymentContract

The Pydantic model an app builds once from its `Config.default()`. CI validates Helm charts and Dockerfiles against the contract, and generators emit deployment artefacts from it. scalo-py parses every field scalo-rs's `scalo::deployment::contract` writes, under the same name and JSON shape, and writes it back unchanged. Only scalo-py has `builder_image`, `python_version`, `emit_healthcheck` and `native_deps.distro_codename`, which scalo-rs ignores.

`tests/fixtures/contract-parity/deployment-contract.json` is a contract scalo-rs emitted with every optional field set, copied from scalo-rs's own `tests/fixtures/contract-parity/`. `tests/unit/deployment/test_contract_parity.py` parses it, re-emits it and checks nothing changed, so a field scalo-rs adds fails here until scalo-py carries it.

Import surface (gated on the `[deployment]` extra; importing without
`pydantic>=2.13` defers and raises `ProviderNotAvailableError`):

```python
from scalo.deployment import (
    DeploymentContract, HealthContract, OciLabels,
    PortContract, SecretGroupContract, SecretEnvContract,
    EnabledCondition, EqualsCondition, OneOfCondition,
    ImageProfile,
)
```

---

## Top-level fields

| Field | Type | Default | Purpose |
|---|---|---|---|
| `schema_version` | `int` | `3` (`DEFAULT_SCHEMA_VERSION`) | CI rejects above `MAX_SUPPORTED_SCHEMA_VERSION` |
| `app_name` | `str` | required | Matches `Chart.yaml` `name`; image repo segment |
| `binary_name` | `str` | `""` | Falls back to `app_name` via `.binary()` |
| `description` | `str` | `""` | Chart description |
| `metrics_port` | `int` (1..65535) | required | Metrics + health listen port |
| `health` | `HealthContract` | factory | Probe paths -- see below |
| `env_prefix` | `str` | required | Dynaconf prefix; `__` is the nesting separator |
| `metric_prefix` | `str` | required | Prometheus namespace |
| `config_mount_path` | `str` | required | E.g. `/etc/event-loader/config.yaml` |
| `image_registry` | `str` | required | Container registry base. A blank value is refused at construction |
| `extra_ports` | `list[PortContract]` | `[]` | HTTP / gRPC / data ports beyond metrics |
| `unbound_listen_paths` | `list[str]` | `[]`, left out when empty | `default_config` listen paths that need no port, e.g. a send-only client's bind address |
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
| `oci_labels` | `OciLabels` | factory | Static OCI labels and the namespace of scalo's own keys -- see [`OciLabels`](#ocilabels) |
| `config_schema` | `dict \| None` | `None` | JSON Schema of the app's `Config` (v3) |
| `capabilities` | `list[Capability]` | `[]` | Runtime-surface catalogue (v3) |

`image_registry` has no default, and scalo-py refuses a missing or blank one when the contract is built. scalo-rs refuses it later, in `validate()`. Read an organisation-wide value from the cascade:

```python
image_registry=image_registry_from_cascade() or "registry.example.com/team"
```

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
    image_registry="registry.example.com/team",
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
| `title` | `""` | Falls back to `app_name` in generators |
| `description` | `""` | |
| `vendor` | `""` | `org.opencontainers.image.vendor`. Empty writes no label |
| `label_namespace` | `"io.scalo"` (`DEFAULT_LABEL_NAMESPACE`) | Namespace of scalo's own keys, below |
| `licenses` | `""` | `org.opencontainers.image.licenses` and the Dockerfile `# License` line. Empty writes neither |
| `copyright` | `""` | The Dockerfile `# Copyright` line. Empty writes no line |

Dynamic labels (`org.opencontainers.image.source`, `revision`,
`version`, `created`) are CI-injected via `--build-arg`; the static
labels listed here come from the contract.

`vendor`, `licenses` and `copyright` name the app's vendor, licence and copyright holder. scalo names none of its own, so an app's artefacts carry only the terms the app states.

scalo stamps a few keys of its own beside the standard `org.opencontainers.image.*` labels, all under `label_namespace`:

| Key | Where | Value |
| --- | --- | --- |
| `<namespace>.profile` | Dockerfile, runtime stage, container manifest | `production` or `development` |
| `<namespace>.app` | container manifest | `app_name` |
| `<namespace>.metrics_port` | container manifest | `metrics_port` |
| `<namespace>.contract.version` / `.source-commit` / `.image-ref` | Dockerfile, runtime stage, container manifest, `Chart.yaml`, ArgoCD `Application`, when a `ContractIdentity` is passed | see [IDENTITY.md](IDENTITY.md) |

An app that already ships its own namespace keeps it by setting `label_namespace`, and every key above moves with it.

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

Two optional fields say when the listener exists and which address it serves. Each is left out of the emitted contract when unset:

| Field | Type | Meaning |
| --- | --- | --- |
| `when` | `EnabledCondition \| EqualsCondition \| OneOfCondition \| None` | The values condition under which the listener exists. None means it always listens |
| `bound_from` | `str \| None` | Dotted `default_config` path of the listen address, e.g. `grpc.listen` |

The condition is tagged by `kind`, as scalo-rs's `PortCondition` serialises it. `path` is dotted and `.Values`-relative, e.g. `config.grpc.enabled`:

| Model | JSON |
| --- | --- |
| `EnabledCondition(path=...)` | `{"kind": "enabled", "path": ...}` -- true is anything but false, null, zero or empty |
| `EqualsCondition(path=..., value=...)` | `{"kind": "equals", "path": ..., "value": ...}` |
| `OneOfCondition(path=..., values=[...])` | `{"kind": "one_of", "path": ..., "values": [...]}` |

scalo-py's generators read neither field yet: the Dockerfile `EXPOSE`, the container manifest, the Compose fragment and the chart carry every port unconditionally, where scalo-rs's keep a gated port out of `EXPOSE` and render it only while its condition holds.

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
DEFAULT_SCHEMA_VERSION = 3
MAX_SUPPORTED_SCHEMA_VERSION = 3
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
    image_registry="registry.example.com/team",
)
raw = contract.to_json()
restored = DeploymentContract.from_json(raw)
assert restored == contract
```

`exclude_none=False` so a parsed contract round-trips byte-equal to the
emitted JSON. CI uses this to diff a freshly emitted contract against
the one committed in the repo. The fields scalo-rs leaves out when unset are
left out here too: `unbound_listen_paths`, a port's `when` and `bound_from`,
and `native_deps.distro`, `unresolved_base_image` and `contradicted_base_image`.

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
        image_registry=image_registry_from_cascade() or "registry.example.com/team",
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
