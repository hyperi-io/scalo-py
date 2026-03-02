# Application Profiles

Profile-based configuration for different deployment environments.

## Overview

hyperi-pylib applications support three deployment profiles:

- **dev**: Local development
- **docker**: CI/CD and integration testing
- **prod**: Production Kubernetes deployment

Profiles enable the same application code to run in different environments with appropriate settings for each context.

## Profile Comparison

| Feature | dev | docker | prod |
|---------|-----|--------|------|
| **Logging Format** | console | json | json |
| **Logging Level** | DEBUG | INFO | INFO |
| **Colored Logs** | Yes | No | No |
| **Health Checks** | Disabled | Enabled | Enabled |
| **Metrics** | Disabled | Enabled | Enabled |
| **Hot Reload** | Yes | No | No |
| **Graceful Shutdown** | Yes | Yes | Yes |
| **Shutdown Timeout** | 30s | 30s | 30s |

## Profile Details

### dev Profile

Local development with developer-friendly output:

```python
app = Application.api(name="my-api", profile="dev")
```

**Features:**

- Console logging with colors
- DEBUG level logs
- Hot reload enabled (where supported)
- No health check server (not needed locally)
- No metrics collection (not needed locally)
- Graceful shutdown still works (Ctrl+C)

**Use Cases:**

- Local development with hot reload
- Debugging with verbose logs
- Testing without metrics overhead

### docker Profile

CI/CD pipelines and integration testing:

```python
app = Application.daemon(name="worker", profile="docker")
```

**Features:**

- JSON structured logging
- INFO level logs (cleaner output)
- Health check HTTP server on port 8080
- Metrics collection enabled
- No hot reload (containers are immutable)

**Use Cases:**

- GitHub Actions / GitLab CI
- Docker Compose integration tests
- Pre-production validation

### prod Profile

Production Kubernetes deployment:

```python
app = Application.api(name="api", profile="prod")
```

**Features:**

- JSON structured logging for log aggregation
- INFO level logs
- Health check endpoints for k8s probes
  - `/health` - Liveness probe
  - `/ready` - Readiness probe (with dependency checks)
- Metrics for Prometheus scraping
- Graceful shutdown (waits for in-flight requests)
- Kubernetes-specific timing:
  - `readiness_initial_delay`: 5s
  - `liveness_initial_delay`: 30s
  - `startup_initial_delay`: 0s

**Use Cases:**

- Production Kubernetes clusters
- HELM deployments
- KEDA autoscaling
- ArgoCD GitOps

## Profile Overrides

Override specific settings while keeping profile defaults:

```python
app = Application.daemon(
    name="worker",
    profile="prod",
    profile_overrides={
        "health_check_port": 9000,  # Change from default 8080
        "metrics_port": 9001,       # Change from default 9090
        "shutdown_timeout": 60,     # Increase from 30s
        "logging": {
            "level": "WARNING"      # Less verbose in prod
        }
    }
)
```

## Environment Variables

Override profile at runtime:

```bash
# Override in container
HYPERI_LIB_PROFILE=prod python -m my_app serve

# Override in k8s manifest
env:
  - name: HYPERI_LIB_PROFILE
    value: "prod"
```

## Profile Selection

### CLI Flag

```bash
# Explicitly set profile
python -m my_app serve --profile prod

# Docker CMD
CMD ["python", "-m", "my_app", "serve", "--profile", "prod"]
```

### Constructor Argument

```python
app = Application.api(
    name="my-api",
    version="1.0.0",
    profile="prod"  # Explicit in code
)
```

### Environment Variable

```bash
export HYPERI_LIB_PROFILE=docker
python -m my_app serve  # Uses docker profile
```

**Priority**: CLI flag > Constructor arg > Environment variable > Default (dev)

## Profile Settings Reference

### Logging

```python
"logging": {
    "format": "console" | "json",
    "level": "DEBUG" | "INFO" | "WARNING" | "ERROR",
    "colors": True | False
}
```

### Health Checks

```python
"health_check": True | False,
"health_check_port": 8080,  # HTTP server port
"readiness_initial_delay": 5,   # k8s readiness probe delay
"liveness_initial_delay": 30,   # k8s liveness probe delay
"startup_initial_delay": 0      # k8s startup probe delay
```

### Metrics

```python
"metrics": True | False,
"metrics_port": 9090  # Prometheus scrape port
```

### Shutdown

```python
"graceful_shutdown": True | False,
"shutdown_timeout": 30  # Max seconds to wait for cleanup
```

### Development

```python
"reload": True | False  # Hot reload (where supported)
```

## Best Practices

### Development

```python
# Use dev profile for local work
if __name__ == "__main__":
    app = Application.api(name="my-api", profile="dev")
    app.run()  # Runs with hot reload, colored logs
```

### Testing

```python
# Use docker profile in tests
@pytest.fixture
def app():
    return Application.daemon(name="test-worker", profile="docker")
```

### Production

```dockerfile
# Dockerfile - use prod profile
CMD ["python", "-m", "my_app", "serve", "--profile", "prod"]
```

```yaml
# Kubernetes - explicit profile
containers:
  - name: api
    image: my-api:1.0.0
    command: ["python", "-m", "my_api", "serve", "--profile", "prod"]
    ports:
      - containerPort: 8000  # API port
      - containerPort: 8080  # Health check port
      - containerPort: 9090  # Metrics port
```

## Custom Profiles

Define custom profiles for special environments:

```python
from hyperi_pylib.application.profiles import PROFILES

# Add staging profile (between docker and prod)
PROFILES["staging"] = {
    **PROFILES["docker"],  # Start with docker profile
    "logging": {"level": "INFO"},
    "metrics": True,
    "health_check": True
}

app = Application.api(name="my-api", profile="staging")
```

## Troubleshooting

### Health checks not working

**Problem**: `/health` returns 404

**Solution**: Check profile enables health checks:

```python
app = Application.daemon(profile="prod")  # prod enables health checks
# NOT: profile="dev" (dev disables health checks)
```

### Metrics not collected

**Problem**: `/metrics` returns 404

**Solution**: Enable metrics in profile:

```python
app = Application.api(
    profile="prod",  # prod enables metrics
    # OR
    profile_overrides={"metrics": True}
)
```

### Wrong log format

**Problem**: Logs are JSON but need console output

**Solution**: Use dev profile or override:

```python
app = Application.api(
    profile="prod",
    profile_overrides={"logging": {"format": "console", "colors": True}}
)
```

## See Also

- [Container Deployment](CONTAINER_DEPLOYMENT.md) - Docker and k8s guides
- [Kubernetes Integration](KUBERNETES.md) - HELM charts, KEDA scaling
- [API Applications](APP-API.md) - FastAPI services
- [Daemon Applications](APP-DAEMON.md) - Background workers
