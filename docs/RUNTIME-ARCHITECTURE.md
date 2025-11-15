# HyperLib Runtime Architecture

Unified deployment model supporting both **containerized** and **local** environments.

## Problem Statement

Modern Python applications need to run in two very different environments:

1. **Development/Testing** - Local machine with user home directories
2. **Production** - Containers (Docker/K8s) with `/app` mount points

Hardcoding paths like `/app/config` breaks local development. Using `~/.config` breaks containers.

## Solution: Unified Runtime Environment

HyperLib provides automatic environment detection and unified path resolution:

```python
from hs_lib import get_runtime_paths

# Automatic detection
paths = get_runtime_paths("my-app")

# Same code works everywhere
config_file = paths.config_dir / "settings.yaml"
data_file = paths.data_dir / "database.db"
temp_file = paths.temp_dir / "cache.json"
```

**Container mode:**
- `config_dir` → `/app/config`
- `data_dir` → `/app/data`
- `temp_dir` → `/app/tmp`

**Local mode (non-root user):**
- `config_dir` → `~/.my-app/config`
- `data_dir` → `~/.my-app/data`
- `temp_dir` → `/tmp/my-app-{uid}`
- `log_dir` → `~/.my-app/logs`

**Local mode (root user):**
- `config_dir` → `/etc/my-app`
- `data_dir` → `/var/lib/my-app`
- `temp_dir` → `/tmp/my-app`
- `log_dir` → `/var/log/my-app`

## Path Semantics

### config_dir - Read-Only Configuration

**Container:** `/app/config` (Kubernetes ConfigMap)
- Mounted read-only
- Configuration files (YAML, JSON, etc.)
- Never write to this directory in production

**Local (non-root):** `~/.my-app/config` (daemon convention)
- Writable during development
- User-specific configuration

**Local (root):** `/etc/my-app` (system daemon convention)
- System-wide configuration
- Requires root privileges to modify

**Usage:**
```python
settings_file = paths.config_dir / "app.yaml"
with open(settings_file) as f:
    config = yaml.safe_load(f)
```

### data_dir - Persistent Storage

**Container:** `/app/data` (Kubernetes PersistentVolumeClaim)
- Survives pod restarts
- Database files, uploaded content, application state
- Backed by network storage (NFS, Ceph, EBS)

**Local (non-root):** `~/.my-app/data` (daemon convention)
- User-specific application data
- Survives between runs

**Local (root):** `/var/lib/my-app` (system daemon convention)
- System-wide application data
- Standard Unix daemon storage location

**Usage:**
```python
db_file = paths.data_dir / "app.db"
state_file = paths.data_dir / "last_sync.json"
uploads_dir = paths.data_dir / "uploads"
```

### temp_dir - Ephemeral Storage

**Container:** `/app/tmp` (Kubernetes EmptyDir)
- Deleted on pod restart
- Fast local SSD/RAM storage
- Temporary files, caches, processing

**Local (non-root):** `/tmp/my-app-{uid}` (user-isolated)
- Temporary files
- UID suffix prevents conflicts between users
- May be cleared by system

**Local (root):** `/tmp/my-app`
- System daemon temporary storage
- May be cleared by system

**Usage:**
```python
cache_file = paths.temp_dir / "download.tmp"
processing_dir = paths.temp_dir / "work"
```

### log_dir - Log Output

**Container:** `None` (stdout/stderr)
- Container runtime captures logs
- No log files needed
- Aggregated by Kubernetes/Docker

**Local (non-root):** `~/.my-app/logs` (daemon convention)
- File-based logging
- Rotated log files
- Useful for debugging

**Local (root):** `/var/log/my-app` (system daemon convention)
- System daemon logs
- Managed by log rotation
- Standard Unix logging location

**Usage:**
```python
if paths.log_dir:
    # Local mode - write log files
    log_file = paths.log_dir / "app.log"
else:
    # Container mode - use stdout
    # (hs-lib logger handles this automatically)
```

## Container Detection

HyperLib automatically detects container environments using multiple methods:

### Method 1: Docker (/.dockerenv)

```python
if Path("/.dockerenv").exists():
    # Running in Docker
```

### Method 2: Kubernetes (Environment Variable)

```python
if os.getenv("KUBERNETES_SERVICE_HOST"):
    # Running in Kubernetes pod
```

### Method 3: cgroups (Docker/K8s)

```python
with open("/proc/1/cgroup") as f:
    if "docker" in f.read() or "kubepods" in f.read():
        # Running in container
```

### Method 4: PID 1 (Init Process)

```python
if os.getpid() == 1:
    # Process running as PID 1 (container init)
```

## API Reference

### get_runtime_paths()

Convenience function for common usage:

```python
from hs_lib import get_runtime_paths

paths = get_runtime_paths("my-app", ensure_dirs=True)
```

**Parameters:**
- `app_name` (str): Application name (used in local paths)
- `ensure_dirs` (bool): Create directories if missing (default: True)

**Returns:** RuntimePaths dataclass

### RuntimeEnvironment

Advanced usage with custom detection:

```python
from hs_lib.runtime import RuntimeEnvironment

# Auto-detect
runtime = RuntimeEnvironment("my-app")
paths = runtime.detect_runtime()

# Force container mode (testing)
runtime = RuntimeEnvironment("my-app", force_mode="container")
paths = runtime.detect_runtime()

# Force local mode (testing)
runtime = RuntimeEnvironment("my-app", force_mode="local")
paths = runtime.detect_runtime()

# Create directories
runtime.ensure_directories(paths)
```

### RuntimePaths

Dataclass with path information:

```python
@dataclass
class RuntimePaths:
    config_dir: Path        # Read-only configuration
    data_dir: Path          # Persistent storage
    temp_dir: Path          # Ephemeral storage
    log_dir: Path | None    # Log files (None in containers)
    is_container: bool      # True if running in container
    detection_method: str   # How container was detected
```

## Integration with Application

### Application Factory Pattern

hs-lib.application already integrates RuntimePaths:

```python
from hs_lib import Application

# API application
app = Application.api(name="my-service", port=8000)

# Automatically uses RuntimePaths internally
# Container mode: /app/config, /app/data, /app/tmp
# Local mode (non-root): ~/.my-service/config, ~/.my-service/data, /tmp/my-service-{uid}
# Local mode (root): /etc/my-service, /var/lib/my-service, /var/log/my-service
```

### Manual Integration

For custom applications:

```python
from hs_lib import get_runtime_paths, Application

paths = get_runtime_paths("my-app")

# Use paths in your code
config = load_config(paths.config_dir / "settings.yaml")
db = open_database(paths.data_dir / "app.db")
cache = setup_cache(paths.temp_dir)

# Create application with custom paths
app = Application.daemon(
    name="my-app",
    # ... other config
)
```

## Cross-Platform Support

### Linux/Unix (Daemon/CLI Conventions)

**Non-root user:**
```
config_dir: ~/.appname/config
data_dir:   ~/.appname/data
temp_dir:   /tmp/appname-{uid}
log_dir:    ~/.appname/logs
```

**Root user (system daemon):**
```
config_dir: /etc/appname
data_dir:   /var/lib/appname
temp_dir:   /tmp/appname
log_dir:    /var/log/appname
```

### macOS (Daemon/CLI Conventions)

**Same as Linux** - Uses Unix daemon conventions:
```
config_dir: ~/.appname/config
data_dir:   ~/.appname/data
temp_dir:   /tmp/appname-{uid}  (non-root) or /tmp/appname (root)
log_dir:    ~/.appname/logs (non-root) or /var/log/appname (root)
```

### Windows (Not Currently Supported)

**Future support planned:**
```
config_dir: %APPDATA%\appname
data_dir:   %LOCALAPPDATA%\appname
temp_dir:   %LOCALAPPDATA%\appname\temp
log_dir:    %LOCALAPPDATA%\appname\logs
```

### Container (All Platforms)

```
config_dir: /app/config
data_dir:   /app/data
temp_dir:   /app/tmp
log_dir:    None (stdout)
```

## Deployment Examples

### Kubernetes Deployment

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: my-app
    image: my-app:1.0
    volumeMounts:
    - name: config
      mountPath: /app/config
      readOnly: true
    - name: data
      mountPath: /app/data
    - name: tmp
      mountPath: /app/tmp
  volumes:
  - name: config
    configMap:
      name: my-app-config
  - name: data
    persistentVolumeClaim:
      claimName: my-app-data
  - name: tmp
    emptyDir: {}
```

Application code automatically uses these mount points.

### Docker Compose

```yaml
services:
  my-app:
    image: my-app:1.0
    volumes:
      - ./config:/app/config:ro
      - app-data:/app/data
      - /tmp:/app/tmp
volumes:
  app-data:
```

### Local Development

```bash
# No configuration needed!
python -m my_app.main

# Automatically uses (non-root):
# ~/.my-app/config/
# ~/.my-app/data/
# /tmp/my-app-{uid}/
# ~/.my-app/logs/
```

## Testing

### Unit Tests

```python
from hs_lib.runtime import RuntimeEnvironment

def test_local_paths():
    runtime = RuntimeEnvironment("test-app", force_mode="local")
    paths = runtime.detect_runtime()

    assert "test-app" in str(paths.config_dir)
    assert paths.is_container is False

def test_container_paths():
    runtime = RuntimeEnvironment("test-app", force_mode="container")
    paths = runtime.detect_runtime()

    assert paths.config_dir == Path("/app/config")
    assert paths.is_container is True
```

### Integration Tests

```python
def test_app_works_in_both_modes():
    # Test local mode
    runtime_local = RuntimeEnvironment("test-app", force_mode="local")
    paths_local = runtime_local.detect_runtime()
    app = MyApp(paths_local)
    assert app.run()

    # Test container mode
    runtime_container = RuntimeEnvironment("test-app", force_mode="container")
    paths_container = runtime_container.detect_runtime()
    app = MyApp(paths_container)
    assert app.run()
```

## Migration Guide

### Before (Hardcoded Paths)

```python
# ❌ Breaks in containers
CONFIG_DIR = Path.home() / ".my-app/config"
DATA_DIR = Path.home() / ".my-app/data"

# ❌ Breaks in local development
CONFIG_DIR = Path("/app/config")
DATA_DIR = Path("/app/data")

# ❌ Doesn't support both root and non-root users
CONFIG_DIR = Path("/etc/my-app")  # Won't work for non-root
CONFIG_DIR = Path.home() / ".my-app/config"  # Won't work for root daemon
```

### After (Unified Runtime)

```python
from hs_lib import get_runtime_paths

# ✅ Works everywhere
paths = get_runtime_paths("my-app")
CONFIG_DIR = paths.config_dir
DATA_DIR = paths.data_dir
```

## Best Practices

1. **Never hardcode paths** - Always use RuntimePaths
2. **Respect read-only config** - Don't write to `config_dir` in production
3. **Use temp for ephemeral data** - Don't use `data_dir` for temporary files
4. **Check log_dir** - Handle both file and stdout logging
5. **Test both modes** - Use `force_mode` in tests

## Performance

- Detection runs once at startup (~1ms)
- Cached for application lifetime
- Zero overhead after initialization
- No runtime penalties

## Security

- **No privilege escalation** - Uses standard user paths
- **No secrets in code** - Configuration via ConfigMaps
- **Proper permissions** - Respects filesystem ACLs
- **Container isolation** - Follows K8s security model

## Future Enhancements

Potential future features:

- S3/cloud storage backends for `data_dir`
- Automatic ConfigMap watching for config updates
- Path validation and sanitization
- Custom path schemas per deployment type
- Integration with cloud-native storage (Rook, Longhorn)
