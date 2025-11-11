# Container Deployment Guide

Production-ready container deployment for Hyperlib applications.

## Quick Start

### 1. Create Application

```python
# src/my_app/__init__.py
from hyperlib import Application

app = Application.api(
    name="my-app",
    version="1.0.0",
    profile="prod"  # Container-native patterns enabled
)

@app.route("/")
def root():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run()
```

### 2. Create Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies (Derek's policy: include debug utils)
RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies with uv
RUN pip install uv && \
    uv sync --locked --no-dev

# Run as non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 8000 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s \
    CMD curl -f http://localhost:8080/health/live || exit 1

# Run application
CMD ["python", "-m", "my_app", "serve", "--profile", "prod"]
```

### 3. Build and Run

```bash
# Build image
docker build -t my-app:1.0.0 .

# Run container
docker run -p 8000:8000 -p 8080:8080 -p 9090:9090 my-app:1.0.0

# Test health endpoint
curl http://localhost:8080/health/live
# {"status":"healthy","service":"my-app"}

# Test metrics
curl http://localhost:9090/metrics
```

## Multi-Stage Builds

Optimize image size with build/runtime stages:

```dockerfile
# Build stage
FROM python:3.11 as builder

WORKDIR /build

# Install build dependencies
RUN pip install uv

# Copy and build
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --locked --no-dev

# Runtime stage
FROM python:3.11-slim

# Install runtime utilities (2-5% size increase, acceptable for debuggability)
RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src

# Run as non-root
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 8000 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s \
    CMD curl -f http://localhost:8080/health/live || exit 1

# Run
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "my_app", "serve", "--profile", "prod"]
```

## Port Configuration

### Standard Ports

| Port | Purpose | Protocol |
|------|---------|----------|
| 8000 | Application (API/HTTP) | HTTP |
| 8080 | Health checks | HTTP |
| 9090 | Prometheus metrics | HTTP |

### Custom Ports

Override in application:

```python
app = Application.api(
    name="my-app",
    port=3000,  # Application port
    profile="prod",
    profile_overrides={
        "health_check_port": 3001,
        "metrics_port": 3002
    }
)
```

Update Dockerfile:

```dockerfile
EXPOSE 3000 3001 3002
```

## Health Checks

### Docker Native

```dockerfile
HEALTHCHECK --interval=30s \
            --timeout=3s \
            --start-period=40s \
            --retries=3 \
    CMD curl -f http://localhost:8080/health/live || exit 1
```

### Custom Dependency Checks

```python
app = Application.daemon(name="worker", profile="prod")

@app.health_check
def check_database():
    try:
        db.ping()
        return True
    except Exception:
        return False

@app.health_check
def check_redis():
    try:
        redis.ping()
        return True
    except Exception:
        return False
```

Health check endpoints:
- `/health/live` - Liveness (always 200 if running)
- `/health/ready` - Readiness (503 if dependencies fail)

## Environment Variables

### Application Config

```dockerfile
ENV HYPERLIB_PROFILE=prod \
    HYPERLIB_LOGGING__LEVEL=INFO \
    DATABASE_URL=postgresql://localhost/mydb
```

### Runtime Override

```bash
docker run -e HYPERLIB_PROFILE=docker \
           -e DATABASE_URL=postgresql://db:5432/mydb \
           my-app:1.0.0
```

## Logging

### Structured JSON Logs

Production profiles output JSON for log aggregation:

```json
{
  "timestamp": "2025-11-10T17:30:00.123Z",
  "level": "INFO",
  "logger": "my_app",
  "message": "Request processed",
  "http_method": "GET",
  "http_path": "/api/users",
  "http_status": 200,
  "duration_ms": 45.2
}
```

### Log Collection

```bash
# View logs
docker logs my-app

# Follow logs
docker logs -f my-app

# With docker-compose
docker-compose logs -f api
```

## Secrets Management

### Environment Variables

```bash
docker run -e DATABASE_PASSWORD=$(cat /run/secrets/db_password) my-app:1.0.0
```

### Docker Secrets

```yaml
# docker-compose.yml
services:
  api:
    image: my-app:1.0.0
    secrets:
      - db_password
    environment:
      DATABASE_PASSWORD_FILE: /run/secrets/db_password

secrets:
  db_password:
    external: true
```

### Kubernetes Secrets

```yaml
env:
  - name: DATABASE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
```

## Docker Compose

### Development

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
      - "8080:8080"
      - "9090:9090"
    environment:
      - HYPERLIB_PROFILE=docker
      - DATABASE_URL=postgresql://db:5432/mydb
    depends_on:
      - db
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health/live"]
      interval: 30s
      timeout: 3s
      retries: 3

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: mydb
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Production-Like

```yaml
version: '3.8'

services:
  api:
    image: my-app:1.0.0
    ports:
      - "8000:8000"
    environment:
      - HYPERLIB_PROFILE=prod
    secrets:
      - db_password
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9091:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

## Prometheus Scraping

### prometheus.yml

```yaml
scrape_configs:
  - job_name: 'my-app'
    static_configs:
      - targets: ['api:9090']
    scrape_interval: 15s
    scrape_timeout: 10s
```

### Metrics Available

```
# HTTP metrics (API applications)
http_requests_total
http_request_duration_seconds
http_requests_in_progress

# Task metrics (Daemon applications)
task_execution_total
task_execution_duration_seconds
task_queue_depth

# Process metrics (all applications)
process_cpu_seconds_total
process_resident_memory_bytes
process_open_fds
```

## Best Practices

### 1. Always Use Non-Root User

```dockerfile
RUN useradd -m -u 1000 appuser
USER appuser
```

### 2. Include Debug Utilities

Derek's policy: 2-5% image size increase is acceptable for debuggability.

```dockerfile
RUN apt-get install -y curl netcat-openbsd iputils-ping
```

**Rationale**: Removing tiny utilities for disk savings is not efficient cost optimization.

### 3. Multi-Stage Builds

Separate build and runtime stages to minimize final image size:

```dockerfile
FROM python:3.11 as builder
# ... build here ...

FROM python:3.11-slim
COPY --from=builder /build/.venv /app/.venv
```

### 4. Health Check Probes

Always include health checks for orchestration:

```dockerfile
HEALTHCHECK CMD curl -f http://localhost:8080/health/live || exit 1
```

### 5. Graceful Shutdown

Handle SIGTERM properly (Hyperlib does this automatically):

```python
# Automatic with SignalHandlerMixin
app = Application.daemon(name="worker", profile="prod")
# Waits for tasks to complete (up to shutdown_timeout)
```

### 6. Resource Limits

Set memory and CPU limits:

```yaml
resources:
  limits:
    cpus: '1.0'
    memory: 512M
```

## Troubleshooting

### Container Exits Immediately

**Check**: Application startup errors

```bash
docker logs my-app
# Look for stack traces or import errors
```

### Health Check Failing

**Check**: Health server port

```bash
# Inside container
curl http://localhost:8080/health/live

# From host
docker exec -it my-app curl http://localhost:8080/health/live
```

### Metrics Not Available

**Check**: Profile enables metrics

```bash
# Should be "prod" or "docker", not "dev"
docker exec -it my-app env | grep HYPERLIB_PROFILE
```

### Port Already in Use

**Check**: Conflicting containers

```bash
docker ps -a | grep 8000
docker stop <container_id>
```

## Next Steps

- [Kubernetes Deployment](KUBERNETES.md) - HELM charts and k8s deployment
- [Profiles Guide](PROFILES.md) - Understanding dev/docker/prod profiles
- [Application Types](README.md) - API, Daemon, MCP, Oneshot, CLI guides
