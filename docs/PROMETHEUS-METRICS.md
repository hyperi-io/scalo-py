# HyperLib Prometheus Metrics

Production-ready Prometheus metrics for containerized Python applications with an easy-to-use custom metrics API.

## Quick Start

```python
from hyperlib import create_metrics

# Create metrics manager
metrics = create_metrics("my-app")

# Metrics are automatically collected in the background
# HTTP endpoint ready to use
```

## Built-in Metrics (Auto-Collected)

### Process Metrics

- `process_cpu_percent` - CPU usage percentage
- `process_cpu_seconds_total` - Total CPU time
- `process_memory_rss_bytes` - Physical memory (RSS)
- `process_memory_vms_bytes` - Virtual memory
- `process_memory_percent` - Memory as % of system total
- `process_threads_total` - Number of threads
- `process_fds_open` - Open file descriptors (Unix)
- `process_uptime_seconds` - Process uptime

### Container Metrics (Auto-Detected)

- `container_memory_limit_bytes` - Memory limit from cgroups
- `container_memory_usage_bytes` - Current memory usage
- `container_memory_available_bytes` - Available memory
- `container_memory_pressure_percent` - Memory pressure (OOM risk)
- `container_cpu_quota` - CPU cores allocated
- `container_oom_kills_total` - OOM kill counter

### HTTP Metrics (Manual Tracking)

- `http_requests_total` - Total requests (by method, endpoint, status)
- `http_request_duration_seconds` - Request duration histogram
- `http_requests_in_progress` - Active requests gauge
- `http_request_size_bytes` - Request size histogram
- `http_response_size_bytes` - Response size histogram

## Custom Metrics API

### Counter (Values That Only Increase)

```python
# Create counter
requests = metrics.counter(
    "api_requests_total",
    "Total API requests",
    labels=["method", "endpoint", "status"]
)

# Increment
requests.labels(method="GET", endpoint="/users", status="200").inc()
requests.labels(method="POST", endpoint="/users", status="201").inc(5)

# Use cases: requests, errors, events, completions
```

### Gauge (Values That Go Up and Down)

```python
# Create gauge
queue_size = metrics.gauge(
    "queue_size",
    "Number of items in processing queue",
    labels=["priority"]
)

# Set absolute value
queue_size.labels(priority="high").set(42)

# Increment/decrement
queue_size.labels(priority="low").inc()   # 43
queue_size.labels(priority="low").dec(3)  # 40

# Use cases: queue size, active connections, temperature, cache size
```

### Histogram (Distribution of Values)

```python
# Create histogram with default buckets
duration = metrics.histogram(
    "processing_duration_seconds",
    "Time to process request"
)

# Observe values
duration.observe(0.123)
duration.observe(0.456)

# Custom buckets
latency = metrics.histogram(
    "api_latency_seconds",
    "API latency",
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
)
latency.observe(0.234)

# Use cases: request duration, response size, query time
```

### Summary (Percentiles Over Time)

```python
# Create summary
response_time = metrics.summary(
    "response_time_seconds",
    "Response time distribution"
)

# Observe values
response_time.observe(0.123)

# Use cases: percentile tracking, sliding window stats
```

### Info (Static Application Metadata)

```python
# Create info
app_info = metrics.info("app", "Application information")

# Set metadata
app_info.info({
    "version": "1.2.3",
    "environment": "production",
    "region": "us-west-2",
    "build": "abc123"
})

# Use cases: version info, deployment metadata, configuration
```

## FastAPI Integration

```python
from hyperlib import Application, create_metrics
from fastapi import Response

# Create application and metrics
app = Application.api(name="my-service", port=8000)
metrics = create_metrics("my-service")

# Add custom business metrics
db_queries = metrics.counter("db_queries_total", "Database queries", labels=["table"])
cache_hits = metrics.gauge("cache_hit_ratio", "Cache hit ratio")
processing_time = metrics.histogram("processing_seconds", "Processing time")

@app.route("/api/users")
def get_users():
    # Track database query
    db_queries.labels(table="users").inc()

    # Measure processing time
    import time
    start = time.time()

    # ... business logic ...

    duration = time.time() - start
    processing_time.observe(duration)

    return {"users": [...]}

@app.route("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type()
    )

app.run()
```

## Tracking HTTP Requests

```python
import time
from hyperlib import create_metrics

metrics = create_metrics("api-service")

def handle_request(method, endpoint):
    start = time.time()

    # Mark request in progress
    metrics.http.requests_in_progress.labels(method=method).inc()

    try:
        # ... handle request ...
        status = 200
        response_size = 1024

    finally:
        # Track completed request
        duration = time.time() - start
        metrics.http.track_request(method, endpoint, status, duration)
        metrics.http.track_response_size(response_size)
        metrics.http.requests_in_progress.labels(method=method).dec()
```

## Configuration

```python
from hyperlib.prometheus import PrometheusMetrics

# Custom configuration
metrics = PrometheusMetrics(
    app_name="my-app",
    enable_auto_update=True,    # Background metric updates
    update_interval=5,          # Update every 5 seconds
)

# Manual updates (if auto-update disabled)
metrics.update()  # Update process/container metrics now
```

## Prometheus Scrape Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'my-app'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

## Kubernetes ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-app
spec:
  selector:
    matchLabels:
      app: my-app
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
```

## Grafana Dashboard Example

```json
{
  "dashboard": {
    "title": "My App Metrics",
    "panels": [
      {
        "title": "CPU Usage",
        "targets": [
          {
            "expr": "rate(process_cpu_seconds_total[5m])"
          }
        ]
      },
      {
        "title": "Memory Usage",
        "targets": [
          {
            "expr": "process_memory_rss_bytes / container_memory_limit_bytes"
          }
        ]
      },
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Request Duration P95",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

## Best Practices

### 1. Use Descriptive Names

```python
# Good
requests_total = metrics.counter("api_requests_total", "Total API requests")

# Bad
counter1 = metrics.counter("c1", "Counter")
```

### 2. Add Units to Names

```python
# Good
duration_seconds = metrics.histogram("processing_duration_seconds", "Processing time")
size_bytes = metrics.histogram("response_size_bytes", "Response size")

# Avoid
duration = metrics.histogram("processing_duration", "Time")  # What unit?
```

### 3. Use Labels for Dimensions

```python
# Good - Use labels for different dimensions
requests = metrics.counter("requests_total", "Requests", labels=["method", "status"])
requests.labels(method="GET", status="200").inc()
requests.labels(method="POST", status="201").inc()

# Bad - Don't create separate metrics
get_requests = metrics.counter("get_requests", "GET requests")
post_requests = metrics.counter("post_requests", "POST requests")
```

### 4. Limit Label Cardinality

```python
# Good - Fixed set of values
requests.labels(method="GET", status="200")  # Limited to HTTP methods and status codes

# Bad - Unbounded values
requests.labels(user_id=user_id)  # Could create millions of time series!
```

### 5. Reuse Metrics

```python
# Good - Create once, use many times
class MyService:
    def __init__(self):
        self.metrics = create_metrics("my-service")
        self.requests = self.metrics.counter("requests_total", "Requests")

    def handle_request(self):
        self.requests.inc()  # Reuse same metric

# Bad - Creating new metrics repeatedly
def handle_request():
    metrics = create_metrics("my-service")  # Don't do this!
    requests = metrics.counter("requests_total", "Requests")
    requests.inc()
```

## Troubleshooting

### Metrics Not Appearing

```python
# Ensure prometheus_client is installed
pip install prometheus_client

# Check if metrics are enabled
metrics = create_metrics("my-app")
print(metrics.enabled)  # Should be True

# Verify metrics are being collected
print(metrics.get_metrics_text())
```

### High Memory Usage

```python
# Limit label cardinality
# BAD: Unbounded labels
user_requests = metrics.counter("requests", "Requests", labels=["user_id"])

# GOOD: Bounded labels
user_requests = metrics.counter("requests", "Requests", labels=["user_type"])
```

### Container Metrics Not Working

```python
# Check if running in container
from hyperlib.runtime import RuntimeEnvironment

runtime = RuntimeEnvironment("my-app")
is_container, method = runtime._is_container()
print(f"Container: {is_container}, Method: {method}")

# Ensure cgroups v2 is available
# Check: ls /sys/fs/cgroup/
```

## Performance

- **Overhead**: < 0.1ms per metric operation
- **Memory**: ~100KB base + ~1KB per unique metric/label combination
- **Auto-update**: Background thread, 5s interval by default
- **Metric collection**: ~1ms for all built-in metrics

## Advanced Usage

### Custom Update Logic

```python
metrics = PrometheusMetrics(
    app_name="my-app",
    enable_auto_update=False  # Disable auto-update
)

# Update manually when needed
def on_timer():
    metrics.update()  # Update process/container metrics

    # Update custom metrics
    queue_size = get_queue_size()
    metrics.gauge("queue_size", "Queue size").set(queue_size)
```

### Multiple Registries

```python
from prometheus_client import CollectorRegistry

# Separate registries for different purposes
app_registry = CollectorRegistry()
debug_registry = CollectorRegistry()

app_metrics = ProcessMetrics(registry=app_registry, app_name="app")
debug_metrics = ProcessMetrics(registry=debug_registry, app_name="debug")

# Generate separate outputs
app_output = generate_latest(app_registry)
debug_output = generate_latest(debug_registry)
```

### Metric Retrieval

```python
# Get previously created metric
metrics = create_metrics("my-app")

# Create metric
counter = metrics.counter("my_counter", "Test")

# Later, retrieve it
same_counter = metrics.get_custom_metric("my_counter")
assert same_counter is counter
```

## See Also

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Prometheus Python Client](https://github.com/prometheus/client_python)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)
