# Runtime Context

Container vs bare-metal detection and container-aware path resolution.
One import, identical code in K8s, Docker, and local development.

```python
from hyperi_pylib.runtime import get_runtime_paths

paths = get_runtime_paths("my-app")
config_file = paths.config_dir / "app.yaml"   # /app/config in container, ~/.my-app/config locally
data_file   = paths.data_dir / "state.db"     # /app/data,                ~/.my-app/data
cache_file  = paths.cache_dir / "warmup.json" # /app/cache,               ~/.my-app/cache
```

Detection runs once at startup and is cached for the process lifetime.

---

## Environment detection

`RuntimeEnvironment._is_container()` walks seven indicators in
descending order of confidence and returns the first match. The matched
method is stamped into `RuntimePaths.detection_method` for audit trails.

| Order | Indicator | Method tag |
|------:|-----------|------------|
| 1 | `/var/run/secrets/kubernetes.io/serviceaccount` exists | `k8s_serviceaccount` |
| 2 | `KUBERNETES_SERVICE_HOST` env var set | `kubernetes` |
| 3 | `/.dockerenv` exists | `dockerenv` |
| 4 | `/proc/1/cgroup` or `/proc/self/cgroup` contains `docker` / `kubepods` / `containerd` / `crio` | `cgroups_cgroup` |
| 5 | `/proc/self/mountinfo` contains `docker` / `kubelet` / `overlay` / `containerd` | `mountinfo` |
| 6 | `container` / `DOCKER_CONTAINER` / `ECS_CONTAINER_METADATA_URI` env var set | `env_<var>` |
| 7 | PID 1 with `/proc/1/comm` not in `systemd` / `init` / `launchd` | `pid1_<comm>` |

If none match -- bare-metal local mode (`detection_method="local"`).

The order matters. K8s and Docker indicators are 100% reliable;
cgroups and mountinfo are very reliable; env vars and PID 1 are
fallbacks. A container that hides every indicator above PID 1 will
still be detected when running as init.

---

## `RuntimeEnvironment` enum

`RuntimeEnvironment` is the detection class, not an enum. The
environment **kind** is a boolean (`is_container`) plus the
`detection_method` tag -- there is no `kubernetes` / `docker` /
`bare_metal` enum value. Both K8s and Docker collapse to the same
container path set; the tag distinguishes them for diagnostics.

If you need to branch on K8s specifically, check the tag:

```python
paths = get_runtime_paths("my-app")
if paths.detection_method.startswith("k8s") or paths.detection_method == "kubernetes":
    # K8s-specific path
    ...
```

---

## `RuntimePaths` fields

```python
@dataclass
class RuntimePaths:
    config_dir: Path             # read-only configuration
    data_dir: Path               # persistent storage
    temp_dir: Path               # ephemeral storage
    log_dir: Path | None = None  # file logs (None in containers -- stdout)
    cache_dir: Path | None = None # cache (falls back to data_dir/cache via .effective_cache_dir)
    run_dir: Path | None = None  # PID files, sockets (None for non-root local)

    is_container: bool = False
    detection_method: str = "unknown"
```

`effective_cache_dir` returns `cache_dir or data_dir / "cache"`. Use it
when you need a guaranteed cache path.

There is no `secrets_dir` field on `RuntimePaths`. Secrets live behind
`hyperi_pylib.secrets.SecretsManager` -- file-backed providers can
point at `config_dir / "secrets"` or a K8s `Secret` mount path of your
choosing.

---

## Path layout by mode

### Container mode (`is_container=True`)

Base path defaults to `/app`, overridable via `CONTAINER_BASE_PATH`.

| Field | Path | K8s volume kind |
|-------|------|-----------------|
| `config_dir` | `{base}/config` | ConfigMap (read-only) |
| `data_dir` | `{base}/data` | PersistentVolumeClaim |
| `temp_dir` | `{base}/tmp` | EmptyDir |
| `cache_dir` | `{base}/cache` | EmptyDir or PVC |
| `run_dir` | `/run/{app_name}` | EmptyDir or `medium: Memory` |
| `log_dir` | `None` | stdout / stderr (container runtime captures) |

`CONTAINER_BASE_PATH` lets you mount at `/mnt`, `/dfe`, `/opt/app`,
etc. without code changes:

```bash
CONTAINER_BASE_PATH=/mnt python -m my_app
# config_dir = /mnt/config, data_dir = /mnt/data, ...
```

### Local mode, non-root user

| Field | Path |
|-------|------|
| `config_dir` | `~/.{app}/config` |
| `data_dir` | `~/.{app}/data` |
| `temp_dir` | `/tmp/{app}-{uid}` (UID suffix prevents cross-user conflicts) |
| `cache_dir` | `~/.{app}/cache` |
| `log_dir` | `~/.{app}/logs` |
| `run_dir` | `None` (non-root doesn't typically use `/run`) |

### Local mode, root / system daemon

| Field | Path |
|-------|------|
| `config_dir` | `/etc/{app}` |
| `data_dir` | `/var/lib/{app}` |
| `temp_dir` | `/tmp/{app}` |
| `cache_dir` | `/var/cache/{app}` |
| `log_dir` | `/var/log/{app}` |
| `run_dir` | `/run/{app}` |

Root detection: `os.getuid() == 0` on Unix; falls through to non-root
paths on platforms without `getuid` (Windows).

---

## `CONTAINER_BASE_PATH` override

Single env var rebases every container path:

```python
# Default
RuntimeEnvironment("myapp").detect_runtime().config_dir  # Path('/app/config')

# Override
os.environ["CONTAINER_BASE_PATH"] = "/mnt"
RuntimeEnvironment("myapp").detect_runtime().config_dir  # Path('/mnt/config')
```

Use cases:

- Multi-tenant images that mount under `/mnt/<tenant>`
- Shared-base layouts (`/opt/app`) for fleets of services
- Migration from legacy mount paths without a code change
- Test harnesses pinning to a `tmp_path` under pytest

`run_dir` is **not** rebased -- it stays at `/run/{app}` so it lines
up with systemd / `tmpfs` conventions regardless of base.

---

## `ensure_directories()` behaviour

`RuntimeEnvironment.ensure_directories(paths, create_config=False)`:

- **`data_dir` and `temp_dir`** -- always created. Failure raises
  `RuntimeError` (these are required).
- **`log_dir`, `cache_dir`, `run_dir`** -- created if non-`None`.
  Failure logs a warning and continues (best-effort).
- **`config_dir`** -- created only if `create_config=True` **or** not in
  a container. Containers mount `config_dir` from a ConfigMap or
  Secret; creating it would mask the mount.

`get_runtime_paths(app_name, ensure_dirs=True)` (the default) calls
this for you.

---

## Forcing modes for testing

`force_mode` bypasses detection entirely:

```python
from hyperi_pylib.runtime import RuntimeEnvironment

# Container layout, regardless of host
paths = RuntimeEnvironment("my-app", force_mode="container").detect_runtime()

# Local layout, regardless of host (useful for K8s integration test runners)
paths = RuntimeEnvironment("my-app", force_mode="local").detect_runtime()
```

The `force_mode` skips the seven-indicator walk; the resulting
`detection_method` is `"forced"` (container) or `"local"` (local).

Combine with `monkeypatch.setenv("CONTAINER_BASE_PATH", str(tmp_path))`
to redirect a forced-container test into a pytest `tmp_path`.

---

## Deployment cheat sheet

### K8s

```yaml
volumeMounts:
- { name: config, mountPath: /app/config, readOnly: true }
- { name: data,   mountPath: /app/data }
- { name: tmp,    mountPath: /app/tmp }
- { name: cache,  mountPath: /app/cache }
volumes:
- { name: config, configMap: { name: my-app-config } }
- { name: data,   persistentVolumeClaim: { claimName: my-app-data } }
- { name: tmp,    emptyDir: {} }
- { name: cache,  emptyDir: {} }
```

### Docker Compose

```yaml
services:
  my-app:
    volumes:
      - ./config:/app/config:ro
      - app-data:/app/data
      - /tmp:/app/tmp
volumes:
  app-data:
```

### Local dev

```bash
python -m my_app          # uses ~/.my-app/config, ~/.my-app/data, /tmp/my-app-{uid}, ...
```

---

## Related

- [../README.md](../README.md)
- [../INTEGRATION.md](../INTEGRATION.md)
- [../ARCHITECTURE.md](../ARCHITECTURE.md)
- [../AUTO-WIRING.md](../AUTO-WIRING.md)
- [SERVICE-RUNTIME.md](SERVICE-RUNTIME.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../core-pillars/LOGGING.md](../core-pillars/LOGGING.md)
