# Directory config

A YAML-directory configuration store where each file is a "table" (database-style). In-memory cache, background polling refresh, optional git tracking for writes. Git goes through `dulwich`, so no `git` binary is needed. Ships in the base package.

```python
from scalo.config import DirectoryConfigStore
```

---

## Quick start

```python
from scalo.config import DirectoryConfigStore

store = DirectoryConfigStore("/config/app", refresh_interval=30)
store.start()
host = store.get("loaders/ingest-loader", "database.host")
store.stop()
```

---

## When to reach for this

`DirectoryConfigStore` complements the standard 7-layer config cascade
(see [`../core-pillars/config.md`](../core-pillars/config.md)). Use it
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

```text
/config/app/
├── globals.yaml                  # table: "globals"
├── loaders/
│   ├── ingest-loader.yaml       # table: "loaders/ingest-loader"
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
loader_cfg = store.get("loaders/ingest-loader")

# One key via dot notation
host = store.get("loaders/ingest-loader", "database.host")
port = store.get("loaders/ingest-loader", "database.port", default=5432)

# Discover what's there
tables = store.list_tables()
# ["globals", "loaders/ingest-loader", "loaders/kafka-loader",
#  "monitoring/alerts/thresholds"]
```

A whole-table read returns a shallow copy, and a keyed read returns the cached value itself, so mutating a nested dict you got back changes the cache for every reader. Copy it (`copy.deepcopy`) before you change it. Reads are thread-safe via an `RLock`.

---

## Writing

```python
store.set(
    "loaders/ingest-loader",
    "database.host",
    "new-host",
    message="rotate db host post-migration",
    author="Ops <ops@example.com>",
)

store.delete("loaders/ingest-loader", "database.password",
             author="Ops <ops@example.com>")
```

Writes hold an exclusive advisory lock (`fcntl.LOCK_EX`) on the table's directory from the read to the write, write the YAML to a temporary sibling and rename it over the table, refresh the cache slot, commit to git if the directory is a repo, and fire change callbacks. Subdirectories are created automatically on first write to a new table. A write to a table whose file is not a YAML mapping raises `ValueError`, and one whose file cannot be read raises the `OSError`, leaving the file as it was rather than replacing it with the one new key.

Read-only stores raise `PermissionError` on writes. Writability is auto-detected from filesystem permissions, and `writable=True` or `writable=False` overrides it. `delete()` raises `KeyError` for a missing table or key.

---

## Git awareness

If the directory is inside a git repo, writes auto-commit through `dulwich`. Commit messages default to `config: set <table>.<key>` and `config: delete <table>.<key>`, and `message=...` overrides one per call. The `author` argument follows the standard `"Name <email>"` format.

```python
store = DirectoryConfigStore(
    "/config/app",
    git_branch="staging",   # checkout on init; create if missing
    git_push=True,          # push to origin after each commit
)

store.list_branches()       # ["main", "staging", "release/2025-q4"]
store.switch_branch("main") # switch + refresh cache
store.switch_branch("experiments/new-rules", create=True)
```

`switch_branch` refreshes the cache after switching, because files on the new branch may differ. `git_push` pushes the current branch to `origin` after every commit. A push that fails is logged at ERROR and the change stays in the local repo.

| Property | Meaning |
|----------|---------|
| `store.is_git` | Whether the directory is inside a git repo. |
| `store.current_branch` | Current branch name (None for detached HEAD or non-repo). |

---

## Hot-reload via background polling

```python
store = DirectoryConfigStore("/config/app", refresh_interval=30)
store.start()
```

A daemon thread polls every `refresh_interval` seconds. When a file's mtime changes, the store reparses it and fires registered callbacks. Set `refresh_interval=0` to disable polling, in tests or when you would rather call the private `store._refresh_all()` from a SIGHUP handler.

Polling works over NFS, FUSE and ConfigMap subPath mounts, where filesystem events such as `inotify` are unreliable.

---

## Change callbacks

```python
def on_loader_change(table: str, data: dict) -> None:
    logger.info("Loader config changed", table=table)
    loader.reload(data)

store.on_change("loaders/ingest-loader", on_loader_change)
```

Callbacks fire from the polling thread when the new YAML parses successfully **and** the contents differ from what was cached. Callback exceptions are caught and logged at ERROR, so one bad callback doesn't break refresh for everyone else.

They also fire on `set()` and `delete()`, from the calling thread, so a service can update its own config and react in the same callback.

---

## Lifecycle

```python
# Context manager -- calls start() / stop() for you
with DirectoryConfigStore("/config/app") as store:
    host = store.get("loaders/ingest-loader", "database.host")

# Manual
store = DirectoryConfigStore("/config/app")
store.start()
try:
    ...
finally:
    store.stop()    # joins refresh thread (10 s timeout), closes git repo
```

---

## Safety

- Table names are normalised and checked: backslashes become slashes, leading and trailing slashes go, and `..` or an empty name raises `ValueError`.
- YAML is loaded with PyYAML's safe loader, so a file cannot construct arbitrary objects.
- A file that fails to parse keeps the last good cached version and logs a WARNING, so a config error doesn't take down the service.
- Two writers, in one process or several, serialise on the directory lock, so neither loses the other's update.
- A table is replaced by rename, so a reader, the refresh thread included, sees the whole old file or the whole new one. A half-written `.<table>.yaml.*.tmp` is never read as a table.

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

- [../core-pillars/config.md](../core-pillars/config.md)
- [secrets.md](secrets.md)
- [../integration.md](../integration.md)
- [../runtime/runtime-context.md](../runtime/runtime-context.md)
- [../extras-flags.md](../extras-flags.md)
