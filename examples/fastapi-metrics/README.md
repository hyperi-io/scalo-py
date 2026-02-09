# FastAPI Metrics Example

Demonstrates hyperi-pylib's Prometheus metrics integration with FastAPI.

## Features

- Prometheus metrics endpoint (`/metrics`)
- Automatic process/container metrics collection
- Custom application metrics (counters, gauges, histograms)
- Request duration tracking
- Health check endpoints

## Quick Start

```bash
# Install dependencies
uv sync

# Run the API server
uv run python main.py

# In another terminal, test the endpoints
curl http://localhost:8000/
curl http://localhost:8000/api/users
curl http://localhost:8000/health
curl http://localhost:8000/metrics

# Run tests
uv run pytest
```

## Metrics Endpoint

The `/metrics` endpoint exposes Prometheus-format metrics:

```
# HELP myapp_http_requests_total Total HTTP requests
# TYPE myapp_http_requests_total counter
myapp_http_requests_total{method="GET",endpoint="/api/users",status="200"} 5.0

# HELP myapp_http_request_duration_seconds HTTP request duration
# TYPE myapp_http_request_duration_seconds histogram
myapp_http_request_duration_seconds_bucket{endpoint="/api/users",le="0.1"} 5.0

# HELP process_cpu_seconds_total Total CPU time
# TYPE process_cpu_seconds_total counter
process_cpu_seconds_total 0.52
```

## Creating Custom Metrics

```python
from hyperi_pylib.metrics import create_metrics

# Create metrics manager
metrics = create_metrics(namespace="myapp")

# Counter - things that only go up
requests = metrics.counter("http_requests", "Total HTTP requests", ["method", "endpoint"])
requests.labels(method="GET", endpoint="/api/users").inc()

# Gauge - things that go up and down
active_users = metrics.gauge("active_users", "Currently active users")
active_users.set(42)

# Histogram - distribution of values
duration = metrics.histogram("request_duration", "Request duration in seconds", ["endpoint"])
duration.labels(endpoint="/api/users").observe(0.123)
```

## Health Endpoints

| Endpoint | Purpose | K8s Probe |
|----------|---------|-----------|
| `/health` | Basic liveness | livenessProbe |
| `/health/live` | Process alive | livenessProbe |
| `/health/ready` | Ready for traffic | readinessProbe |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_HOST` | Bind address | 0.0.0.0 |
| `API_PORT` | Port number | 8000 |
| `METRICS_NAMESPACE` | Prometheus namespace | myapp |

## Kubernetes Integration

```yaml
spec:
  containers:
  - name: myapp
    ports:
    - containerPort: 8000
      name: http
    livenessProbe:
      httpGet:
        path: /health/live
        port: http
    readinessProbe:
      httpGet:
        path: /health/ready
        port: http
```

Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: myapp
    static_configs:
      - targets: ['myapp:8000']
    metrics_path: /metrics
```

## See Also

- [hyperi-pylib Metrics Documentation](../../docs/METRICS.md)
- [Prometheus Python Client](https://github.com/prometheus/client_python)
