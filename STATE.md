# hyperi-pylib - Project State

**Repository**: <https://github.com/hyperi-io/hyperi-pylib>
**Type**: Python package (shared library)
**Purpose**: Enterprise infrastructure for all HyperI Python projects

---

## ⚠ Release discipline — READ FIRST

**A release is NOT complete until the new version is on PyPI.**
A `git push` (or `hyperi-ci push` without `--release`) only triggers
the CI build + semantic-release tag. It does **not** publish to PyPI.
A two-step flow is required, and both steps must be verified:

1. **Publish:** use `hyperi-ci push --release` (combined push + auto-
   publish if CI passes) OR push first, then `hyperi-ci release vX.Y.Z`
   on the resulting tag. **Bare `git push` is not a release.**
2. **Verify on PyPI:** after the publish workflow completes, confirm
   the new version is live:

   ```bash
   curl -sSL https://pypi.org/pypi/hyperi-pylib/json \
       | grep -o '"version":"[^"]*"' | head -1
   ```

   The reported version MUST match the just-released tag. If it
   doesn't, the release did NOT land — investigate the workflow
   run (`hyperi-ci logs --failed`) before declaring done.

**Why this matters:** the local git tag, the GitHub Release, and the
PyPI artefact are three separate states. Downstream consumers
(`dfe-engine`, etc.) pin to the PyPI version. A green CI + a tag
without a published artefact looks complete but isn't.

---

## Design decision: cross-language spec workflow (pylib leads)

When a feature spans pylib + rustlib (log scrubbing, config cascade,
metrics, deployment contract, etc.), this is how specs and
implementations stay in sync.

**The spec is canonical at `hyperi-ai/standards/specs/`** once
accepted. Until it gets there, the working master lives in
`docs/superpowers/specs/` in each consumer project, with the
contract sections byte-identical between pylib's and rustlib's
copies. "Byte-identical" means a `diff` over the contract sections
returns empty — drift is mechanically detectable.

**Pylib implements first** as the reference implementation. Python's
cheaper iteration cost means we discover spec gaps faster in pylib
than in rustlib. When implementation reveals a gap or ambiguity:

1. Fix the canonical spec (in hyperi-ai, or the working master if
   canonical hasn't landed)
2. Fix the rustlib copy byte-identically (contract sections)
3. Adapt the pylib code to the corrected spec — never the other way
   around
4. All three changes ship together; never let one lag

**Rustlib references pylib code** once pylib stabilises a feature.
The pylib code is the cross-language reference for algorithm shape,
edge cases, and fixture interpretation. The spec is the contract;
the pylib code is the reference implementation. Same redaction
labels, same metric names, same config keys, same fixture results —
verified by CI.

This ordering matters: discovering a spec mistake after rustlib has
shipped costs more than discovering it during the pylib build. Move
fast in Python; once stable, port carefully to Rust.

The discipline holds even after rustlib work starts. Disagreements
are resolved by updating the spec and both implementations, not by
letting them drift.

---

## Design decision: pylib is for control plane, not the hot path

This is foundational and shapes every other choice in the library.

> **Pylib runs control-plane APIs, UI backends, orchestrators,
> CLI tools, integration glue, batch workloads, and configuration
> management. It does not run the hot path. Hot-path data
> processing — millions of messages per second, microsecond
> budgets, hand-tuned allocator paths — lives in
> `hyperi-rustlib` (or a Rust binary that consumes it).**

What this looks like in code:

- **We optimise sensibly.** No gratuitously slow choices, no
  algorithmic mistakes, no leaving obvious perf on the table.
- **The lean is toward stability, expressiveness, and
  integration** — not toward microseconds. Readability + ease
  of correct use + fitting cleanly with FastAPI / typer / the
  Astral tool chain ranks above shaving a millisecond.
- **Heavier deps are acceptable when they earn their keep**
  (NER-grade PII detection is a 5–200ms call; that's fine on a
  control-plane process, not in a Rust ingest loop).
- **Async APIs exist for ergonomics**, not because pylib is
  shouldering microsecond latency budgets. We do them properly
  (no sync-in-async, proper offload to threads) but we don't
  hand-roll loops to save dispatch overhead.
- **We don't hard-iterate the hot path** — that's rustlib's job.
  No SIMD primitives, no arena allocators, no zero-copy parsers
  for pylib's call surface. Reach for rustlib (via PyO3) when
  that becomes the actual requirement.

If you're reading pylib code and wondering why something prefers
the slower-but-clearer option, the readable abstraction over the
inlined one, or a 5ms regex over a 50µs hand-roll — this is why.
Speed in pylib is "fast enough for control plane and integration";
speed in rustlib is "fast enough for the hot path".

---

## ⚠ Cross-Repo Reminder: hyperi-ai PYTHON.md

`hyperi-ai/standards/languages/PYTHON.md` carries a deliberately
**drift-safe** "hyperi-pylib" section — it lists capabilities, not API
surface, so routine pylib changes don't require touching it.

**You only need to revisit that section when pylib gains or loses a
WHOLE capability.** Examples that would trigger an update:

- New top-level subsystem (e.g., adding a GraphQL client, a job-queue
  abstraction, a feature-flag SDK).
- Removal of a subsystem (e.g., deprecating Kafka helpers in favour of
  something else).
- A capability being moved out into its own package.

You do NOT need to update PYTHON.md for: function-signature changes,
new feature extras, version bumps, internal refactors, performance
work, bug fixes, or new options on existing subsystems.

When in doubt, ask: "would a HyperI Python developer think differently
about *what tools they reach for* because of this change?" If yes,
update PYTHON.md's pylib section. If no, leave it alone.

---

## Session Management

**New session?** Run `/start` to initialise (reads STATE.md, TODO.md, standards)
**Save progress:** Run `/save` to checkpoint

### Local Development

```bash
make quality               # Lint, type-check, security audit
make test                  # Run test suite
make build                 # Build wheel
```

Requires `hyperi-ci` CLI: `uv tool install hyperi-ci`

CI runs via `hyperi-io/hyperi-ci` reusable GitHub Actions workflow — no submodule.

---

**Build type:** Native wheel only (no Nuitka)

---

## Architecture: PostgreSQL Cache Backend

```text
┌─────────────────────────────────────────────────────────┐
│                    Application (dfe-engine)             │
│  ┌─────────────────────────────────────────────────┐   │
│  │         PostgresCache (hyperi-pylib)                │   │
│  │  ┌─────────────┐  ┌─────────────────────────┐   │   │
│  │  │ Serializer  │  │ AsyncConnectionPool     │   │   │
│  │  │ (msgpack)   │  │ (psycopg3)              │   │   │
│  │  └─────────────┘  └─────────────────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │  Pod A  │      │  Pod B  │      │  Pod C  │
    └────┬────┘      └────┬────┘      └────┬────┘
         └────────────────┼────────────────┘
                          ▼
              ┌───────────────────────┐
              │      PostgreSQL       │
              │   cache_entries       │
              └───────────────────────┘
```

### API Usage

```python
from hyperi_pylib.cache import PostgresCache, generate_cache_key

cache = PostgresCache(dsn="postgresql://user:pass@host/db")
await cache.init()

key = generate_cache_key("analytics", "events", org_id="acme")
await cache.set(key, {"data": [...]}, ttl_seconds=300, namespace="analytics")
value = await cache.get(key)

await cache.close()
```

---

## CI Architecture

CI uses `hyperi-io/hyperi-ci` reusable GitHub Actions workflows. No local submodule.

### Configuration

**Single source:** `.hyperi-ci.yaml`

### Publish

Publishes to **public PyPI** (`publish-target: oss`).

### Runner Configuration

**Org-level:** `GH_RUNNER_DEFAULT=arc-runner-16cpu` (ARC self-hosted runners)
**No repo-level override** — inherits org setting

### Update CI Config

Only `.hyperi-ci.yaml` needs editing — workflow files are managed by `hyperi-ci`.

---

## Architecture: DfeApp CLI Framework

Mirrors rustlib's `cli::app` module. Python DFE services subclass `DfeApp` to get
standard CLI lifecycle for free (80% boilerplate, 20% app logic).

```python
from hyperi_pylib.cli import DfeApp, VersionInfo

class MyService(DfeApp):
    name = "dfe-control-plane"
    env_prefix = "DFE_CP"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "1.0.0")

    def run_service(self, config) -> None:
        ...  # sync

    async def run_service_async(self, config) -> None:
        ...  # or async

if __name__ == "__main__":
    MyService().cli()
```

**Standard subcommands:** `run`, `version`, `config-check`
**No `top` command** — Python is never on the hot path (that's Rust)
**Config:** Always uses `hyperi_pylib.config` cascade (Dynaconf), not bespoke loading

---

## Quick Reference

**Python requirement:** 3.12+

**Local commands:**

```bash
make quality    # Lint, type-check, security audit
make test       # Run test suite
make build      # Build wheel
```

**CI config:** `.hyperi-ci.yaml` — edit to adjust quality/publish settings.

---

## Architecture: Deployment Contract (`hyperi_pylib.deployment`)

Mirrors `hyperi_rustlib::deployment`: same JSON contract input → matching
Dockerfile / Helm chart / Compose fragment / ArgoCD ``Application`` output
across both implementations.

**Capability summary:**

- ``DeploymentContract`` (Pydantic v2 models) — app metadata, ports, secrets,
  KEDA scaling, native deps, OCI labels.
- Generators: ``generate_dockerfile``, ``generate_runtime_stage``,
  ``generate_container_manifest`` (JSON for CI), ``generate_compose_fragment``,
  ``generate_chart`` (full Helm chart), ``generate_argocd_application``.
- Cascade helpers: ``image_registry_from_cascade``, ``base_image_from_cascade``,
  ``argocd_repo_url_from_cascade`` — read from Dynaconf ``deployment.*`` keys.
- ``DfeApp.deployment_contract()`` hook + ``generate-artefacts`` standard CLI
  subcommand emit the four artefacts to ``--output-dir``.
- ``NativeDepsContract.for_pylib_extras`` (Python apps) and
  ``for_rustlib_features`` (polyglot via PyO3) auto-resolve runtime APT
  packages.

**Opt-in:** Optional extra ``[deployment]`` adds ``pydantic>=2.13``. Apps that
don't ship as containers don't pull in Pydantic. Importing the module without
the extra raises ``ProviderNotAvailableError`` at first use.

**Cross-language byte parity:** Generators use Python f-strings (not jinja2)
to match rustlib's ``format!()`` output character-for-character. Parity tests
land in v2.29.0+ once ``hyperi-rustlib/tests/parity/fixtures/`` ships.

**hyperi-ai PYTHON.md:** the deployment subsystem IS a new top-level
capability — bump the pylib capabilities section in
``hyperi-ai/standards/languages/PYTHON.md`` next time it's touched.

---

## Active Work: Secrets Abstraction — Plan 4

**Current state:** Plans 1-3 shipped. File and Ansible Vault providers have full
list/CRUD/metadata support. Cloud providers (OpenBao, AWS, GCP, Azure) are being
filled in now — see TODO.md for current task progress.

**Spec:** `docs/superpowers/specs/2026-04-10-secrets-abstraction-extensions-design.md`.
**Implementation order:** OpenBao → AWS → GCP → Azure (easiest → hardest).
**Target:** v2.28.0 (minor bump — capability addition).

**Key design invariants (don't break these):**

- Cloud providers inherit from `VersionedProvider`, file providers from `SecretProvider`.
- `isinstance(p, VersionedProvider)` is the capability check in `SecretsManager.get_version` / `list_versions`.
- AWS `batch_get` should use native `batch_get_secret_value` — `SecretsManager.batch_get` already delegates via `hasattr(p, "batch_get_async")`.
- Map provider errors to: `SecretNotFoundError`, `SecretAlreadyExistsError`, `SecretPermissionError(provider, operation, path, hint)`, `SecretVersionNotFoundError`.

**Test strategy (no creds required for pylib work):**

- Unit tests for OpenBao/Azure use `pytest-httpx` (HTTP/REST wire fakes — already in deps).
- Unit tests for AWS use `moto` (in-process AWS emulator — add to dev extras).
- Unit tests for GCP configure HTTP transport via `client_options={"api_endpoint": ...}` then use `pytest-httpx`.
- OpenBao integration: docker `hashicorp/vault` image via the dual-mode cascade pattern in `tests/conftest.py`.
- Live AWS/GCP/Azure integration tests skip via existing `@requires_*` markers when CLI/SSO/ADC creds aren't available — release CI runs against docker fakes per HyperI policy.

---

## Cloud test environment notes

- **AWS:** the production / engineering account is now `104771614995` (`hypersec-internet-services`
  SSO profile). Static `AWS_ACCESS_KEY_ID` env vars from earlier sessions are stale — use
  `aws sso login --profile hypersec-internet-services` then export creds via
  `aws configure export-credentials --profile hypersec-internet-services --format env`. The
  account may not have all the test resources running yet; coordinate before assuming
  `hyperi-pylib-test` secrets exist.
- **Azure / M365:** the current Azure tenant and M365 environment are scheduled to be
  deleted and recreated soon. Anything that depends on tenant ID, vault URL, service
  principal, or M365-side fixtures (e.g. `HYPERI_TEST_AZURE_VAULT_URL`,
  `AZURE_TENANT_ID`) will need to be refreshed once the new tenant comes up. Live Azure
  integration tests will need new vault + a re-seeded test secret post-recreation.
- **GCP:** `infra-486601` project remains in use; service account JSON at
  `~/certs/gsuite-admin-sa.json`.
- **OpenBao:** devex VM at `10.66.0.101:8200` is unreachable from `derek-dragonfly` —
  use docker `hashicorp/vault` locally instead.

---

**Last Updated:** 2026-04-30
