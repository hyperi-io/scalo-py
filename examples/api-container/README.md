# API Container Example

Simple FastAPI application with container-native patterns.

## Features

- FastAPI REST API with health checks
- Custom dependency checks (database, redis)
- Prometheus metrics
- Profile-based configuration (dev/docker/prod)
- Docker and Kubernetes deployment

## Quick Start

### Local Development

```bash
# Install dependencies
pip install hs-lib[api]

# Run locally
python src/example_api.py

# API: http://localhost:8000
# Health: http://localhost:8080/health
# Metrics: http://localhost:9090/metrics
```

### Docker

```bash
# Build
docker build -t example-api:latest .

# Run
docker run -p 8000:8000 -p 8080:8080 -p 9090:9090 example-api:latest

# Test
curl http://localhost:8080/health
curl http://localhost:8000/api/users
```

### Kubernetes

```bash
# Deploy
kubectl apply -f k8s/

# Check
kubectl get pods -l app=example-api
kubectl logs -f deployment/example-api

# Test
kubectl port-forward svc/example-api 8000:80
curl http://localhost:8000/api/users
```

## Project Structure

```
api-container/
├── src/
│   └── example_api.py          # Application code
├── k8s/
│   ├── deployment.yaml         # Kubernetes deployment
│   └── service.yaml            # Kubernetes service
├── Dockerfile                  # Multi-stage build
├── docker-compose.yml          # Local testing
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## API Endpoints

- `GET /` - Root endpoint
- `GET /api/users` - List users
- `POST /api/users` - Create user
- `GET /health` - Liveness probe (port 8080)
- `GET /ready` - Readiness probe (port 8080)
- `GET /metrics` - Prometheus metrics (port 9090)

## Configuration

### Profiles

- **dev**: Local development (console logs, no health checks)
- **docker**: Docker Compose (JSON logs, health checks, metrics)
- **prod**: Kubernetes (JSON logs, health checks, metrics, optimized)

### Environment Variables

```bash
# Profile selection
HYPERLIB_PROFILE=prod

# Application config
API_PORT=8000
DATABASE_URL=postgresql://localhost/mydb
REDIS_URL=redis://localhost:6379
```

## Health Checks

### Custom Dependency Checks

```python
@app.health_check
def check_database():
    try:
        db.ping()
        return True
    except Exception:
        return False
```

The `/ready` endpoint returns 503 if any check fails.

## Metrics

Available at `http://localhost:9090/metrics`:

```
http_requests_total{method="GET",endpoint="/api/users",status="200"}
http_request_duration_seconds{method="GET",endpoint="/api/users"}
process_cpu_seconds_total
process_resident_memory_bytes
```

## See Also

- [Hyperlib Documentation](https://github.com/hypersec-io/hyperlib/tree/main/docs)
- [Container Deployment Guide](../../docs/CONTAINER_DEPLOYMENT.md)
- [Kubernetes Guide](../../docs/KUBERNETES.md)
