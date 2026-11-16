# Runtime Context

Container vs bare-metal detection and container-aware path resolution.
One import, identical code in K8s, Docker, and local development.

```python
from scalo.runtime import get_runtime_paths

paths = get_runtime_paths("my-app")
config_file = paths.config_dir / "app.yaml"   # /app/config in container, ~/.my-app/config locally
data_file   = paths.data_dir / "state.db"     # /app/data,                ~/.my-app/data
cache_file  = paths.cache_dir / "warmup.json" # /app/cache,               ~/.my-app/cache
```

Each `get_runtime_paths()` call runs detection again and creates the directories unless `ensure_dirs=False`. Nothing is cached.

## Environment detection

`RuntimeEnvironment._is_container()` walks seven indicators in
descending order of confidence and returns the first match. The matched
method is stamped into `RuntimePaths.detection_method` for audit trails.

| Order | Indicator | Method tag |
|------:|-----------|------------|
| 1 | `/var/run/secrets/kubernetes.io/serviceaccount` exists | `k8s_serviceaccount` |
| 2 | `KUBERNETES_SERVICE_HOST` env var set | `kubernetes` |
| 3 | `/.dockerenv` exists | `dockerenv` |
| 4 | `/proc/1/cgroup` or `/proc/self/cgroup` contains `/docker/`, `/kubepods`, `/lxc/`, `/containerd/` or a `docker-<64 hex>.scope` | `cgroups_cgroup` |
| 5 | The mount at `/` in `/proc/self/mountinfo` is an overlay with options naming `docker`, `containerd` or `kubelet` | `mountinfo` |
| 6 | `container` / `DOCKER_CONTAINER` / `ECS_CONTAINER_METADATA_URI` env var set | `env_<var>` |
| 7 | PID 1 with `/proc/1/comm` not in `systemd` / `init` / `launchd` | `pid1_<comm>` |

If none match -- bare-metal local mode (`detection_method="local"`).

Checks 1 to 6 are the same ones `get_mount_config()` uses, and check 7 runs here and nowhere else.

The order is by confidence: K8s and Docker markers first, the cgroup and the root mount next, env vars and PID 1 last. A container that hides every indicator above PID 1 is still detected when its process runs as init.

Container evidence is all that counts. A host's daemon cgroups (`docker.service`, `containerd.service`) and the container mounts a docker host lists in its mountinfo do not match, so a developer machine that runs docker stays in local mode.

`RuntimeEnvironment` is the detection class. It reports a boolean (`is_container`) plus the `detection_method` tag, and K8s and Docker get the same container path set. `scalo.config.get_environment()` names the kind instead: `kubernetes`, `docker`, `container` or `bare_metal`, from the same checks run once at import.

To branch on K8s from the paths, check the tag:

```python
paths = get_runtime_paths("my-app")
if paths.detection_method.startswith("k8s") or paths.detection_method == "kubernetes":
    # K8s-specific path
    ...
```

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
`scalo.secrets.SecretsManager` -- file-backed providers can
point at `config_dir / "secrets"` or a K8s `Secret` mount path of your
choosing.

## Path layout by mode

In container mode (`is_container=True`) the base path defaults to `/app`, overridable via `CONTAINER_BASE_PATH`.

| Field | Path | K8s volume kind |
|-------|------|-----------------|
| `config_dir` | `{base}/config` | ConfigMap (read-only) |
| `data_dir` | `{base}/data` | PersistentVolumeClaim |
| `temp_dir` | `{base}/tmp` | EmptyDir |
| `cache_dir` | `{base}/cache` | EmptyDir or PVC |
| `run_dir` | `/run/{app_name}` | EmptyDir or `medium: Memory` |
| `log_dir` | `None` | stdout / stderr (container runtime captures) |

`CONTAINER_BASE_PATH` lets you mount at `/mnt`, `/srv`, `/opt/app`,
etc. without code changes:

```bash
CONTAINER_BASE_PATH=/mnt python -m my_app
# config_dir = /mnt/config, data_dir = /mnt/data, ...
```

In local mode, as a non-root user:

| Field | Path |
|-------|------|
| `config_dir` | `~/.{app}/config` |
| `data_dir` | `~/.{app}/data` |
| `temp_dir` | `{tmp}/{app}-{uid}`, where `{tmp}` is the system temp dir (`$TMPDIR`, else `/tmp`), and the UID suffix keeps users apart |
| `cache_dir` | `~/.{app}/cache` |
| `log_dir` | `~/.{app}/logs` |
| `run_dir` | `None` (non-root doesn't typically use `/run`) |

In local mode, as root or a system daemon:

| Field | Path |
|-------|------|
| `config_dir` | `/etc/{app}` |
| `data_dir` | `/var/lib/{app}` |
| `temp_dir` | `{tmp}/{app}` |
| `cache_dir` | `/var/cache/{app}` |
| `log_dir` | `/var/log/{app}` |
| `run_dir` | `/run/{app}` |

Root detection: `os.getuid() == 0` on Unix. Platforms without `getuid` (Windows) get the non-root paths, with the login name in place of the UID.

`CONTAINER_BASE_PATH` rebases every container path but `run_dir`, which stays at `/run/{app}` to line up with systemd and `tmpfs` conventions. It is read bare, whatever the env prefix:

```python
# Default
RuntimeEnvironment("myapp", force_mode="container").detect_runtime().config_dir  # Path('/app/config')

# Override
os.environ["CONTAINER_BASE_PATH"] = "/mnt"
RuntimeEnvironment("myapp", force_mode="container").detect_runtime().config_dir  # Path('/mnt/config')
```

Use it for multi-tenant images that mount under `/mnt/<tenant>`, a shared `/opt/app` layout across services, or a test that points a forced-container layout at a pytest `tmp_path`.

## Directories and forced modes

`RuntimeEnvironment.ensure_directories(paths, create_config=False)` creates `data_dir` and `temp_dir` always, and raises `RuntimeError` when it cannot. It creates `log_dir`, `effective_cache_dir` and `run_dir` when they are set, and logs a warning on failure. It creates `config_dir` with `create_config=True` or outside a container, and not otherwise, because a container mounts that directory and creating it would hide the mount.

`get_runtime_paths(app_name, ensure_dirs=True)` (the default) calls this for you.

`force_mode` bypasses detection entirely:

```python
from scalo.runtime import RuntimeEnvironment

# Container layout, regardless of host
paths = RuntimeEnvironment("my-app", force_mode="container").detect_runtime()

# Local layout, regardless of host (useful for K8s integration test runners)
paths = RuntimeEnvironment("my-app", force_mode="local").detect_runtime()
```

`force_mode` skips the seven-indicator walk, and the resulting `detection_method` is `"forced"` (container) or `"local"` (local). Combine it with `monkeypatch.setenv("CONTAINER_BASE_PATH", str(tmp_path))` to redirect a forced-container test into a pytest `tmp_path`.

## Deployment cheat sheet

K8s:

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

Docker Compose:

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

Local dev:

```bash
python -m my_app          # uses ~/.my-app/config, ~/.my-app/data, $TMPDIR/my-app-{uid}, ...
```
