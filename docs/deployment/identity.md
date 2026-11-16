# Contract Identity Annotation Scheme v1

Three greppable keys stamped onto the image so the same contract output is traceable across surfaces (Dockerfile `LABEL`, container manifest JSON `labels`, and YAML annotations on a chart or ArgoCD `Application` built elsewhere) and across scalo-rs and scalo-py. It mirrors scalo-rs's `scalo::deployment::contract_identity`. scalo-py's output is pinned byte for byte by a golden fixture, which scalo-rs keeps no copy of (see [Cross-language parity](#cross-language-parity)).

OCI has `org.opencontainers.image.source` and `.revision`, which cover the source repo URL and commit SHA, but stop at the container image. Helm charts and ArgoCD `Application` CRs are separate surfaces with no equivalent convention. The `<namespace>.contract.*` keys put the same values on any of the three, and the reverse-DNS namespace keeps them clear of OCI's reserved namespaces.

Import surface, with no pydantic dependency, so it imports without the `deployment` extra:

```python
from scalo.deployment import (
    DEFAULT_LABEL_NAMESPACE,  # "io.scalo"
    KEY_SEGMENT,              # "contract"
    VERSION,                  # "v1"
    ContractIdentity,
    IdentityError,
)
```

## The three keys

The keys sit under `<namespace>.contract`, where `<namespace>` is the contract's `oci_labels.label_namespace`: `io.scalo` unless the app sets its. The table shows the default.

| Key | Value form | Validation |
|---|---|---|
| `io.scalo.contract.version` | literal `v1` | constant -- the scheme version |
| `io.scalo.contract.source-commit` | 40-char lowercase hex SHA | matches `^[0-9a-f]{40}$` exactly. No `sha256:` prefix, no whitespace |
| `io.scalo.contract.image-ref` | `<registry>/<repo>:<tag>` OR `<registry>/<repo>@sha256:<digest>` | non-empty, includes `/`, and the registry host contains `.` or a port `:`, or is the literal `localhost` |

The registry validation forbids an implicit `docker.io`, because an ambiguous registry breaks image provenance. Use the explicit form `docker.io/library/...` if you need Docker Hub.

## `ContractIdentity`

`@dataclass(frozen=True, slots=True)` -- immutable, no `__dict__`.

```python
@dataclass(frozen=True, slots=True)
class ContractIdentity:
    source_commit: str
    image_ref: str
```

`__post_init__` runs both validators, so invalid input raises
`IdentityError` at construction.

### `detect(image_ref)` classmethod

Auto-resolve `source_commit` from the environment:

1. `GITHUB_SHA` env var (GitHub Actions).
2. `CI_COMMIT_SHA` env var (GitLab).
3. `git rev-parse HEAD` in the current working directory, with a 10 s timeout. A missing `git` or a timeout falls through.

If none yield a 40-char lowercase hex SHA, raises `IdentityError`.

```python
identity = ContractIdentity.detect(
    image_ref="ghcr.io/example-org/orders-api:v2.7.3",
)
```

### `as_dockerfile_labels(namespace)` -- emit Dockerfile `LABEL` lines

Three lines under `namespace`, canonical order, NO trailing newline. `as_dockerfile_labels("io.scalo")`:

```dockerfile
LABEL io.scalo.contract.version="v1"
LABEL io.scalo.contract.source-commit="0123456789abcdef0123456789abcdef01234567"
LABEL io.scalo.contract.image-ref="ghcr.io/example-org/orders-api:v2.7.3"
```

### `as_yaml_annotations(namespace, indent=0)` -- emit YAML annotation lines

Three lines under `namespace`, canonical order, NO trailing newline, padded with `indent` spaces. Values are always double-quoted so YAML parsers don't coerce `v1` to a partial version literal and don't misread refs containing `@sha256:`. `as_yaml_annotations("io.scalo", indent=2)`:

```yaml
  io.scalo.contract.version: "v1"
  io.scalo.contract.source-commit: "0123456789abcdef0123456789abcdef01234567"
  io.scalo.contract.image-ref: "ghcr.io/example-org/orders-api:v2.7.3"
```

### `as_labels(namespace)` -- the keys as a dict

The same three keys and values, in the same order, as a `dict[str, str]`. The container manifest merges it into its `labels`. scalo-rs has no equivalent, because its manifest has no identity keys.

No scalo-py generator calls `as_yaml_annotations`. It is for code that builds a YAML surface itself: `indent=2` fits a `Chart.yaml` top-level `annotations:` block, and `indent=4` an ArgoCD `Application` `metadata.annotations:` block.

```python
class IdentityError(DeploymentError, ValueError):
    ...
```

Subclasses BOTH `DeploymentError`, so a handler for the broad deployment exception catches it, AND `ValueError`, so a generic validation handler does as well.

## Pre-push vs post-push image refs

Two valid forms for `image_ref`:

| Form | When | Example |
|---|---|---|
| Tag | Pre-push, mutable | `ghcr.io/example-org/orders-api:v2.7.3` |
| Digest | Post-push, immutable | `ghcr.io/example-org/orders-api@sha256:abc123...` |

CI typically stamps the tag form during build, before the digest exists, and re-stamps the digest form post-push for the production artefact. Both forms pass validation, and a consumer that needs the immutable form checks for `@sha256:` in the value.

## Wiring into the generators

All three identity-aware generators take `identity` as a keyword-only
opt-in, default `None`:

```python
generate_dockerfile(contract, identity=identity)
generate_runtime_stage(contract, identity=identity)
generate_container_manifest(contract, identity=identity)
```

With `identity=None` the output has no identity keys. With an `identity`:

| Generator | Where identity lands |
|---|---|
| `generate_dockerfile` | three `LABEL` lines after `io.scalo.profile` |
| `generate_runtime_stage` | three `LABEL` lines after `io.scalo.profile`, before the dynamic OCI `ARG`/`LABEL` block |
| `generate_container_manifest` | three keys in the `labels` JSON dict |

Every generator renders the keys under the contract's `oci_labels.label_namespace`.

`generate_compose_fragment` and `generate_argocd_app_project` do NOT take `identity`.

## Cross-language parity

A golden fixture at `tests/fixtures/contract-parity/v1-output.txt` pins the output. It has four sections, separated by `=== <section-name> ===` headers, all rendered under `io.scalo`:

- `dockerfile-labels` -- output of `as_dockerfile_labels("io.scalo")`
- `yaml-annotations-indent-0` -- output of `as_yaml_annotations("io.scalo", 0)`
- `yaml-annotations-indent-2` -- output of `as_yaml_annotations("io.scalo", 2)`
- `yaml-annotations-indent-4` -- output of `as_yaml_annotations("io.scalo", 4)`

All sections use the same test inputs:

```text
source_commit = "0123456789abcdef0123456789abcdef01234567"
image_ref     = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"
```

`tests/unit/deployment/test_contract_identity_parity.py` diffs `ContractIdentity` output against each section byte for byte, and checks the file has LF line endings. When `SCALO_RS_GOLDEN_PATH` names another copy of the file, it diffs that as well, and skips otherwise. scalo-rs has the `contract_identity` module (`src/deployment/contract_identity.rs`) but no copy of the fixture, so nothing diffs the two implementations' output.
