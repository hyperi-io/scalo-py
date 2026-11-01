# NativeDepsContract

Runtime shared libraries the container needs beyond what the wheels
carry. The contract drives the Dockerfile's APT block automatically --
consumers don't hand-write `RUN apt-get install` lines.

```python
from scalo.deployment import NativeDepsContract, AptRepoContract
```

No scalo-py extra installs a package beyond `ca-certificates curl
netcat-openbsd iputils-ping` (the always-on base packages). The
confluent-kafka wheel bundles a librdkafka with OpenSSL and zlib linked
in, the Python image holds its own OpenSSL, and `ca-certificates` fills
the CA store both read.

---

## `NativeDepsContract`

| Field | Type | Default |
|---|---|---|
| `apt_repos` | `list[AptRepoContract]` | `[]` |
| `apt_packages` | `list[str]` | `[]` |
| `distro` | `BaseDistro \| None` | `None`, left out when unset |
| `unresolved_base_image` | `str \| None` | `None`, left out when unset |
| `contradicted_base_image` | `str \| None` | `None`, left out when unset |
| `distro_codename` | `str` | `trixie` |

`distro`, `unresolved_base_image` and `contradicted_base_image` carry what scalo-rs records: the release the package names were resolved for (`trixie`, `bookworm`, `noble`, `jammy` or `focal`), the base image whose release could not be derived, and the base image that names a different release from the one config stated. Both factories set `distro` from `distro_codename` when scalo knows that release. A contract that names `distro` but not `distro_codename` takes `distro_codename` from it.

- `is_empty()` -- shortcut the Dockerfile generator uses to emit a
  smaller APT block when there's nothing extra.
- `for_scalo_extras(extras, base_image, *, distro_codename=...)` --
  factory; see below.
- `for_scalo_features(features, base_image, *, distro_codename=...)`
  -- factory for polyglot apps that re-bind a scalo-rs core.

`distro_codename` names the base-image suite the package names were
selected for, and is recorded in the emitted contract so CI can audit
which suite an image targets. It defaults to `trixie` (Debian 13),
which is what `python:{python_version}-slim` resolves to.

State it explicitly -- never sniff it out of the base-image string.
`debian:13-slim`, `debian:stable-slim` and any digest-pinned reference
all defeat substring matching, and getting it wrong produces a package
name that does not exist in the target suite (see
[Verify by building](#verify-by-building-not-by-reading-the-index)).

---

## `AptRepoContract`

A custom APT repository, for a package no distro suite carries.

| Field | Required | Notes |
|---|---|---|
| `key_url` | yes | GPG key URL -- fetched via `curl -fsSL` |
| `keyring` | yes | Local path; the basename (sans extension) names the sources-list file |
| `url` | yes | Base URL after `deb` |
| `codename` | no | E.g. `noble`. The *vendor repo's* suite, the contract's `distro_codename` when empty |
| `packages` | no | Packages installed from this specific repo |

`codename` here is the suite the **vendor** publishes, which is not
always the base image's own suite. Leave it empty to take the
contract's release.

For distro-versioned package names (`libgit2-1.9` vs `libgit2-1.7`) use
`distro_codename` on the contract instead -- never this field.

---

## Extras -> APT mapping

`NativeDepsContract.for_scalo_extras(extras, base_image)` builds the
runtime contract from your `pyproject.toml` extras list. Pass the same
strings used in `pip install "scalo[...]"`.

| Extra | Adds repos | Adds packages |
|---|---|---|
| every extra, `kafka` included | -- | none |

The contract still records the release (`distro_codename`), so CI can
audit which suite the image targets.

---

## `for_scalo_features` (polyglot apps)

For services with a Rust core re-bound to Python (or vice-versa),
`for_scalo_features(features, base_image)` accepts Cargo feature
names and maps them to runtime APT packages. The mapping mirrors
scalo-rs's own `NativeDepsContract::for_scalo_features` -- both
implementations resolve to the same package set for the same feature
list, by design. The scalo-rs release build links librdkafka, OpenSSL,
zlib and zstd statically.

| Cargo feature | APT packages |
|---|---|
| `directory-config-git` | `libgit2-1.9` (trixie) / `libgit2-1.7` (older) |
| `transport-kafka`, `dlq-kafka*`, `spool`, `tiered-sink`, `http`, `secrets*`, `otel*` | none: linked statically |

The libgit2 name is resolved from `distro_codename` via
`libgit2_runtime_package()`. Soname-versioned packages do not alias --
different ABI versions are genuinely different libraries, so there is
no virtual provider to fall back on and the name must match the suite.

---

## No musl, no Alpine

Application images use a glibc base -- Debian slim. This is a house
rule, and `validate_base_image()` flags a contract that breaks it.

The reason is specific rather than tribal. Python wheels are published
for manylinux, not musllinux, so on Alpine `pip`/`uv` silently falls
back to building from source: a much slower build that yields a slower
runtime, for no gain. scalo's own C-linked dependencies make it worse
-- `confluent-kafka` and `common-expression-language` have no musl
wheels at all, which is exactly why the builder sets `UV_NO_BUILD=1`
to turn that silent fallback into a loud failure.

Alpine images in this repo are test scaffolding, not application
images: a public canary in `test-support.md` and a label-only mock in
`tests/e2e/test_contract_artefacts.py`. Neither breaks the rule and
neither should be "fixed".

---

## Verify by building, not by reading the index

Package names get checked by **building**, never by reading a
distribution's package pages or search UI.

This is not a style preference. An earlier review of this file reported
three build-breaking package names, reasoned from published indexes.
Two of the three were wrong: the packages resolved via `Provides:`
aliases that the package pages do not surface. Only the libgit2 one was
real, and it was real precisely because soname-versioned packages are
the case where aliasing does *not* happen.

So: change a package name, then build the image on the target base
before believing it.

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

- [contract.md](contract.md)
- [artefacts.md](artefacts.md)
- [../extras-flags.md](../extras-flags.md)
- [identity.md](identity.md)
- [test-support.md](test-support.md)
- [../integration.md](../integration.md)
