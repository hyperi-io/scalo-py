# Daemon Container Example

Background task worker with container-native patterns.

## Features

- Daemon application with health checks
- Custom dependency checks (database, queue)
- Prometheus metrics for task execution
- Profile-based configuration (dev/docker/prod)
- Docker and Kubernetes deployment

## Quick Start

### Local Development

```bash
# Install dependencies
pip install hs-lib[daemon]

# Run locally
python src/example_daemon.py

# Health: http://localhost:8080/health
# Metrics: http://localhost:9090/metrics
```

### Docker

```bash
# Build
docker build -t example-daemon:latest .

# Run
docker run -p 8080:8080 -p 9090:9090 example-daemon:latest

# Test
curl http://localhost:8080/health
curl http://localhost:9090/metrics
```

### Kubernetes

```bash
# Deploy
kubectl apply -f k8s/

# Check
kubectl get pods -l app=example-daemon
kubectl logs -f deployment/example-daemon

# Test health
kubectl exec -it deployment/example-daemon -- curl http://localhost:8080/ready
```

## Project Structure

```
daemon-container/
├── src/
│   └── example_daemon.py       # Application code
├── k8s/
│   ├── deployment.yaml         # Kubernetes deployment
│   └── service.yaml            # Kubernetes service
├── Dockerfile                  # Multi-stage build
├── docker-compose.yml          # Local testing
├── prometheus.yml              # Prometheus config
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Application

The daemon runs background tasks on a schedule:

```python
from hs_lib import Application, logger

app = Application.daemon(
    name="example-daemon",
    version="1.0.0",
    profile="prod",
)

@app.health_check
def check_database():
    # Check database connection
    return True

@app.task(interval=60)
def process_queue():
    logger.info("Processing queue...")
    # Process items
```

## Configuration

### Profiles

- **dev**: Local development (console logs, no health checks)
- **docker**: Docker Compose (JSON logs, health checks, metrics)
- **prod**: Kubernetes (JSON logs, health checks, metrics, optimized)

### Environment Variables

```bash
# Profile selection
HS_LIB_PROFILE=prod

# Application config
DATABASE_URL=postgresql://localhost/mydb
QUEUE_URL=redis://localhost:6379
```

## Health Checks

### Endpoints

- `GET /health` - Liveness probe (is daemon running?)
- `GET /ready` - Readiness probe (can daemon process tasks?)

### Custom Dependency Checks

```python
@app.health_check
def check_database():
    try:
        db.ping()
        return True
    except Exception:
        return False

@app.health_check
def check_queue():
    try:
        queue.ping()
        return True
    except Exception:
        return False
```

The `/ready` endpoint returns 503 if any check fails.

## Metrics

Available at `http://localhost:9090/metrics`:

```
task_execution_total{task="process_queue",status="success"}
task_execution_duration_seconds{task="process_queue"}
process_cpu_seconds_total
process_resident_memory_bytes
```

## KEDA Autoscaling

Scale based on queue depth:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: example-daemon-scaler
spec:
  scaleTargetRef:
    name: example-daemon
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      query: task_queue_depth{app="example-daemon"}
      threshold: "10"
```

## See Also

- [hs-lib Documentation](https://github.com/hypersec-io/hs-lib/tree/main/docs)
- [Container Deployment Guide](../../docs/CONTAINER_DEPLOYMENT.md)
- [Kubernetes Guide](../../docs/KUBERNETES.md)
