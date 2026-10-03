# Migrating from `hyperi-pylib` to `scalo`

`scalo` is the renamed, de-branded, Apache-2.0 continuation of the
`hyperi-pylib` library. It is the **same codebase and the same version
line** -- `scalo` picks up where `hyperi-pylib` left off (the 2.28.x
series continues into 2.29.x; there is no version reset). The import
package was renamed `hyperi_pylib` -> `scalo`, a handful of unused
subsystems were dropped, and brand-specific naming was made
configurable.

This guide lists every change a consumer needs to make. Most are
mechanical.

---

## 1. Package + import rename

```diff
- pip install hyperi-pylib
+ pip install scalo
```

```diff
- from hyperi_pylib.config import settings
- from hyperi_pylib.logger import logger
- from hyperi_pylib.metrics import create_metrics
+ from scalo.config import settings
+ from scalo.logger import logger
+ from scalo.metrics import create_metrics
```

A project-wide find/replace of `hyperi_pylib` -> `scalo` (imports) and
`hyperi-pylib` -> `scalo` (dependency specifiers) covers the bulk.

Extras keep their names: `scalo[kafka,metrics,opentelemetry,secrets,deployment]`.

---

## 2. Licence change: BUSL-1.1 -> Apache-2.0

`scalo` is licensed under **Apache-2.0** (was BUSL-1.1). Third-party
attributions (gitleaks rules, python-stdnum) are recorded in `NOTICE`.
There are no longer any commercial-use restrictions, AI-training
restrictions, or `COMMERCIAL.md` / `AI-TRAINING-POLICY.md` files.

---

## 3. Removed subsystems

The following were dropped because no current consumer used them. If you
relied on one, the replacement is noted.

| Removed | Notes / replacement |
|---|---|
| `hyperi_pylib.database` (URL builders) | Build your DSN directly, or with your driver's helpers. |
| `hyperi_pylib.cache` (`PostgresCache`) | No drop-in replacement. A shared Postgres cache is the wrong shape for resilience (adds a SPOF). For config last-known-good, use `scalo.config.DirectoryConfigStore`. |
| PostgreSQL config-cascade layer | The cascade is now 7 layers (was 8). Load DB config like any other setting via `settings`. |
| `hyperi_pylib.harness` | Was test-only; moved into the library's own test suite. |

Dropping `cache` also removed `psycopg`, `cashews`, and `msgpack` from
the dependency tree.

---

## 4. Environment variables: bare by default, single prefix

`hyperi-pylib`'s internal `HYPERI_*` control variables have been
**removed entirely** (no deprecated fallback). `scalo` uses a single,
configurable env-var prefix that is **bare ("") by default**:

- With no prefix set, control/config vars are read bare: `DEBUG`,
  `LOG_LEVEL`, `DATABASE_HOST`, ...
- A consuming app sets its own prefix once -- then *everything*
  (scalo's control knobs and your config-cascade keys) is read as
  `<PREFIX>_<KEY>`:

  ```python
  from scalo.cli import ServiceApp

  class MyService(ServiceApp):
      name = "my-service"
      env_prefix = "DFE"        # -> DFE_DEBUG, DFE_DATABASE__HOST, ...
  ```

  or imperatively via `set_env_prefix("DFE")` (importable today only from
  `scalo._env_compat` - a public re-export is on the review list),
  or via the bare `ENV_PREFIX` environment variable.

**Action for downstream apps:** pick your prefix (e.g. `DFE`, `DFE_CP`)
and set it on your `ServiceApp`. Any `HYPERI_*` env vars in your
deployment must be renamed to `<YOURPREFIX>_*` (or bare). See
`hyperi-io/dfe-engine#58`.

---

## 5. CLI: `DfeApp` -> `ServiceApp`

The base class is now `ServiceApp`. `DfeApp` shipped as a deprecated
alias for one release and has since been removed.

```diff
- from scalo.cli import DfeApp
- class MyService(DfeApp): ...
+ from scalo.cli import ServiceApp
+ class MyService(ServiceApp): ...
```

---

## 6. Metrics: `dfe_groups` -> `groups`, and a configurable namespace

The metric-group module moved:

```diff
- from hyperi_pylib.metrics.dfe_groups import AppMetrics, ConsumerMetrics
+ from scalo.metrics.groups import AppMetrics, ConsumerMetrics
```

Metric **names are now bare by default** -- no library brand prefix
(`dfe_`/`hyperi_`) is baked in. Differentiation between services is via
labels the platform/scrape adds (`job`, `instance`, k8s `pod`/`namespace`),
not a name prefix. There is a single, optional **metric namespace** that
mirrors the env-prefix rule: bare unless you set it, and when set it
prefixes *all* metrics (built-in groups and your own).

**To keep your existing `dfe_`-prefixed metric names**, set the
namespace to `dfe`:

```python
from scalo.metrics import create_metrics
m = create_metrics("my-service", metric_prefix="dfe")   # -> dfe_records_received_total, ...
```

or process-wide via `from scalo.metrics import set_metric_prefix; set_metric_prefix("dfe")`,
or config `metrics.namespace: dfe`. Dashboards/alerts that assume
`dfe_*` names keep working unchanged once the namespace is set.

The naming validator `validate_dfe_prefix(name, app)` shipped as a
deprecated alias and has since been removed; use
`validate_metric_prefix(name, app, prefix=...)`.

---

## 7. version-check: opt-in, configurable URL

The startup version check is now **off by default** and must be enabled
explicitly. Its endpoint is a config-cascade value (no hard-coded URL):

```yaml
version_check:
  enabled: true
  api_url: "https://your-release-feed.example/latest"
```

It is a *version check*, not telemetry -- it does not phone home unless
you enable it and point it at a URL you control.

---

## 8. Deployment contract: neutral defaults

The deployment generators (`scalo.deployment`) carry no organisation's name. There is no default registry, ArgoCD source, vendor, licence or copyright, and scalo's own label keys sit under `io.scalo`. Name yours in the contract (`image_registry`, `oci_labels`) or the `deployment.*` config cascade keys (`deployment.image_registry`, `deployment.argocd.repo_url`, `deployment.argocd.dest_namespace`). See [migrations.md](migrations.md).

---

## Quick checklist

- [ ] `hyperi-pylib` -> `scalo` in dependencies; `hyperi_pylib` -> `scalo` in imports.
- [ ] Rename `HYPERI_*` env vars to `<YOURPREFIX>_*` and set `env_prefix` on your `ServiceApp`.
- [ ] `DfeApp` -> `ServiceApp` (alias removed).
- [ ] `metrics.dfe_groups` -> `metrics.groups`.
- [ ] If you want `dfe_`-prefixed metric names, set the metric namespace to `dfe`.
- [ ] Replace any use of the removed `database` / `cache` modules.
- [ ] Enable `version_check` explicitly if you used it.
- [ ] Set your `deployment.*` cascade overrides if you generate artefacts.
- [ ] Note the licence change to Apache-2.0.
