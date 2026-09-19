# Service Runtime

> **Deprecation notice.** The `Application` framework (`Application.api()`,
> `Application.daemon()`, `Application.cli()`, `profile_overrides`, and
> the related `ServiceRuntime` plumbing) has been **removed** and moved
> to backlog. It was experimental and never used in production. Use the
> core modules directly. From the package docstring:
>
> > The Application framework may return in a future version once the
> > design is mature.
>
> If you landed here grepping for `Application`, `ServiceRuntime`,
> `profile_overrides`, or `app = Application.api(...)` -- read on for
> the supported pattern.

---

## What replaced it

Compose the core modules directly. Everything `Application` used to
auto-wire is still available as a standalone import, and each one is
configured the same way you would have configured it through the
framework.

| Old | New |
|-----|-----|
| `Application.api(name=..., port=...)` | `FastAPI()` + `create_health_router(...)` + `create_metrics(...)` |
| `Application.daemon(name=...)` | `from scalo import logger, config, runtime` + your loop |
| `Application.cli(name=...)` | `from scalo.cli import ServiceApp` (Typer-based) |
| `app.profile_overrides({...})` | `scalo.config` 7-layer cascade -- env / `settings.<env>.yaml` |
| `app.runtime.paths` | `from scalo.runtime import get_runtime_paths` |
| `app.metrics` | `from scalo.metrics import create_metrics` |
| `app.health` | `from scalo.health import HealthManager` |
| `app.logger` | `from scalo.logger import logger` |

The composed pieces are the same ones the framework was wrapping. You
lose the single-import constructor; you gain explicit wiring with no
hidden globals.

---

## Canonical compose pattern

The full recipe lives in [INTEGRATION.md](../INTEGRATION.md) steps
1-9. Condensed:

```python
from fastapi import FastAPI
from scalo.config import settings
from scalo.logger import logger, info
from scalo.metrics import create_metrics
from scalo.health import HealthManager, create_health_router
from scalo.runtime import get_runtime_paths

# 1. Runtime context -- paths, container detection
paths = get_runtime_paths("my-service")

# 2. Config -- 7-layer cascade, already loaded at import
brokers = settings.get("kafka.brokers", "localhost:9092")

# 3. Logger -- structured, autodetects JSON / TTY
info("Service starting", version="2.28.3", config_dir=str(paths.config_dir))

# 4. Metrics -- Prometheus + OTel, /metrics endpoint
m = create_metrics("my_service")
requests = m.counter("requests_total", "Total requests", ["method", "status"])

# 5. Health -- /livez and /readyz
health = HealthManager()
app = FastAPI()
app.include_router(create_health_router(health))

# 6. Mark ready once dependencies are up
@app.on_event("startup")
async def startup():
    await connect_deps()
    health.set_ready()
```

That covers config + logger + metrics + health + runtime in a
handful of lines, with no framework in between.

---

## Why the framework was dropped

- **Not used in production.** Every DFE service composes the core
  modules directly.
- **Premature abstraction.** The factory methods (`api` / `daemon` /
  `cli`) bundled decisions -- port, lifecycle, signal handling, FastAPI
  app instance -- that real services need to make themselves.
- **Profile-override layer duplicated the 7-layer config cascade.**
  `profile_overrides({...})` was a fifth way to override settings on
  top of CLI / env / `.env` / `settings.<env>.yaml` / `settings.yaml` /
  defaults. One way is enough.
- **Hidden globals.** The framework owned the `FastAPI` app and the
  signal handlers. Composing yourself makes the wiring obvious.

The pieces it wired weren't wrong -- they were each useful in
isolation. Stripping the wrapper means you import what you need and
nothing else.

---

## Migration cheat sheet

If you have old `Application`-based code (none of this should be in
production, but if you're porting a spike):

```python
# Before
from scalo import Application
app = Application.api(name="my-service", port=8000)
app.metrics.counter("requests_total", "...", ["method"])
app.health.set_ready()
paths = app.runtime.paths
```

```python
# After
from fastapi import FastAPI
from scalo.metrics import create_metrics
from scalo.health import HealthManager, create_health_router
from scalo.runtime import get_runtime_paths

app = FastAPI()
health = HealthManager()
app.include_router(create_health_router(health))

m = create_metrics("my_service")
m.counter("requests_total", "...", ["method"])
paths = get_runtime_paths("my-service")
health.set_ready()
```

Run with uvicorn / hypercorn / gunicorn as you would any FastAPI app
-- the framework used to pick the runner for you; now you pick.

For CLI tools, use [api/CLI.md](../api/CLI.md) -- the Typer-based
`ServiceApp` is the supported replacement for `Application.cli()`
(`DfeApp` remains as a deprecated alias).

---

## When the framework returns

The package docstring states it "may return in a future version once
the design is mature." If it does:

- It will be additive -- compose-the-modules will keep working.
- It will likely be a *thin* wrapper that picks the FastAPI app,
  signal handlers, and shutdown ordering, not a config-override layer.
- Subscribe to the [scalo changelog] for the announcement.

[scalo changelog]: https://github.com/hyperi-io/scalo-py/releases

Until then -- compose directly.

---

## Related

- [../README.md](../README.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../architecture.md](../architecture.md)
- [../AUTO-WIRING.md](../AUTO-WIRING.md)
- [RUNTIME-CONTEXT.md](RUNTIME-CONTEXT.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../api/CLI.md](../api/CLI.md)
