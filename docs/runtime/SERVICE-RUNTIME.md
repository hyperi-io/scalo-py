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
| `Application.daemon(name=...)` | `from hyperi_pylib import logger, config, runtime` + your loop |
| `Application.cli(name=...)` | `from hyperi_pylib.cli import DfeApp` (Typer-based) |
| `app.profile_overrides({...})` | `hyperi_pylib.config` 8-layer cascade -- env / `settings.<env>.yaml` |
| `app.runtime.paths` | `from hyperi_pylib.runtime import get_runtime_paths` |
| `app.metrics` | `from hyperi_pylib.metrics import create_metrics` |
| `app.health` | `from hyperi_pylib.health import HealthManager` |
| `app.logger` | `from hyperi_pylib.logger import logger` |

The composed pieces are the same ones the framework was wrapping. You
lose the single-import constructor; you gain explicit wiring with no
hidden globals.

---

## Canonical compose pattern

The full recipe lives in [INTEGRATION.md](../INTEGRATION.md) steps
1-9. Condensed:

```python
from fastapi import FastAPI
from hyperi_pylib.config import settings
from hyperi_pylib.logger import logger, info
from hyperi_pylib.metrics import create_metrics
from hyperi_pylib.health import HealthManager, create_health_router
from hyperi_pylib.runtime import get_runtime_paths

# 1. Runtime context -- paths, container detection
paths = get_runtime_paths("my-service")

# 2. Config -- 8-layer cascade, already loaded at import
brokers = settings.get("kafka.brokers", "localhost:9092")

# 3. Logger -- structured, autodetects JSON / TTY
info("Service starting", version="2.28.3", config_dir=str(paths.config_dir))

# 4. Metrics -- Prometheus + OTel, /metrics endpoint
m = create_metrics(namespace="my_service")
requests = m.counter("requests_total", "Total requests", ["method", "status"])

# 5. Health -- /health/live, /health/ready, /health/startup
health = HealthManager()
app = FastAPI()
app.include_router(create_health_router(health))

# 6. Mark ready once dependencies are up
@app.on_event("startup")
async def startup():
    await connect_deps()
    health.set_ready()
```

That covers config + logger + metrics + health + runtime in
roughly 20 lines, with no framework in between.

---

## Why the framework was dropped

- **Not used in production.** Every DFE service composes the core
  modules directly.
- **Premature abstraction.** The factory methods (`api` / `daemon` /
  `cli`) bundled decisions -- port, lifecycle, signal handling, FastAPI
  app instance -- that real services need to make themselves.
- **Profile-override layer duplicated the 8-layer config cascade.**
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
from hyperi_pylib import Application
app = Application.api(name="my-service", port=8000)
app.metrics.counter("requests_total", "...", ["method"])
app.health.set_ready()
paths = app.runtime.paths
```

```python
# After
from fastapi import FastAPI
from hyperi_pylib.metrics import create_metrics
from hyperi_pylib.health import HealthManager, create_health_router
from hyperi_pylib.runtime import get_runtime_paths

app = FastAPI()
health = HealthManager()
app.include_router(create_health_router(health))

m = create_metrics(namespace="my_service")
m.counter("requests_total", "...", ["method"])
paths = get_runtime_paths("my-service")
health.set_ready()
```

Run with uvicorn / hypercorn / gunicorn as you would any FastAPI app
-- the framework used to pick the runner for you; now you pick.

For CLI tools, use [api/CLI.md](../api/CLI.md) -- the Typer-based
`DfeApp` is the supported replacement for `Application.cli()`.

---

## When the framework returns

The package docstring states it "may return in a future version once
the design is mature." If it does:

- It will be additive -- compose-the-modules will keep working.
- It will likely be a *thin* wrapper that picks the FastAPI app,
  signal handlers, and shutdown ordering, not a config-override layer.
- Subscribe to the [hyperi-pylib changelog] for the announcement.

[hyperi-pylib changelog]: https://github.com/hyperi-io/hyperi-pylib/releases

Until then -- compose directly.

---

## Related

- [../README.md](../README.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../ARCHITECTURE.md](../ARCHITECTURE.md)
- [../AUTO-WIRING.md](../AUTO-WIRING.md)
- [RUNTIME-CONTEXT.md](RUNTIME-CONTEXT.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../api/CLI.md](../api/CLI.md)
