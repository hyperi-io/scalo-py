# NativeDepsContract

Runtime shared libraries the container needs because a Python wheel
dynamically links against system C libs (librdkafka, libpq, OpenSSL,
etc.). The contract drives the Dockerfile's APT block automatically --
consumers don't hand-write `RUN apt-get install` lines.

```python
from hyperi_pylib.deployment import NativeDepsContract, AptRepoContract
```

Most pylib services need NOTHING beyond `ca-certificates curl
netcat-openbsd iputils-ping` (the always-on base packages). Wheels are
self-contained for `config`, `logger`, `metrics`, `health`, `runtime`,
`secrets-file`, `secrets-ansible`, `expression`, `resilience`,
`concurrency`, `cache` (sqlite mode), `http` (default), and pretty
much every pillar except the explicitly C-linked transports.

---

## `NativeDepsContract`

| Field | Type | Default |
|---|---|---|
| `apt_repos` | `list[AptRepoContract]` | `[]` |
| `apt_packages` | `list[str]` | `[]` |

- `is_empty()` -- shortcut the Dockerfile generator uses to emit a
  smaller APT block when there's nothing extra.
- `for_pylib_extras(extras, base_image)` -- factory; see below.
- `for_rustlib_features(features, base_image)` -- factory for
  polyglot apps that re-bind a rustlib core.

---

## `AptRepoContract`

A custom APT repository (e.g. Confluent for `librdkafka`).

| Field | Required | Notes |
|---|---|---|
| `key_url` | yes | GPG key URL -- fetched via `curl -fsSL` |
| `keyring` | yes | Local path; the basename (sans extension) names the sources-list file |
| `url` | yes | Base URL after `deb` |
| `codename` | no | E.g. `noble`. Derived from `base_image` when empty |
| `packages` | no | Packages installed from this specific repo |

Codename autodetect maps `bookworm`/`jammy`/`focal` from the base
image string; everything else (including `ubuntu:24.04`) falls back to
`noble`.

---

## Extras -> APT mapping

`NativeDepsContract.for_pylib_extras(extras, base_image)` builds the
runtime contract from your `pyproject.toml` extras list. Pass the same
strings used in `pip install "hyperi-pylib[...]"`.

| Extra | Adds repos | Adds packages |
|---|---|---|
| `kafka` | Confluent | `librdkafka1`, `libssl3`, `zlib1g` |
| `cache` (postgres mode) | -- | `libpq5`, `libssl3` |
| `opentelemetry` | -- | `libssl3`, `zlib1g` |
| `http` | -- | `libssl3`, `zlib1g` |
| `secrets-*` (any) | -- | `libssl3`, `zlib1g` |
| all others | -- | none |

Dedup is built in: `libssl3` and `zlib1g` appear once no matter how
many extras pull them in.

Example -- a typical DFE service:

```python
native_deps = NativeDepsContract.for_pylib_extras(
    ["kafka", "metrics", "opentelemetry", "secrets-vault", "http"],
    base_image="ubuntu:24.04",
)
```

Produces: Confluent repo + `librdkafka1`, plus `libssl3` and `zlib1g`.
Anything not in the table maps to no extra packages -- intentionally
strict so the image stays minimal.

---

## `for_rustlib_features` (polyglot apps)

For services with a Rust core re-bound to Python (or vice-versa),
`for_rustlib_features(features, base_image)` accepts Cargo feature
names and maps them to runtime APT packages. The mapping mirrors
rustlib's own `NativeDepsContract::for_rustlib_features` -- both
implementations resolve to the same package set for the same feature
list, by design.

Feature mapping (excerpt):

| Cargo feature | APT packages |
|---|---|
| `transport-kafka`, `dlq-kafka*` | Confluent repo + `librdkafka1` + `libssl3` + `zlib1g` |
| `spool`, `tiered-sink` | `libzstd1` |
| `http`, `secrets*`, `transport*`, `config-postgres`, `otel*` | `libssl3` + `zlib1g` |
| `directory-config-git` | `libgit2-1.7` |

---

## Dockerfile APT block behaviour

When the contract is empty (`is_empty()` is true), the Dockerfile
emits a single short `RUN apt-get install` line with just the base
packages (plus dev tools if `image_profile=DEVELOPMENT`).

When non-empty, the block:

1. Installs base packages first (always includes `gnupg` so the next
   step can verify the custom-repo key).
2. For each `AptRepoContract`: downloads the GPG key, dearmors it to
   the `keyring` path, writes a `deb [signed-by=<keyring>]` entry to
   `/etc/apt/sources.list.d/<keyring-stem>.list`.
3. Re-runs `apt-get update` and installs the union of all per-repo
   packages plus `apt_packages`.
4. Cleans `/var/lib/apt/lists/*`.

The development profile additionally installs `bash strace tcpdump
procps dnsutils net-tools less jq` in the base packages step.

---

## Related

- [CONTRACT.md](CONTRACT.md)
- [ARTEFACTS.md](ARTEFACTS.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
- [IDENTITY.md](IDENTITY.md)
- [TEST-SUPPORT.md](TEST-SUPPORT.md)
- [../INTEGRATION.md](../INTEGRATION.md)
