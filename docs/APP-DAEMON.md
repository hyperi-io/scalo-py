# Daemon Applications

Long-running background services with container-native patterns.

## Quick Start

```python
from hyperlib import Application

app = Application.daemon(name="worker", version="1.0.0", profile="prod")

@app.task(interval=60)
def process_queue():
    logger.info("Processing queue...")
    # Your business logic

if __name__ == "__main__":
    app.run()  # Runs Typer CLI with 'start' command
```

Container CMD: `python -m my_worker start --profile prod`

## Features

- **Scheduled tasks**: Run functions at intervals
- **Graceful shutdown**: Handles SIGTERM/SIGINT correctly (fixes orphaning bug)
- **Health HTTP server**: `/health/live` and `/health/ready` endpoints for k8s probes (port 8080)
- **Automatic metrics**: Task execution counters, duration histograms
- **Typer CLI**: Commands for start, status, stop, version, config

## Profiles

- **dev**: Local development (no health checks, no metrics)
- **docker**: CI/CD containers (health checks, metrics, JSON logs)
- **prod**: Kubernetes deployment (health checks, metrics, JSON logs)

## Scheduled Tasks

```python
@app.task(interval=60)
def sync_data():
    # Runs every 60 seconds
    pass

@app.task(interval=300)
async def cleanup():
    # Async tasks supported
    await db.cleanup_old_records()
```

## Lifecycle Hooks

```python
@app.on_startup
def startup():
    logger.info("Daemon starting...")
    db.connect()

@app.on_shutdown
def cleanup():
    logger.info("Daemon stopping...")
    db.disconnect()
```

## Health Checks

Enabled automatically in docker/prod profiles (port 8080):

- **GET /health/live**: Liveness probe (always returns 200 if running)
- **GET /health/ready**: Readiness probe (checks dependencies, 503 if any fail)

### Custom Dependency Checks

Register custom health checks for databases, caches, external services:

```python
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

The `/health/ready` endpoint will return 503 if any check returns `False` or raises an exception.

Configure port:
```python
app = Application.daemon(
    name="worker",
    profile_overrides={"health_check_port": 8888}
)
```

## Metrics

Enabled automatically in docker/prod profiles. Tracks:

- `task_execution_total` (counter): Task runs by status (started/success/failed)
- `task_execution_duration_seconds` (histogram): Task duration by task name

Access via metrics mixin:
```python
@app.task(interval=60)
def my_task():
    app.track_counter("custom_metric", labels={"type": "important"})
```

## Production Example

```python
from hyperlib import Application, logger

app = Application.daemon(
    name="data-processor",
    version="1.0.0",
    profile="prod"
)

@app.on_startup
def startup():
    logger.info("Connecting to database...")
    db.connect()

@app.task(interval=300)
def process_pending_jobs():
    jobs = db.get_pending_jobs()
    for job in jobs:
        process_job(job)

@app.on_shutdown
def cleanup():
    logger.info("Shutting down gracefully...")
    db.disconnect()

if __name__ == "__main__":
    app.run()
```

Dockerfile:
```dockerfile
CMD ["python", "-m", "my_worker", "start", "--profile", "prod"]
```

Kubernetes manifest:
```yaml
spec:
  containers:
  - name: worker
    ports:
    - containerPort: 8080
      name: health
    - containerPort: 9090
      name: metrics
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8080
      initialDelaySeconds: 10
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /health/ready
        port: 8080
      initialDelaySeconds: 5
      periodSeconds: 5
```

## Thread Safety

Tasks run in separate threads (daemon=False by default). The daemon waits for all tasks to complete during shutdown (up to `shutdown_timeout`).

**Important**: This fixes the orphaned process bug where daemon threads were left running after container exit.
