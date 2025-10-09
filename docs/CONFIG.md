# Hyperlib Configuration Guide

## Overview

Hyperlib provides intelligent, container-aware configuration management that automatically detects and adapts to your deployment environment (Kubernetes/HELM, Docker, or bare metal). It follows industry-standard conventions while remaining flexible and override-friendly.

## Key Features

- **Auto-detection** of runtime environment (K8s, Docker, bare metal)
- **HELM-aware** configuration with standard mount points
- **Docker-compatible** paths and secrets management
- **Zero-config deployment** - works out of the box
- **Override-friendly** - explicit config always wins
- **Database configuration** helpers for common databases
- **Standard environment variables** detection

## Quick Start

```python
from hyperlib import config

# Auto-detects environment and configures paths
print(f"Environment: {config.get_environment()}")  # kubernetes, docker, or bare_metal
print(f"Mounts: {config.get_mount_config()}")      # Standard mount paths

# Access configuration
settings = config.get_settings()  # Dynaconf settings object
db_config = config.get_database_config("postgresql")  # Database config
```

## Environment Detection

Hyperlib automatically detects your runtime environment:

| Environment | Detection Method |
|------------|------------------|
| Kubernetes | `/var/run/secrets/kubernetes.io/serviceaccount/token` exists |
| Docker | `/.dockerenv` file exists |
| Container | `/proc/1/cgroup` contains "docker" or "containerd" |
| Bare Metal | Default when none of the above |

### Manual Override

```bash
# Disable auto-detection
export HYPERLIB_AUTO_DETECT=false

# Enable debug output
export HYPERLIB_DEBUG=1
```

## Mount Paths

### Standard Mount Points

Hyperlib detects and uses standard mount points based on your environment:

#### HELM Deployments (Kubernetes)

| Mount Type | Standard Path | Usage | K8s Resource |
|------------|---------------|-------|--------------|
| config_dir | `/config` | Application configuration | ConfigMap |
| secrets_dir | `/secrets` | Sensitive data | Secret |
| data_dir | `/data` | Persistent data | PersistentVolumeClaim |
| logs_dir | `/logs` | Application logs | PVC or EmptyDir |
| temp_dir | `/tmp` | Temporary files | EmptyDir |

#### Docker Deployments

| Mount Type | Standard Path | Usage |
|------------|---------------|-------|
| config_dir | `/app/config` | Configuration files |
| secrets_dir | `/run/secrets` | Docker secrets |
| data_dir | `/app/data` | Persistent data |
| logs_dir | `/app/logs` | Application logs |
| temp_dir | `/tmp/{app_name}` | Temporary files |

#### Local Development

| Mount Type | Standard Path | Usage |
|------------|---------------|-------|
| config_dir | `~/.config/{app_name}` | User configuration |
| secrets_dir | `~/.{app_name}/secrets` | Local secrets |
| data_dir | `~/.local/share/{app_name}` | Application data |
| logs_dir | `~/.local/share/{app_name}/logs` | Log files |
| temp_dir | `/tmp/{app_name}` | Temporary files |

### Auto-Detection Priority

Hyperlib checks for existing directories in this order:

1. **HELM standard paths** (`/config`, `/secrets`, `/data`)
2. **Docker standard paths** (`/app/config`, `/run/secrets`)
3. **Linux standard paths** (`/etc/app`, `/var/lib/app`)
4. **Environment-specific defaults**

### Accessing Mount Paths

```python
from hyperlib.config import get_mount_config

mounts = get_mount_config()
print(f"Config: {mounts.config_dir}")
print(f"Secrets: {mounts.secrets_dir}")
print(f"Data: {mounts.data_dir}")
print(f"Logs: {mounts.logs_dir}")
print(f"Temp: {mounts.temp_dir}")
```

## Environment Variables

### Standard Variables Detection

Hyperlib automatically detects common environment variables:

```python
from hyperlib.config import get_standard_env_vars

env_vars = get_standard_env_vars()
# Returns detected variables from:
# - HELM (HELM_RELEASE_NAME, HELM_NAMESPACE)
# - Kubernetes (POD_NAME, NODE_NAME, POD_IP)
# - Docker (CONTAINER_ID, DOCKER_HOST)
# - Application (APP_NAME, APP_ENV, LOG_LEVEL)
# - Databases (POSTGRES_HOST, MYSQL_PORT, etc.)
```

### Database Configuration

Helper for database environment variables:

```python
from hyperlib.config import get_database_config

# Auto-detects POSTGRES_* environment variables
postgres_config = get_database_config("postgresql")
# Returns: {host, port, user, password, database, sslmode}

# Custom prefix
clickhouse_config = get_database_config("clickhouse", env_prefix="CH")
# Looks for CH_HOST, CH_PORT, CH_USER, etc.
```

### Application Configuration

```python
# Set custom app name (default: "app")
export HYPERLIB_APP_NAME=my-service

# Set custom env prefix (default: "APP")
export HYPERLIB_ENV_PREFIX=MYAPP
# Now looks for MYAPP_* environment variables
```

## Configuration Files

### Dynaconf Integration

Hyperlib uses Dynaconf for configuration management:

```python
from hyperlib.config import settings

# Access configuration values
api_key = settings.API_KEY
database_url = settings.get("DATABASE_URL", "postgresql://localhost/db")
```

### Configuration Sources (Priority Order)

1. **Command-line arguments** (highest priority)
2. **Environment variables** (`{ENV_PREFIX}_*`)
3. **`.env` file** (in working directory)
4. **Config files** (YAML/JSON in config_dir)
5. **Default values** (lowest priority)

### YAML Configuration

Hyperlib supports environment variable substitution in YAML:

```yaml
# config.yaml
database:
  host: ${POSTGRES_HOST:-localhost}
  port: ${POSTGRES_PORT:-5432}
  user: ${POSTGRES_USER:-postgres}
  password: ${POSTGRES_PASSWORD}

logging:
  level: ${LOG_LEVEL:-INFO}
  format: ${LOG_FORMAT:-json}
```

## HELM Deployment Example

### values.yaml

```yaml
# HELM values file
app:
  name: my-service

persistence:
  enabled: true
  size: 10Gi

config:
  mountPath: /config

secrets:
  mountPath: /secrets
```

### deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: {{ .Values.app.name }}
        env:
        - name: HELM_RELEASE_NAME
          value: {{ .Release.Name }}
        - name: APP_NAME
          value: {{ .Values.app.name }}
        volumeMounts:
        - name: config
          mountPath: /config
          readOnly: true
        - name: secrets
          mountPath: /secrets
          readOnly: true
        - name: data
          mountPath: /data
        - name: temp
          mountPath: /tmp
```

### Python Application

```python
from hyperlib.config import get_mount_config, get_environment
from hyperlib.logger import get_logger

logger = get_logger("my-service")

# Auto-detects HELM deployment
env = get_environment()  # Returns: "kubernetes"
mounts = get_mount_config()

logger.info(f"Running in {env} environment")
logger.info(f"Config dir: {mounts.config_dir}")  # /config
logger.info(f"Secrets dir: {mounts.secrets_dir}")  # /secrets
logger.info(f"Data dir: {mounts.data_dir}")  # /data
```

## Docker Deployment Example

### docker-compose.yml

```yaml
version: '3.8'
services:
  app:
    image: my-service:latest
    environment:
      - APP_NAME=my-service
      - LOG_LEVEL=INFO
      - POSTGRES_HOST=db
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
      - ./logs:/app/logs
    secrets:
      - db_password

  db:
    image: postgres:14
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

### Python Application

```python
from hyperlib.config import get_database_config, get_mount_config

# Auto-detects Docker environment
mounts = get_mount_config()
# config_dir: /app/config
# secrets_dir: /run/secrets
# data_dir: /app/data

# Auto-detects POSTGRES_* env vars
db_config = get_database_config("postgresql")
# Uses POSTGRES_HOST=db from docker-compose
```

## Migration Guide

### From Custom Configuration

#### Before (Custom Implementation)

```python
# 350+ lines of custom config code
import os
from pathlib import Path

class Config:
    def __init__(self):
        self.env = os.getenv("ENVIRONMENT", "development")

        if os.path.exists("/.dockerenv"):
            self.config_dir = Path("/app/config")
            self.data_dir = Path("/app/data")
        else:
            self.config_dir = Path.home() / ".config/myapp"
            self.data_dir = Path.home() / ".local/share/myapp"

        self.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        # ... dozens more lines
```

#### After (Hyperlib)

```python
# 5 lines with hyperlib
from hyperlib.config import get_mount_config, get_database_config

mounts = get_mount_config()  # Auto-detects paths
db_config = get_database_config("postgresql")  # Auto-detects env vars
```

### From hardcoded paths

#### Before

```python
LOG_DIR = "/app/logs"
CONFIG_FILE = "/app/config/settings.yaml"
TEMP_DIR = "/tmp"

# Breaks in local development!
```

#### After

```python
from hyperlib.config import get_mount_config

mounts = get_mount_config()
LOG_DIR = mounts.logs_dir  # /app/logs in Docker, ~/.local/share/app/logs locally
CONFIG_FILE = mounts.config_dir / "settings.yaml"
TEMP_DIR = mounts.temp_dir
```

## Advanced Usage

### Custom Mount Detection

```python
from hyperlib.config import detect_standard_mounts

# Returns dict of detected mount points
detected = detect_standard_mounts()
# {'config_dir': Path('/config'), 'data_dir': Path('/data'), ...}
```

### HELM Detection

```python
from hyperlib.config import detect_helm_deployment

if detect_helm_deployment():
    print("Running in HELM-deployed pod")
    # Use HELM-specific configuration
```

### Complete Container Information

```python
from hyperlib.config import get_container_config

info = get_container_config()
# Returns:
# {
#   'environment': 'kubernetes',
#   'app_name': 'my-service',
#   'mounts': {...},
#   'is_helm': True,
#   'standard_env': {...}
# }
```

### Multi-Environment Configuration

```python
from hyperlib.config import get_target_config

# Load environment-specific config
config = get_target_config("production")
# Reads from ~/.app/targets.yaml
```

## Best Practices

1. **Let auto-detection work** - Don't override unless necessary
2. **Use standard paths** - Follow HELM/Docker conventions
3. **Environment variables over files** - Easier in containers
4. **Secrets separate from config** - Use secrets_dir for sensitive data
5. **Log to stdout in containers** - Let K8s/Docker handle log aggregation

## Troubleshooting

### Debug Mode

```bash
export HYPERLIB_DEBUG=1
python app.py

# Output:
# Environment detected: Kubernetes
# HELM K8s mount paths detected
# Detected config_dir: /config
# Detected secrets_dir: /secrets
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Wrong environment detected | Set `HYPERLIB_AUTO_DETECT=false` and configure manually |
| Mount paths not found | Check directory exists and has correct permissions |
| Database config not working | Verify environment variables are set with correct prefix |
| HELM not detected | Ensure HELM_RELEASE_NAME is set or standard paths exist |

## Environment Variable Reference

### Hyperlib Control Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `HYPERLIB_AUTO_DETECT` | Enable auto-detection | `true` |
| `HYPERLIB_DEBUG` | Enable debug output | `false` |
| `HYPERLIB_APP_NAME` | Application name | `app` |
| `HYPERLIB_ENV_PREFIX` | Env var prefix | `APP` |

### Standard Container Variables

| Variable | Detected From | Usage |
|----------|---------------|-------|
| `HELM_RELEASE_NAME` | HELM | Release identifier |
| `KUBERNETES_NAMESPACE` | K8s | Namespace |
| `POD_NAME` | K8s | Pod identifier |
| `DOCKER_CONTAINER` | Docker | Container ID |
| `APP_ENV` | App | Environment name |
| `LOG_LEVEL` | App | Logging level |

### Database Variables

Pattern: `{PREFIX}_{SUFFIX}` where:
- Prefix: `POSTGRES`, `MYSQL`, `MONGO`, `REDIS`, `CLICKHOUSE`
- Suffix: `HOST`, `PORT`, `USER`, `PASSWORD`, `DATABASE`

## API Reference

### Core Functions

```python
# Environment detection
get_environment() -> str  # "kubernetes", "docker", or "bare_metal"
detect_helm_deployment() -> bool  # True if HELM detected

# Mount configuration
get_mount_config() -> MountConfig  # Auto-detected mount paths
detect_standard_mounts() -> dict  # Raw detected paths

# Configuration access
get_settings() -> Dynaconf  # Dynaconf settings object
get_container_config() -> dict  # Complete container info

# Database helpers
get_database_config(db_type: str, env_prefix: str = None) -> dict

# Environment variables
get_standard_env_vars() -> dict  # Detected standard vars
```

### Classes

```python
@dataclass
class MountConfig:
    config_dir: Optional[Path]   # Configuration files
    secrets_dir: Optional[Path]  # Secrets
    data_dir: Optional[Path]     # Persistent data
    temp_dir: Optional[Path]     # Temporary files
    logs_dir: Optional[Path]     # Log files
```

## Version History

- **v1.6.0** - Added HELM/Docker auto-detection, database helpers
- **v1.5.0** - Initial container-aware configuration