# Directory config

A YAML-directory configuration store where each file is a "table"
(database-style). In-memory cache, background polling refresh, optional
git tracking for writes. Pure-Python git via `dulwich` — no `git`
binary required. Ships in the base package.

```python
from hyperi_pylib.config import DirectoryConfigStore
```

---

## Quick start

```python
from hyperi_pylib.config import DirectoryConfigStore

store = DirectoryConfigStore("/config/dfe", refresh_interval=30)
store.start()
host = store.get("loaders/dfe-loader", "database.host")
store.stop()
```

---

## When to reach for this

`DirectoryConfigStore` complements the standard 8-layer config cascade
(see [`../core-pillars/CONFIG.md`](../core-pillars/CONFIG.md)). Use it
when:

- You have many independent config "tables" (one per loader, alert
  ruleset, scoring profile) and don't want one giant `settings.yaml`.
- Operators edit configs at runtime and you want hot-reload.
- You want every change git-tracked with audit trail.
- A network-mounted directory (S3 FUSE, NFS, ConfigMap subPath) holds
  the truth.

The standard cascade is right when settings are mostly static and
loaded once. `DirectoryConfigStore` is right when configs are many,
dynamic, and editable.

---

## Table layout

Each YAML file is one table. Names use forward-slash paths:

```
/config/dfe/
├── globals.yaml                  # table: "globals"
├── loaders/
│   ├── dfe-loader.yaml          # table: "loaders/dfe-loader"
│   └── kafka-loader.yaml        # table: "loaders/kafka-loader"
└── monitoring/
    └── alerts/
        └── thresholds.yaml      # table: "monitoring/alerts/thresholds"
```

Both `.yaml` and `.yml` extensions are recognised.

---

## Reading

```python
# Whole table as a dict
loader_cfg = store.get("loaders/dfe-loader")

# One key via dot notation
host = store.get("loaders/dfe-loader", "database.host")
port = store.get("loaders/dfe-loader", "database.port", default=5432)

# Discover what's there
tables = store.list_tables()
# ["globals", "loaders/dfe-loader", "loaders/kafka-loader",
#  "monitoring/alerts/thresholds"]
```

Reads return deep copies — mutating the returned dict won't poison the
cache. Thread-safe via `RLock`.

---

## Writing

```python
store.set(
    "loaders/dfe-loader",
    "database.host",
    "new-host",
    message="rotate db host post-migration",
    author="derek@hyperi.io",
)

store.delete("loaders/dfe-loader", "database.password",
             author="derek@hyperi.io")
```

Writes take an advisory file lock (`fcntl.LOCK_EX`), update the YAML
file, refresh the cache slot, commit to git if the directory is a repo,
and fire change callbacks. Subdirectories are created automatically on
first write to a new table.

Read-only stores raise `PermissionError` on writes. Writability is
auto-detected from filesystem permissions; override with
`writable=True/False`.

---

## Git awareness

If the directory is inside a git repo, writes auto-commit through
`dulwich`. Commit messages default to `config: set <table>.<key>` —
override per call with `message=...`. The `author` argument follows the
standard `"Name <email>"` format.

```python
store = DirectoryConfigStore(
    "/config/dfe",
    git_branch="staging",   # checkout on init; create if missing
    git_push=True,          # push to origin after each commit
)

store.list_branches()       # ["main", "staging", "release/2025-q4"]
store.switch_branch("main") # switch + refresh cache
store.switch_branch("experiments/new-rules", create=True)
```

`switch_branch` refreshes the cache after switching — files on the new
branch may differ. `git_push` pushes the current branch to `origin`
after every commit; on push failure the change still lives locally and
gets logged at ERROR level.

| Property | Meaning |
|----------|---------|
| `store.is_git` | Whether the directory is inside a git repo. |
| `store.current_branch` | Current branch name (None for detached HEAD or non-repo). |

---

## Hot-reload via background polling

```python
store = DirectoryConfigStore("/config/dfe", refresh_interval=30)
store.start()
```

A daemon thread polls every `refresh_interval` seconds. When a file's
mtime changes, the store reparses it and fires registered callbacks.
Set `refresh_interval=0` to disable polling — useful in tests or when
you'd rather poke `store._refresh_all()` from a SIGHUP handler.

Polling beats `inotify` for two reasons: it works over NFS, FUSE, and
ConfigMap subPath mounts where filesystem events are unreliable; and
it survives the daemon thread being slow to spawn.

---

## Change callbacks

```python
def on_loader_change(table: str, data: dict) -> None:
    logger.info("Loader config changed", table=table)
    loader.reload(data)

store.on_change("loaders/dfe-loader", on_loader_change)
```

Callbacks fire from the polling thread when the new YAML parses
successfully **and** the contents actually differ from what was cached.
Callback exceptions are caught and logged — one bad callback doesn't
break refresh for everyone else.

Also fires on explicit `set()` / `delete()` operations, so a service can
update its own config and react in the same callback.

---

## Lifecycle

```python
# Context manager — calls start() / stop() for you
with DirectoryConfigStore("/config/dfe") as store:
    host = store.get("loaders/dfe-loader", "database.host")

# Manual
store = DirectoryConfigStore("/config/dfe")
store.start()
try:
    ...
finally:
    store.stop()    # joins refresh thread (10 s timeout), closes git repo
```

---

## Safety

- Table names go through `_validate_table_name`: backslashes normalised,
  leading/trailing slashes stripped, `..` rejected, empty rejected.
- YAML loaded via `yaml.safe_load` — no arbitrary object construction.
- Files that fail to parse keep the last good cached version and log a
  WARN — config errors don't take down the service.
- Writes use `fcntl.LOCK_EX` so concurrent writers from sibling
  processes don't tear a half-written file.

---

## Constructor reference

| Arg | Default | Meaning |
|-----|---------|---------|
| `directory` | required | Path to the YAML directory. |
| `refresh_interval` | `30` | Polling interval in seconds. `0` disables polling. |
| `writable` | auto | `None` = auto-detect from filesystem permissions. |
| `git_branch` | `None` | Checkout on init. Raises if directory isn't a git repo. |
| `git_push` | `False` | Push to `origin` after each commit. |

---

## Related

- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [DATABASE.md](DATABASE.md)
- [SECRETS.md](SECRETS.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../runtime/RUNTIME-CONTEXT.md](../runtime/RUNTIME-CONTEXT.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
