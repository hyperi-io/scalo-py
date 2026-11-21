# NativeDepsContract

Runtime shared libraries the container needs beyond what the wheels
have. The contract drives the Dockerfile's APT block automatically --
consumers don't hand-write `RUN apt-get install` lines.

```python
from scalo.deployment import NativeDepsContract, AptRepoContract
```

No scalo-py extra installs a package beyond `ca-certificates curl
netcat-openbsd iputils-ping` (the always-on base packages). The
confluent-kafka wheel bundles a librdkafka with OpenSSL and zlib linked
in, the Python image holds its OpenSSL, and `ca-certificates` fills
the CA store both read.

## `NativeDepsContract`

| Field | Type | Default |
|---|---|---|
| `apt_repos` | `list[AptRepoContract]` | `[]` |
| `apt_packages` | `list[str]` | `[]` |
| `distro` | `BaseDistro \| None` | `None`, left out when unset |
| `unresolved_base_image` | `str \| None` | `None`, left out when unset |
| `contradicted_base_image` | `str \| None` | `None`, left out when unset |
| `distro_codename` | `str` | `trixie` |

`distro`, `unresolved_base_image` and `contradicted_base_image` have what scalo-rs records: the release the package names were resolved for (`trixie`, `bookworm`, `noble`, `jammy` or `focal`), the base image whose release could not be derived, and the base image that names a different release from the one config stated. Both factories set `distro` from `distro_codename` when scalo knows that release. A contract that names `distro` but not `distro_codename` takes `distro_codename` from it.

- `is_empty()` -- shortcut the Dockerfile generator uses to emit a
  smaller APT block when there's nothing extra.
- `for_scalo_extras(extras, base_image, *, distro_codename=...)` --
  factory for the scalo-py extras an app uses.
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
[`for_scalo_features`](#for_scalo_features-polyglot-apps)).

`for_scalo_extras(extras, base_image)` takes your `pyproject.toml` extras list, the same strings used in `pip install "scalo[...]"`. No extra, `kafka` included, maps to a package, so the contract records only the release (`distro_codename`) for CI to audit.

## `AptRepoContract`

A custom APT repository, for a package no distro suite has.

| Field | Required | Notes |
|---|---|---|
| `key_url` | yes | GPG key URL -- fetched via `curl -fsSL` |
| `key_fingerprint` | no | Expected OpenPGP fingerprint of the key, uppercase hex with no spaces. The build fails when the downloaded key does not match. Empty skips the check |
| `keyring` | yes | Local path. Its basename, without the extension, names the sources-list file |
| `url` | yes | Base URL after `deb` |
| `codename` | no | E.g. `noble`. The repository's suite, the contract's `distro_codename` when empty |
| `packages` | no | Packages installed from this specific repo |

`codename` is the suite the repository publishes, which is not always the base image's suite. Leave it empty to take the contract's release.

For distro-versioned package names (`libgit2-1.9` vs `libgit2-1.7`) use
`distro_codename` on the contract instead -- never this field.

## `for_scalo_features` (polyglot apps)

For a service with a Rust core re-bound to Python, `for_scalo_features(features, base_image)` takes scalo-rs Cargo feature names and maps them to runtime APT packages. The scalo-rs release build links librdkafka, OpenSSL, zlib and zstd statically, so only `directory-config-git` installs a package.

| Cargo feature | APT packages |
|---|---|
| `directory-config-git` | `libgit2-1.9` on trixie, `libgit2-1.5` on bookworm, `libgit2-1.7` on noble, `libgit2-1.1` on jammy, `libgit2-28` on focal |
| any other | none |

The libgit2 name comes from `distro_codename` via `libgit2_runtime_package()`, which raises `ValueError` for a release outside `BaseDistro`. A soname-versioned package has no alias to fall back on, so the name must match the release.

scalo-rs's `NativeDepsContract::for_scalo_features` names the same packages. It derives the release from `base_image` and records `unresolved_base_image` or `contradicted_base_image`, where scalo-py takes `distro_codename` as given and ignores `base_image`.

Check a package name by building the image on the target base, never by reading a distribution's package pages or search UI. A name that resolves through a `Provides:` alias does not show on those pages, so a name that looks missing there can still install.

## No musl, no Alpine

Application images use a glibc base -- Debian slim. `validate_base_image()` returns a mismatch for a base or builder image whose name contains `alpine` or `musl`.

scalo's C-linked dependencies, `confluent-kafka` and `common-expression-language`, publish manylinux wheels and no musllinux ones. On Alpine, `uv` would build them from source, a much slower build that yields a slower runtime. The builder's `UV_NO_BUILD=1` on the dependency phase turns that into a build failure.

The Alpine images in this repo are test scaffolding, not application images: a label-only mock in `tests/e2e/test_contract_artefacts.py` and the `python:3.12-alpine` input `tests/unit/deployment/test_container_standard.py` feeds the guard.

## Dockerfile APT block behaviour

When the contract is empty (`is_empty()` is true), the Dockerfile
emits a single short `RUN apt-get install` line with just the base
packages (plus dev tools if `image_profile=DEVELOPMENT`).

When non-empty, the block:

1. Installs the base packages, adding `gnupg` when the contract names a custom repository, so the next step can read its key.
2. For each `AptRepoContract`: downloads the GPG key, checks it against `key_fingerprint` when one is set, dearmors it to the `keyring` path, and writes a `deb [signed-by=<keyring>] <url> <codename> main` entry to `/etc/apt/sources.list.d/<keyring-stem>.list`.
3. Re-runs `apt-get update` and installs the union of all per-repo
   packages plus `apt_packages`.
4. Cleans `/var/lib/apt/lists/*`.

The development profile additionally installs `bash strace tcpdump
procps dnsutils net-tools less jq` in the base packages step.
