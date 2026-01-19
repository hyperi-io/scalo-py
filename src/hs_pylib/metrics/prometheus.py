"""
hs-pylib Prometheus Metrics - Production-Ready Observability
==============================================================

Zero-configuration Prometheus metrics for Python applications.
Auto-collects process, container, and application metrics!

Quick Start
===========

    # Install
    pip install hs-pylib[metrics]

    # Create metrics (automatic collection!)
    from hs_pylib import create_metrics

    metrics = create_metrics(namespace="myapp")

    # Use metrics
    metrics.http_requests.inc()                    # HTTP request counter
    metrics.http_duration.observe(0.123)           # Request duration
    metrics.active_connections.set(42)             # Current connections

    # Expose endpoint (FastAPI example)
    from fastapi import FastAPI, Response
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    app = FastAPI()

    @app.get("/metrics")
    def metrics_endpoint():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

Auto-Collected Metrics
======================

**Process Metrics (automatic):**
- CPU usage (user, system, total)
- Memory (RSS, VMS, available)
- Thread count
- File descriptors
- Python version info

**Container Metrics (K8s/Docker):**
- Container memory limit (from cgroups)
- Container memory usage
- OOM kill detection
- CPU throttling

**Application Metrics (you create):**
- HTTP requests/responses
- Request duration/latency
- Active connections
- Queue sizes
- Custom counters/gauges/histograms

Standard Metric Patterns
========================

    # Counter (always increases)
    metrics.http_requests.inc()                    # +1
    metrics.http_requests.inc(5)                   # +5
    metrics.http_requests.labels(method="POST", status="200").inc()

    # Gauge (can go up/down)
    metrics.active_connections.set(42)             # Set to 42
    metrics.active_connections.inc()               # +1
    metrics.active_connections.dec()               # -1

    # Histogram (track distributions)
    metrics.request_duration.observe(0.234)        # Record 234ms
    metrics.payload_size.observe(1024)             # Record 1KB

    # Info (metadata)
    metrics.app_info.info({
        "version": "1.2.3",
        "environment": "production"
    })

Kubernetes Integration
=======================

**Prometheus Annotations (auto-discovery):**

    apiVersion: v1
    kind: Pod
    metadata:
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"

**ServiceMonitor (Prometheus Operator):**

    apiVersion: monitoring.coreos.com/v1
    kind: ServiceMonitor
    metadata:
      name: myapp
    spec:
      endpoints:
        - port: http
          path: /metrics
          interval: 30s

Zero Configuration Required
============================

✅ Auto-collects process metrics (CPU, memory, threads)
✅ Auto-detects container environment (K8s, Docker)
✅ Auto-exposes standard metrics
✅ Standard ENV variables (namespace, port, path)
✅ Works with Prometheus, Grafana, CloudWatch
"""

import os
import platform
import threading
import time
from typing import Any

import psutil

from ..logger import logger
from ..runtime import RuntimeEnvironment

# Check if prometheus_client is available
try:
    from prometheus_client import (  # type: ignore[import-not-found]
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class ProcessMetrics:
    """
    Standard process metrics for containerized applications.

    Provides:
    - CPU usage (percent, seconds)
    - Memory usage (RSS, VMS, percent)
    - Thread count
    - File descriptors
    - Uptime
    """

    def __init__(self, registry: Any | None = None, app_name: str = "app"):
        """
        Initialize process metrics.

        Args:
            registry: Prometheus registry (creates new if None)
            app_name: Application name for labels
        """
        if not PROMETHEUS_AVAILABLE:
            self.enabled = False
            return

        self.enabled = True
        self.app_name = app_name
        self.registry = registry or CollectorRegistry()
        self.process = psutil.Process()
        self.start_time = time.time()
        # Track previous CPU totals to avoid double counting
        initial_cpu = self.process.cpu_times()
        self._prev_cpu_user = initial_cpu.user
        self._prev_cpu_system = initial_cpu.system

        # Runtime environment detection
        runtime_env = RuntimeEnvironment(app_name)
        self.is_container, self.detection_method = runtime_env._is_container()

        # Process info (static)
        self.process_info = Info(
            "process",
            "Process information",
            registry=self.registry,
        )
        self.process_info.info(
            {
                "app_name": app_name,
                "pid": str(os.getpid()),
                "python_version": platform.python_version(),
                "platform": platform.system(),
                "is_container": str(self.is_container),
                "container_detection": self.detection_method,
            }
        )

        # CPU metrics
        self.cpu_percent = Gauge(
            "process_cpu_percent",
            "Process CPU usage percentage",
            registry=self.registry,
        )

        self.cpu_seconds_total = Counter(
            "process_cpu_seconds_total",
            "Total CPU time spent in seconds",
            registry=self.registry,
        )

        # Memory metrics
        self.memory_rss_bytes = Gauge(
            "process_memory_rss_bytes",
            "Resident Set Size (physical memory) in bytes",
            registry=self.registry,
        )

        self.memory_vms_bytes = Gauge(
            "process_memory_vms_bytes",
            "Virtual Memory Size in bytes",
            registry=self.registry,
        )

        self.memory_percent = Gauge(
            "process_memory_percent",
            "Memory usage as percentage of total system memory",
            registry=self.registry,
        )

        # Thread metrics
        self.threads_total = Gauge(
            "process_threads_total",
            "Number of threads",
            registry=self.registry,
        )

        # File descriptor metrics (Unix only)
        if platform.system() != "Windows":
            self.fds_open = Gauge(
                "process_fds_open",
                "Number of open file descriptors",
                registry=self.registry,
            )

        # Uptime
        self.uptime_seconds = Gauge(
            "process_uptime_seconds",
            "Process uptime in seconds",
            registry=self.registry,
        )

        logger.info("Process metrics initialized")

    def update(self):
        """Update all process metrics (call periodically)."""
        if not self.enabled:
            return

        try:
            # CPU metrics
            cpu_percent = self.process.cpu_percent()
            cpu_times = self.process.cpu_times()

            self.cpu_percent.set(cpu_percent)
            # Only increment by the delta since last update
            delta_user = cpu_times.user - self._prev_cpu_user
            delta_system = cpu_times.system - self._prev_cpu_system
            if delta_user > 0:
                self.cpu_seconds_total.inc(delta_user)
            if delta_system > 0:
                self.cpu_seconds_total.inc(delta_system)
            self._prev_cpu_user = cpu_times.user
            self._prev_cpu_system = cpu_times.system

            # Memory metrics
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()

            self.memory_rss_bytes.set(memory_info.rss)
            self.memory_vms_bytes.set(memory_info.vms)
            self.memory_percent.set(memory_percent)

            # Thread metrics
            thread_count = self.process.num_threads()
            self.threads_total.set(thread_count)

            # File descriptors (Unix only)
            if platform.system() != "Windows":
                try:
                    fds = self.process.num_fds()
                    self.fds_open.set(fds)
                except (AttributeError, OSError):
                    pass

            # Uptime
            uptime = time.time() - self.start_time
            self.uptime_seconds.set(uptime)

        except Exception as e:
            logger.error(f"Failed to update process metrics: {e}")


class ContainerMetrics:
    """
    Container-specific metrics (cgroups v2).

    Provides:
    - Memory limit and usage
    - Memory pressure (OOM detection)
    - CPU quota and usage
    - Container state
    """

    def __init__(self, registry: Any | None = None, app_name: str = "app"):
        """
        Initialize container metrics.

        Args:
            registry: Prometheus registry
            app_name: Application name for labels
        """
        if not PROMETHEUS_AVAILABLE:
            self.enabled = False
            return

        self.enabled = True
        self.app_name = app_name
        self.registry = registry or CollectorRegistry()

        # Detect container environment
        runtime_env = RuntimeEnvironment(app_name)
        self.is_container, self.detection_method = runtime_env._is_container()

        if not self.is_container:
            logger.info("Not in container - container metrics disabled")
            self.enabled = False
            return

        self._memory_limit_bytes_value: int | None = None
        self._prev_throttled_usec: int = 0
        self._prev_oom_kills: int = 0

        # Container memory metrics
        self.memory_limit_bytes = Gauge(
            "container_memory_limit_bytes",
            "Container memory limit in bytes",
            registry=self.registry,
        )

        self.memory_usage_bytes = Gauge(
            "container_memory_usage_bytes",
            "Container memory usage in bytes",
            registry=self.registry,
        )

        self.memory_available_bytes = Gauge(
            "container_memory_available_bytes",
            "Container memory available in bytes",
            registry=self.registry,
        )

        self.memory_pressure_percent = Gauge(
            "container_memory_pressure_percent",
            "Memory usage as percentage of limit",
            registry=self.registry,
        )

        # OOM detection
        self.oom_kills_total = Counter(
            "container_oom_kills_total",
            "Number of OOM kills detected",
            registry=self.registry,
        )

        # CPU metrics
        self.cpu_quota = Gauge(
            "container_cpu_quota",
            "Container CPU quota (number of cores)",
            registry=self.registry,
        )

        self.cpu_throttled_seconds_total = Counter(
            "container_cpu_throttled_seconds_total",
            "Total time CPU was throttled in seconds",
            registry=self.registry,
        )

        # Initialize static metrics
        self._read_container_limits()

        logger.info("Container metrics initialized")

    def _read_container_limits(self):
        """Read static container limits from cgroups v2."""
        if not self.enabled:
            return

        try:
            # Memory limit
            memory_limit = self._read_cgroup_memory_limit()
            if memory_limit:
                self.memory_limit_bytes.set(memory_limit)
                self._memory_limit_bytes_value = memory_limit

            # CPU quota
            cpu_quota = self._read_cgroup_cpu_quota()
            if cpu_quota:
                self.cpu_quota.set(cpu_quota)

        except Exception as e:
            logger.warning(f"Failed to read container limits: {e}")

    def _read_cgroup_memory_limit(self) -> int | None:
        """Read memory limit from cgroups v2."""
        try:
            with open("/sys/fs/cgroup/memory.max") as f:
                limit_str = f.read().strip()

            if limit_str == "max":
                # No limit, use system memory
                return psutil.virtual_memory().total

            limit = int(limit_str)
            if limit >= (1 << 63):  # Very large number = no limit
                return psutil.virtual_memory().total

            return limit

        except (FileNotFoundError, ValueError, PermissionError):
            return None

    def _read_cgroup_memory_usage(self) -> int | None:
        """Read current memory usage from cgroups v2."""
        try:
            with open("/sys/fs/cgroup/memory.current") as f:
                usage_str = f.read().strip()
            return int(usage_str)
        except (FileNotFoundError, ValueError, PermissionError):
            return None

    def _read_cgroup_cpu_quota(self) -> float | None:
        """Read CPU quota from cgroups v2."""
        try:
            with open("/sys/fs/cgroup/cpu.max") as f:
                cpu_max = f.read().strip()

            if cpu_max == "max":
                return float(psutil.cpu_count())

            if " " in cpu_max:
                quota, period = cpu_max.split()
                quota = int(quota)
                period = int(period)
                return quota / period

            return None

        except (FileNotFoundError, ValueError, PermissionError):
            return None

    def update(self):
        """Update container metrics (call periodically)."""
        if not self.enabled:
            return

        try:
            # Memory metrics
            memory_usage = self._read_cgroup_memory_usage()
            if memory_usage is not None:
                self.memory_usage_bytes.set(memory_usage)

            memory_limit = self._memory_limit_bytes_value
            if memory_limit and memory_limit > 0 and memory_usage is not None:
                available = memory_limit - memory_usage
                self.memory_available_bytes.set(max(0, available))

                pressure = (memory_usage / memory_limit) * 100
                self.memory_pressure_percent.set(pressure)

                # OOM detection (>95% usage)
                if pressure > 95:
                    logger.warning(f"High memory pressure: {pressure:.1f}%")

            # CPU throttling metrics
            cpu_stats = self._read_cgroup_cpu_stats()
            if cpu_stats:
                throttled_usec = cpu_stats.get("throttled_usec")
                if throttled_usec is not None:
                    delta_throttled = throttled_usec - self._prev_throttled_usec
                    if delta_throttled > 0:
                        self.cpu_throttled_seconds_total.inc(delta_throttled / 1_000_000)
                    self._prev_throttled_usec = throttled_usec

            # OOM kill counter from memory.events
            oom_kills = self._read_memory_events_oom_kill()
            if oom_kills is not None:
                delta_oom = oom_kills - self._prev_oom_kills
                if delta_oom > 0:
                    self.oom_kills_total.inc(delta_oom)
                self._prev_oom_kills = oom_kills

        except Exception as e:
            logger.error(f"Failed to update container metrics: {e}")

    def _read_cgroup_cpu_stats(self) -> dict[str, int]:
        """Read cpu.stat (cgroups v2)."""
        stats: dict[str, int] = {}
        try:
            with open("/sys/fs/cgroup/cpu.stat") as f:
                for line in f:
                    if " " not in line:
                        continue
                    key, value = line.strip().split(" ", 1)
                    try:
                        stats[key] = int(value)
                    except ValueError:
                        continue
        except (FileNotFoundError, PermissionError):
            return {}
        return stats

    def _read_memory_events_oom_kill(self) -> int | None:
        """Read oom_kill counter from memory.events (cgroups v2)."""
        try:
            with open("/sys/fs/cgroup/memory.events") as f:
                for line in f:
                    if line.startswith("oom_kill"):
                        _, value = line.strip().split(" ", 1)
                        return int(value)
        except (FileNotFoundError, PermissionError, ValueError):
            return None
        return None


class HTTPMetrics:
    """
    HTTP request metrics for API applications.

    Provides:
    - Request count (by method, endpoint, status)
    - Request duration (histogram)
    - Active requests (gauge)
    - Request size (histogram)
    - Response size (histogram)
    """

    def __init__(self, registry: Any | None = None, app_name: str = "app"):
        """
        Initialize HTTP metrics.

        Args:
            registry: Prometheus registry
            app_name: Application name for labels
        """
        if not PROMETHEUS_AVAILABLE:
            self.enabled = False
            return

        self.enabled = True
        self.app_name = app_name
        self.registry = registry or CollectorRegistry()

        # Request metrics
        self.requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=self.registry,
        )

        self.request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=self.registry,
        )

        self.requests_in_progress = Gauge(
            "http_requests_in_progress",
            "Number of HTTP requests currently being processed",
            ["method"],
            registry=self.registry,
        )

        self.request_size_bytes = Histogram(
            "http_request_size_bytes",
            "HTTP request size in bytes",
            registry=self.registry,
        )

        self.response_size_bytes = Histogram(
            "http_response_size_bytes",
            "HTTP response size in bytes",
            registry=self.registry,
        )

        logger.info("HTTP metrics initialized")

    def track_request(self, method: str, endpoint: str, status: int, duration: float):
        """
        Track completed HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Endpoint path
            status: HTTP status code
            duration: Request duration in seconds
        """
        if not self.enabled:
            return

        self.requests_total.labels(method=method, endpoint=endpoint, status=str(status)).inc()
        self.request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

    def track_request_size(self, size_bytes: int):
        """Track request size."""
        if self.enabled:
            self.request_size_bytes.observe(size_bytes)

    def track_response_size(self, size_bytes: int):
        """Track response size."""
        if self.enabled:
            self.response_size_bytes.observe(size_bytes)


class PrometheusMetrics:
    """
    Unified metrics manager for containerized applications.

    Combines:
    - Process metrics (CPU, memory, threads)
    - Container metrics (cgroups, OOM detection)
    - HTTP metrics (request tracking)
    - Custom metrics (easy to add)

    Provides automatic metric collection and HTTP endpoint.

    Example - Adding custom metrics:
        metrics = create_metrics("my-app")

        # Create custom counter
        requests = metrics.counter(
            "api_requests",
            "Total API requests",
            labels=["method", "endpoint"]
        )
        requests.labels(method="GET", endpoint="/users").inc()

        # Create custom gauge
        queue_size = metrics.gauge("queue_size", "Number of items in queue")
        queue_size.set(42)

        # Create custom histogram
        processing_time = metrics.histogram(
            "processing_seconds",
            "Processing time in seconds"
        )
        processing_time.observe(1.23)
    """

    def __init__(self, app_name: str = "app", enable_auto_update: bool = True, update_interval: int = 5):
        """
        Initialize metrics manager.

        Args:
            app_name: Application name
            enable_auto_update: Start background thread for metric updates
            update_interval: Seconds between metric updates (default: 5)
        """
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus metrics disabled (prometheus_client not installed)")
            self.enabled = False
            return

        self.enabled = True
        self.app_name = app_name
        self.update_interval = update_interval

        # Create shared registry
        self.registry = CollectorRegistry()

        # Initialize metric collectors
        self.process = ProcessMetrics(registry=self.registry, app_name=app_name)
        self.container = ContainerMetrics(registry=self.registry, app_name=app_name)
        self.http = HTTPMetrics(registry=self.registry, app_name=app_name)

        # Custom metrics storage
        self._custom_metrics: dict[str, Any] = {}

        # Auto-update thread
        self.shutdown_event = threading.Event()
        self.update_thread = None

        if enable_auto_update:
            self.start_auto_update()

        logger.info(f"Prometheus metrics initialized for {app_name}")

    def start_auto_update(self):
        """Start background thread for automatic metric updates."""
        if not self.enabled:
            return

        if self.update_thread and self.update_thread.is_alive():
            logger.warning("Auto-update already running")
            return

        def update_loop():
            while not self.shutdown_event.is_set():
                try:
                    self.update()
                    self.shutdown_event.wait(self.update_interval)
                except Exception as e:
                    logger.error(f"Metric update error: {e}")
                    self.shutdown_event.wait(self.update_interval)

        self.update_thread = threading.Thread(
            target=update_loop,
            name=f"{self.app_name}_metrics",
            daemon=True,
        )
        self.update_thread.start()

        logger.info("Automatic metric updates started")

    def stop_auto_update(self):
        """Stop background metric updates."""
        if self.update_thread:
            self.shutdown_event.set()
            self.update_thread.join(timeout=10)
            logger.info("Automatic metric updates stopped")

    def update(self):
        """Update all metrics immediately."""
        if not self.enabled:
            return

        self.process.update()
        self.container.update()

    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus text format.

        Returns:
            Metrics as bytes (ready for HTTP response)
        """
        if not self.enabled:
            return b"# Prometheus metrics not available\n"

        try:
            return generate_latest(self.registry)
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            return f"# Error generating metrics: {e}\n".encode()

    def get_metrics_text(self) -> str:
        """
        Get metrics as text string.

        Returns:
            Metrics as string
        """
        return self.get_metrics().decode("utf-8")

    def get_content_type(self) -> str:
        """Get Prometheus content type for HTTP responses."""
        return CONTENT_TYPE_LATEST if PROMETHEUS_AVAILABLE else "text/plain"

    # Custom metrics API

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Counter metric.

        Counter is for values that only increase (requests, errors, etc.).

        Args:
            name: Metric name (e.g., "api_requests_total")
            description: Human-readable description
            labels: Optional label names (e.g., ["method", "endpoint"])

        Returns:
            Counter instance

        Example:
            requests = metrics.counter(
                "api_requests_total",
                "Total API requests",
                labels=["method", "status"]
            )
            requests.labels(method="GET", status="200").inc()
            requests.labels(method="POST", status="201").inc(5)
        """
        if not self.enabled:
            return _NoOpMetric()

        if name in self._custom_metrics:
            return self._custom_metrics[name]

        metric = Counter(
            name,
            description,
            labelnames=labels or [],
            registry=self.registry,
        )
        self._custom_metrics[name] = metric
        logger.debug(f"Created counter metric: {name}")
        return metric

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Gauge metric.

        Gauge is for values that can go up and down (queue size, temperature, etc.).

        Args:
            name: Metric name (e.g., "queue_size")
            description: Human-readable description
            labels: Optional label names

        Returns:
            Gauge instance

        Example:
            queue_size = metrics.gauge("queue_size", "Items in processing queue")
            queue_size.set(42)
            queue_size.inc()  # 43
            queue_size.dec(3)  # 40
        """
        if not self.enabled:
            return _NoOpMetric()

        if name in self._custom_metrics:
            return self._custom_metrics[name]

        metric = Gauge(
            name,
            description,
            labelnames=labels or [],
            registry=self.registry,
        )
        self._custom_metrics[name] = metric
        logger.debug(f"Created gauge metric: {name}")
        return metric

    def histogram(
        self,
        name: str,
        description: str,
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Any:
        """
        Create or get a Histogram metric.

        Histogram tracks distribution of values (request duration, response size, etc.).

        Args:
            name: Metric name (e.g., "request_duration_seconds")
            description: Human-readable description
            labels: Optional label names
            buckets: Custom bucket boundaries (default: prometheus_client defaults)

        Returns:
            Histogram instance

        Example:
            duration = metrics.histogram(
                "processing_duration_seconds",
                "Time to process request"
            )
            duration.observe(0.123)
            duration.observe(0.456)

            # With custom buckets
            latency = metrics.histogram(
                "api_latency_seconds",
                "API latency",
                buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0)
            )
        """
        if not self.enabled:
            return _NoOpMetric()

        if name in self._custom_metrics:
            return self._custom_metrics[name]

        kwargs = {
            "name": name,
            "documentation": description,
            "labelnames": labels or [],
            "registry": self.registry,
        }

        if buckets is not None:
            kwargs["buckets"] = buckets

        metric = Histogram(**kwargs)
        self._custom_metrics[name] = metric
        logger.debug(f"Created histogram metric: {name}")
        return metric

    def summary(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get a Summary metric.

        Summary tracks percentiles over a sliding time window.

        Args:
            name: Metric name
            description: Human-readable description
            labels: Optional label names

        Returns:
            Summary instance

        Example:
            response_time = metrics.summary(
                "response_time_seconds",
                "Response time distribution"
            )
            response_time.observe(0.123)
        """
        if not self.enabled:
            return _NoOpMetric()

        if name in self._custom_metrics:
            return self._custom_metrics[name]

        from prometheus_client import Summary

        metric = Summary(
            name,
            description,
            labelnames=labels or [],
            registry=self.registry,
        )
        self._custom_metrics[name] = metric
        logger.debug(f"Created summary metric: {name}")
        return metric

    def info(self, name: str, description: str) -> Any:
        """
        Create or get an Info metric.

        Info provides static information about the application.

        Args:
            name: Metric name
            description: Human-readable description

        Returns:
            Info instance

        Example:
            app_info = metrics.info("app", "Application information")
            app_info.info({
                "version": "1.2.3",
                "environment": "production",
                "region": "us-west-2"
            })
        """
        if not self.enabled:
            return _NoOpMetric()

        if name in self._custom_metrics:
            return self._custom_metrics[name]

        metric = Info(
            name,
            description,
            registry=self.registry,
        )
        self._custom_metrics[name] = metric
        logger.debug(f"Created info metric: {name}")
        return metric

    def get_custom_metric(self, name: str) -> Any | None:
        """
        Get a previously created custom metric by name.

        Args:
            name: Metric name

        Returns:
            Metric instance or None if not found
        """
        return self._custom_metrics.get(name)


class _NoOpMetric:
    """No-op metric for when prometheus_client is not available."""

    def inc(self, *args, **kwargs):
        """No-op increment."""
        pass

    def dec(self, *args, **kwargs):
        """No-op decrement."""
        pass

    def set(self, *args, **kwargs):
        """No-op set."""
        pass

    def observe(self, *args, **kwargs):
        """No-op observe."""
        pass

    def info(self, *args, **kwargs):
        """No-op info."""
        pass

    def labels(self, *args, **kwargs):
        """No-op labels."""
        return self


# Convenience function
def create_metrics(
    app_name: str = "app",
    enable_auto_update: bool = True,
    update_interval: int = 5,
) -> PrometheusMetrics:
    """
    Create metrics manager with sensible defaults.

    Args:
        app_name: Application name
        enable_auto_update: Start background updates
        update_interval: Seconds between updates

    Returns:
        PrometheusMetrics instance

    Example:
        metrics = create_metrics("my-app")

        # In HTTP handler
        return Response(
            content=metrics.get_metrics(),
            media_type=metrics.get_content_type()
        )
    """
    return PrometheusMetrics(
        app_name=app_name,
        enable_auto_update=enable_auto_update,
        update_interval=update_interval,
    )
