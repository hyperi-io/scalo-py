# Contract Identity Annotation Scheme v1

Three greppable keys stamped onto every deployment artefact so the
same logical contract output is traceable across surfaces (Dockerfile
`LABEL`, Helm `Chart.yaml` annotations, ArgoCD `Application`
annotations, container manifest JSON `labels`) and across language
tiers (rustlib, pylib, hyperi-ci). Mirrors
`hyperi_rustlib::deployment::contract_identity` byte-for-byte; both
implementations are diffed against a shared golden fixture.

Import surface -- no pydantic dependency, importable as soon as the
deployment package is available:

```python
from hyperi_pylib.deployment import (
    KEY_PREFIX,        # "io.hyperi.contract"
    VERSION,           # "v1"
    ContractIdentity,
    IdentityError,
)
```

---

## The three keys

| Key | Value form | Validation |
|---|---|---|
| `io.hyperi.contract.version` | literal `v1` | constant -- the scheme version |
| `io.hyperi.contract.source-commit` | 40-char lowercase hex SHA | matches `^[0-9a-f]{40}$` exactly. No `sha256:` prefix, no whitespace |
| `io.hyperi.contract.image-ref` | `<registry>/<repo>:<tag>` OR `<registry>/<repo>@sha256:<digest>` | non-empty; must include `/`; registry host must contain `.`, a port `:`, or be literal `localhost` |

The registry validation deliberately forbids implicit `docker.io` --
ambiguous registries break image provenance. Use the explicit form
`docker.io/library/...` if you need Docker Hub.

---

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
3. `git rev-parse HEAD` in the current working directory (10s
   timeout; `FileNotFoundError` or `TimeoutExpired` -> falls through).

If none yield a 40-char lowercase hex SHA, raises `IdentityError`.

```python
identity = ContractIdentity.detect(
    image_ref="ghcr.io/hyperi-io/dfe-loader:v2.7.3",
)
```

### `as_dockerfile_labels()` -- emit Dockerfile `LABEL` lines

Three lines, canonical order, NO trailing newline:

```dockerfile
LABEL io.hyperi.contract.version="v1"
LABEL io.hyperi.contract.source-commit="0123456789abcdef0123456789abcdef01234567"
LABEL io.hyperi.contract.image-ref="ghcr.io/hyperi-io/dfe-loader:v2.7.3"
```

### `as_yaml_annotations(indent=0)` -- emit YAML annotation lines

Three lines, canonical order, NO trailing newline, padded with
`indent` spaces. Values are always double-quoted so YAML parsers
don't coerce `v1` to a partial version literal and don't misread refs
containing `@sha256:`.

```yaml
  io.hyperi.contract.version: "v1"
  io.hyperi.contract.source-commit: "0123456789abcdef0123456789abcdef01234567"
  io.hyperi.contract.image-ref: "ghcr.io/hyperi-io/dfe-loader:v2.7.3"
```

Indent levels used in the generators:

- `indent=2` -- Helm `Chart.yaml` top-level `annotations:` block.
- `indent=4` -- ArgoCD `Application` `metadata.annotations:` block.

---

## `IdentityError`

```python
class IdentityError(DeploymentError, ValueError):
    ...
```

Subclasses BOTH `DeploymentError` (so consumers catching the broad
deployment exception still trigger) AND `ValueError` (so generic
validation handlers in calling code still trigger). The double-base
is intentional and load-bearing.

---

## Pre-push vs post-push image refs

Two valid forms for `image_ref`:

| Form | When | Example |
|---|---|---|
| Tag | Pre-push, mutable | `ghcr.io/hyperi-io/dfe-loader:v2.7.3` |
| Digest | Post-push, immutable | `ghcr.io/hyperi-io/dfe-loader@sha256:abc123...` |

CI typically stamps the tag form during build (the digest doesn't
exist yet) and re-stamps the digest form post-push for the production
artefact. Both forms pass validation; consumers wanting the immutable
guarantee filter by the presence of `@sha256:` in the value.

---

## Wiring into the generators

All five identity-aware generators take `identity` as a keyword-only
opt-in, default `None`:

```python
generate_dockerfile(contract, identity=identity)
generate_runtime_stage(contract, identity=identity)
generate_container_manifest(contract, identity=identity)
generate_chart(contract, output_dir, identity=identity)
generate_argocd_application(contract, argo, identity=identity)
```

Behaviour when `identity=None`: pre-identity output, byte-for-byte
unchanged. Behaviour when `identity` is provided:

| Generator | Where identity lands |
|---|---|
| `generate_dockerfile` | three `LABEL` lines after `io.hyperi.profile` |
| `generate_runtime_stage` | three `LABEL` lines after `io.hyperi.profile`, before the dynamic OCI `ARG`/`LABEL` block |
| `generate_container_manifest` | three keys in the `labels` JSON dict |
| `generate_chart` (Chart.yaml only) | `annotations:` block at the top level of `Chart.yaml` (indent=2) |
| `generate_argocd_application` | three keys in `metadata.annotations` next to `argocd.argoproj.io/sync-wave` (indent=4) |

`generate_compose_fragment` and `generate_argocd_app_project` do NOT
take `identity` -- Compose has no annotation surface, and AppProjects
predate any individual contract instance.

---

## Cross-language parity

The scheme is single-sourced via a golden fixture at
`tests/fixtures/contract-parity/v1-output.txt`. Four sections, separated
by `=== <section-name> ===` headers:

- `dockerfile-labels` -- output of `as_dockerfile_labels()`
- `yaml-annotations-indent-0` -- output of `as_yaml_annotations(0)`
- `yaml-annotations-indent-2` -- output of `as_yaml_annotations(2)`
- `yaml-annotations-indent-4` -- output of `as_yaml_annotations(4)`

All sections use the same test inputs:

```
source_commit = "0123456789abcdef0123456789abcdef01234567"
image_ref     = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"
```

`tests/unit/deployment/test_contract_identity_parity.py` diffs
`ContractIdentity` output against each section byte-for-byte. When a
local `/projects/hyperi-rustlib/tests/fixtures/contract-parity/v1-output.txt`
exists, the parity test additionally diffs the two repos' copies --
any mismatch fails the suite with the diff in the assertion message.

File invariants: LF line endings, UTF-8, trailing newline, no blank
lines inside content blocks.

### Status

The pylib fixture is the authored reference until rustlib publishes
its `contract_identity` module. Once rustlib lands, copy its golden
verbatim into the pylib repo and update the parity test's drift
detection to point at the rustlib path. Eventually both copies move
to `hyperi-ci/tests/fixtures/contract-parity/` and both libs consume
from there.

---

## Phase staging

The scheme rolls out in three coordinated phases across pylib,
rustlib, and the consumer apps:

| Phase | State | Default | Generators |
|---|---|---|---|
| 1 (current) | opt-in | `identity=None` | output unchanged unless caller passes identity |
| 2 | required | `identity` is required at call sites | running without identity raises -- forces consumers to wire it |
| 3 | inlined | wrapper dropped | identity is always stamped; the kwarg disappears |

Phase 1 keeps existing CI green during the rollout. Phase 2 lands
once every consumer app has been updated -- the change is
`identity: ContractIdentity` (positional or required kwarg).
Phase 3 is a major version bump.

---

## Why a separate scheme

OCI has `org.opencontainers.image.source` and
`.revision` already -- those cover the source repo URL and commit
SHA, but stop at the container image. Helm charts and ArgoCD
`Application` CRs are separate surfaces with no equivalent
convention. The `io.hyperi.contract.*` keys span all three surfaces
uniformly, and the prefix is namespaced so it can't collide with
OCI's reserved namespaces.

---

## Related

- [CONTRACT.md](CONTRACT.md)
- [ARTEFACTS.md](ARTEFACTS.md)
- [TEST-SUPPORT.md](TEST-SUPPORT.md)
- [NATIVE-DEPS.md](NATIVE-DEPS.md)
- [KEDA.md](KEDA.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../README.md](../README.md)
