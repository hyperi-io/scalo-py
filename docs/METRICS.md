# Metrics

Application metrics with Prometheus and OpenTelemetry support.

## Quick Start

```python
from hs_lib.metrics import create_metrics

# Create metrics manager (Prometheus by default)
metrics = create_metrics("myapp")

# Track metrics
metrics.counter("requests", "Total requests").inc()
metrics.gauge("queue_size", "Items in queue").set(42)
metrics.histogram("latency", "Request latency").observe(0.123)

# Get metrics for /metrics endpoint
metrics_bytes = metrics.metrics
content_type = metrics.content_type
```

## Backends

### Prometheus (Default)

```python
from hs_lib.metrics import create_metrics

metrics = create_metrics("myapp", backend="prometheus")

# Standard Prometheus metrics
counter = metrics.counter("http_requests_total", "Total requests", ["method", "status"])
counter.labels(method="GET", status="200").inc()

# Process metrics (automatic)
# - process_cpu_seconds_total
# - process_resident_memory_bytes
# - process_open_fds

# Container metrics (automatic in containers)
# - container_memory_usage_bytes
# - container_cpu_usage_seconds_total
```

### OpenTelemetry

```python
from hs_lib.metrics import create_metrics

# Requires: pip install hs-lib[opentelemetry]
metrics = create_metrics(
    "myapp",
    backend="opentelemetry",
    backend_config={
        "endpoint": "http://otel-collector:4318",
        "mode": "otlp"  # or "prometheus" for scraping
    }
)

# Same API as Prometheus
counter = metrics.counter("requests", "Total requests")
counter.inc()
```

## Configuration

### Via Code

```python
metrics = create_metrics(
    app_name="myapp",
    backend="prometheus",
    enable_auto_update=True,  # Background metrics collection
    update_interval=5,        # Update every 5 seconds
    backend_config={
        "port": 9090  # Metrics endpoint port
    }
)
```

### Via Config File

```yaml
# config.yaml
metrics:
  backend: prometheus
  enabled: true
  port: 9090
  update_interval: 5
```

```python
from hs_lib.config import get_config
from hs_lib.metrics import create_metrics

config = get_config()
metrics = create_metrics(
    "myapp",
    backend=config.get("metrics", {}).get("backend", "prometheus")
)
```

## Metric Types

### Counter

Values that only increase (requests, errors, etc.):

```python
requests = metrics.counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"]
)

# Increment
requests.labels(method="GET", endpoint="/users", status="200").inc()
requests.labels(method="POST", endpoint="/users", status="201").inc(1)
```

### Gauge

Values that go up and down (queue size, connections, etc.):

```python
queue_size = metrics.gauge(
    "queue_size",
    "Number of items in queue"
)

# Set value
queue_size.set(42)

# Increment/decrement
queue_size.inc()
queue_size.dec(5)
```

### Histogram

Track distribution of values (latency, size, etc.):

```python
latency = metrics.histogram(
    "request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)

# Observe value
latency.labels(method="GET", endpoint="/users").observe(0.123)
```

## Properties

Use properties instead of getters (cleaner API):

```python
# New style (properties)
metrics_data = metrics.metrics          # bytes
text_data = metrics.metrics_text        # str
content_type = metrics.content_type     # str

# Old style (deprecated but supported)
metrics_data = metrics.get_metrics()
text_data = metrics.get_metrics_text()
content_type = metrics.get_content_type()
```

## FastAPI Integration

```python
from hs_lib import Application
from hs_lib.metrics import create_metrics
from fastapi import Response

app = Application.api(name="my-api")
metrics = create_metrics("my-api")

@app.get("/metrics")
def metrics_endpoint():
    return Response(
        content=metrics.metrics,
        media_type=metrics.content_type
    )

@app.get("/users")
def get_users():
    # Track request
    metrics.counter("users_requests").inc()

    users = fetch_users()

    # Track result count
    metrics.gauge("users_count").set(len(users))

    return users
```

## Automatic Application Metrics

Applications automatically track metrics based on profile:

### API Application

```python
app = Application.api(name="my-api", profile="prod")
# Automatic metrics:
# - http_requests_total{method,path,status}
# - http_request_duration_seconds{method,path}
# - http_request_size_bytes{method,path}
# - http_response_size_bytes{method,path}
```

### Daemon Application

```python
app = Application.daemon(name="worker", profile="prod")
# Automatic metrics:
# - task_execution_total{task,status}  # started/success/failed
# - task_execution_duration_seconds{task}
```

## Process Metrics

Automatically collected (Prometheus backend only):

- `process_cpu_seconds_total`: Total CPU time
- `process_resident_memory_bytes`: Memory usage
- `process_open_fds`: Open file descriptors
- `process_max_fds`: Max file descriptors
- `process_virtual_memory_bytes`: Virtual memory
- `process_start_time_seconds`: Process start time

## Container Metrics

Automatically collected when running in containers:

- `container_memory_usage_bytes`: Container memory usage
- `container_memory_limit_bytes`: Container memory limit
- `container_cpu_usage_seconds_total`: Container CPU usage
- `container_cpu_quota`: Container CPU quota
- `container_cpu_period`: Container CPU period

## Prometheus Scraping

Configure Prometheus to scrape metrics:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'myapp'
    static_configs:
      - targets: ['myapp:9090']
```

## OpenTelemetry Configuration

### OTLP Mode (Push)

```python
metrics = create_metrics(
    "myapp",
    backend="opentelemetry",
    backend_config={
        "mode": "otlp",
        "endpoint": "http://otel-collector:4318",
        "headers": {"x-api-key": "secret"}
    }
)
```

### Prometheus Mode (Pull)

```python
metrics = create_metrics(
    "myapp",
    backend="opentelemetry",
    backend_config={
        "mode": "prometheus",
        "port": 9090
    }
)
```

## Naming Conventions

### Prometheus Style

- Use `_total` suffix for counters: `http_requests_total`
- Use `_seconds` suffix for durations: `request_duration_seconds`
- Use `_bytes` suffix for sizes: `response_size_bytes`
- Use snake_case: `active_connections`

### OpenTelemetry Semantic Conventions

OpenTelemetry backend automatically converts to OTEL conventions:

- `http_requests_total` → `http.server.request.count`
- `request_duration_seconds` → `http.server.request.duration`
- `response_size_bytes` → `http.server.response.size`

## Example: Complete Application

```python
from hs_lib import Application
from hs_lib.metrics import create_metrics

app = Application.api(name="shop-api", profile="prod")
metrics = create_metrics("shop-api")

# Custom business metrics
orders = metrics.counter(
    "orders_total",
    "Total orders",
    ["status", "payment_method"]
)

revenue = metrics.counter(
    "revenue_total_cents",
    "Total revenue in cents",
    ["currency"]
)

inventory = metrics.gauge(
    "inventory_items",
    "Items in inventory",
    ["product_id"]
)

@app.post("/orders")
async def create_order(order: Order):
    # Process order
    result = await process_order(order)

    # Track metrics
    orders.labels(
        status=result.status,
        payment_method=order.payment_method
    ).inc()

    revenue.labels(currency=order.currency).inc(order.total_cents)

    # Update inventory
    for item in order.items:
        current = get_inventory(item.product_id)
        inventory.labels(product_id=item.product_id).set(current - item.quantity)

    return result

@app.get("/metrics")
def get_metrics():
    return Response(
        content=metrics.metrics,
        media_type=metrics.content_type
    )
```

## Testing

```python
def test_metrics():
    metrics = create_metrics("test-app")

    counter = metrics.counter("test_counter", "Test counter")
    counter.inc()

    # Verify metric in output
    output = metrics.metrics_text
    assert "test_counter" in output
```

## Grafana Dashboards

Sample queries for Grafana:

```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# Latency (p95)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Queue size
queue_size

# Memory usage
process_resident_memory_bytes / 1024 / 1024  # MB
```
