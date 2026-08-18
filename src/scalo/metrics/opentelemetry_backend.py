"""
OpenTelemetry metrics backend with dual export.

Provides OpenTelemetry implementation of MetricsBackend interface with
simultaneous OTLP push and Prometheus scrape support.

A single MeterProvider with multiple MetricReaders means every metric
observation is seen by ALL readers automatically - no duplication needed.

OTLP push is ON by default, pointed at a local collector -- good citizen out of
the box, in step with scalo-rs. Opting out is a config line
(``metrics.opentelemetry.enabled: false``, or a blank endpoint), not a feature
you had to know about. Losing the push path never costs the scrape endpoint.

When nothing is listening the exporter is wrapped in a backoff gate
(:mod:`scalo.otel_backoff`), so a dead collector costs one warning and a
widening retry interval rather than a stalled export and a burst of transient
errors every tick.

Configuration (settings.yaml):
    metrics:
      backend: opentelemetry
      opentelemetry:
        enabled: true                            # master switch for OTLP push
        endpoint: http://otel-collector:4317     # or OTEL_EXPORTER_OTLP_ENDPOINT
        protocol: grpc                           # grpc|http, or OTEL_EXPORTER_OTLP_PROTOCOL
        export_interval_millis: 60000
        export_timeout_millis: 10000
        headers: {}                              # commonly a backend API key
        resource_attributes: {}                  # applied last, so they win
        prometheus_scrape: true                  # also expose /metrics (default: true)
        auto_convert_names: true                 # Prometheus->OTEL name conversion
        service_version: "1.0.0"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from ..logger import logger
from ..otel_backoff import DEFAULT_ENDPOINTS, append_signal_path, normalise_protocol
from .base import MetricsBackend, NoOpMetric

# Re-exported under the older name for consumers that import it from here.
DEFAULT_OTLP_ENDPOINTS = DEFAULT_ENDPOINTS

# Bound on the shutdown flush, well under a Kubernetes termination grace period.
SHUTDOWN_FLUSH_MILLIS = 2_000

# ---------------------------------------------------------------------------
# Prometheus-compatible adapter wrappers for OTel instruments
#
# fastapi.py and db.py use prometheus-client-style API:
#   counter.labels(method="GET", endpoint="/api").inc()
#   histogram.labels(db_type="postgres").observe(0.1)
#
# OTel instruments use:
#   counter.add(1, attributes={"method": "GET", "endpoint": "/api"})
#   histogram.record(0.1, attributes={"db_type": "postgres"})
#
# These adapters bridge the two so callers need not know which backend is active.
# ---------------------------------------------------------------------------


class _BoundCounter:
    """OTel counter with pre-bound attribute set."""

    def __init__(self, counter: Any, attributes: dict[str, Any]) -> None:
        self._counter = counter
        self._attributes = attributes

    def inc(self, amount: float = 1) -> None:
        self._counter.add(amount, attributes=self._attributes)


class _BoundGauge:
    """OTel gauge (UpDownCounter) with pre-bound attribute set."""

    def __init__(self, adapter: OtelGaugeAdapter, attributes: dict[str, Any]) -> None:
        self._adapter = adapter
        self._attributes = attributes

    def set(self, value: float) -> None:
        self._adapter._set(value, self._attributes)

    def inc(self, amount: float = 1) -> None:
        self._adapter._add(amount, self._attributes)

    def dec(self, amount: float = 1) -> None:
        self._adapter._add(-amount, self._attributes)


class _BoundHistogram:
    """OTel histogram with pre-bound attribute set."""

    def __init__(self, histogram: Any, attributes: dict[str, Any]) -> None:
        self._histogram = histogram
        self._attributes = attributes

    def observe(self, value: float) -> None:
        self._histogram.record(value, attributes=self._attributes)


class OtelCounterAdapter:
    """Wraps an OTel Counter with prometheus-client-compatible API.

    Translates ``.labels(k=v).inc()`` into ``counter.add(1, attributes={...})``.
    """

    def __init__(
        self,
        counter: Any,
        label_converter: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._counter = counter
        self._label_converter = label_converter

    def labels(self, **kwargs: Any) -> _BoundCounter:
        return _BoundCounter(self._counter, self._label_converter(kwargs))

    def inc(self, amount: float = 1) -> None:
        self._counter.add(amount)

    def add(self, amount: float, attributes: dict[str, Any] | None = None) -> None:
        """Native OTel API passthrough (for tests/advanced use)."""
        self._counter.add(amount, attributes=attributes)


class OtelGaugeAdapter:
    """Wraps an OTel UpDownCounter with prometheus-client-compatible API.

    Tracks current per-labelset values to support absolute ``.set()``, since
    OTel UpDownCounter only accepts deltas.
    """

    def __init__(
        self,
        gauge: Any,
        label_converter: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._gauge = gauge
        self._label_converter = label_converter
        self._current: dict[tuple[tuple[str, Any], ...], float] = {}

    def _key(self, attributes: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
        return tuple(sorted(attributes.items()))

    def _set(self, value: float, attributes: dict[str, Any]) -> None:
        key = self._key(attributes)
        delta = value - self._current.get(key, 0.0)
        self._current[key] = value
        self._gauge.add(delta, attributes=attributes or None)

    def _add(self, delta: float, attributes: dict[str, Any]) -> None:
        key = self._key(attributes)
        self._current[key] = self._current.get(key, 0.0) + delta
        self._gauge.add(delta, attributes=attributes or None)

    def labels(self, **kwargs: Any) -> _BoundGauge:
        return _BoundGauge(self, self._label_converter(kwargs))

    def set(self, value: float) -> None:
        self._set(value, {})

    def inc(self, amount: float = 1) -> None:
        self._add(amount, {})

    def dec(self, amount: float = 1) -> None:
        self._add(-amount, {})


class OtelHistogramAdapter:
    """Wraps an OTel Histogram with prometheus-client-compatible API.

    Translates ``.labels(k=v).observe(v)`` into ``histogram.record(v, attributes={...})``.
    """

    def __init__(
        self,
        histogram: Any,
        label_converter: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._histogram = histogram
        self._label_converter = label_converter

    def labels(self, **kwargs: Any) -> _BoundHistogram:
        return _BoundHistogram(self._histogram, self._label_converter(kwargs))

    def observe(self, value: float) -> None:
        self._histogram.record(value)

    def record(self, value: float, attributes: dict[str, Any] | None = None) -> None:
        """Native OTel API passthrough (for tests/advanced use)."""
        self._histogram.record(value, attributes=attributes)


# Try to import OpenTelemetry SDK
try:
    from opentelemetry import metrics
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Try to import prometheus_client for generate_latest
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except ImportError:
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"


@dataclass
class ResolvedOtelConfig:
    """OTLP settings after config, OTel env vars and defaults are folded together.

    Mirrors scalo-rs ``ResolvedOtelConfig``. Split out from the backend so the
    resolution can be asserted without standing up a MeterProvider.
    """

    enabled: bool = True
    endpoint: str = DEFAULT_OTLP_ENDPOINTS["grpc"]
    protocol: str = "grpc"
    export_interval_millis: int = 60_000
    export_timeout_millis: int = 10_000
    # repr=False: headers commonly carry a backend API key, and this object is
    # held on the backend where any debug dump or log of it would print the
    # value in clear. Redaction elsewhere matches on field NAMES and would not
    # see a token sitting in a map value.
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    resource_attributes: dict[str, str] = field(default_factory=dict)
    # Deployment tier (dev/staging/prod), tagged on the OTel resource as the
    # stable semconv attribute deployment.environment.name.
    deployment_environment: str = "development"

    @property
    def push_active(self) -> bool:
        """Whether OTLP push should be wired up.

        False when disabled or the effective endpoint is blank; the caller then
        installs the Prometheus reader alone.
        """
        return self.enabled and bool(self.endpoint)


def resolve_otel_config(otel_config: dict[str, Any] | None) -> ResolvedOtelConfig:
    """Resolve OTLP settings from config, with OTel env vars taking precedence.

    Precedence per field: the standard ``OTEL_*`` env var, then the config
    cascade's ``metrics.opentelemetry.*``, then the default. The env vars win
    because they are what a deployment sets and what the charts already emit.
    """
    otel_config = otel_config or {}

    protocol = normalise_protocol(
        os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL"),
        normalise_protocol(otel_config.get("protocol"), "grpc"),
    )

    # A whitespace-only endpoint resolves to empty, so OTEL_EXPORTER_OTLP_ENDPOINT=" "
    # reads as "off" rather than as an unparseable URI. It is the off switch for
    # an operator who cannot reach the config file.
    configured_endpoint = otel_config.get("endpoint", DEFAULT_OTLP_ENDPOINTS[protocol])
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", configured_endpoint)
    endpoint = (endpoint or "").strip()

    interval = _int_env("OTEL_METRIC_EXPORT_INTERVAL", otel_config.get("export_interval_millis", 60_000))
    timeout = _int_env("OTEL_METRIC_EXPORT_TIMEOUT", otel_config.get("export_timeout_millis", 10_000))

    from ..config import get_app_env

    return ResolvedOtelConfig(
        enabled=bool(otel_config.get("enabled", True)),
        endpoint=endpoint,
        protocol=protocol,
        export_interval_millis=interval,
        export_timeout_millis=timeout,
        headers=dict(otel_config.get("headers") or {}),
        resource_attributes=dict(otel_config.get("resource_attributes") or {}),
        deployment_environment=get_app_env(),
    )


def _int_env(name: str, fallback: Any) -> int:
    """Read a millisecond env var, falling back to the configured value."""
    raw = os.environ.get(name)
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning(f"{name}={raw!r} is not an integer -- using {fallback}")
    try:
        return int(fallback)
    except (TypeError, ValueError):
        return 0


def _create_otlp_exporter(protocol: str, endpoint: str, timeout_millis: int, headers: dict[str, str]) -> Any:
    """Create the OTLP metric exporter for the given protocol and endpoint.

    The timeout is the per-attempt deadline, so an endpoint that accepts the
    connection and then stalls fails the attempt instead of holding the exporter
    open past the next interval.
    """
    timeout_seconds = max(timeout_millis / 1000, 1)
    if protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        return OTLPMetricExporter(
            endpoint=append_signal_path(endpoint, "v1/metrics"),
            timeout=timeout_seconds,
            headers=headers or None,
        )

    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    return OTLPMetricExporter(endpoint=endpoint, timeout=timeout_seconds, headers=headers or None)


class OpenTelemetryBackend(MetricsBackend):
    """
    OpenTelemetry implementation of MetricsBackend with dual export.

    By default, attaches BOTH an OTLP push exporter AND a Prometheus scrape
    reader to a single MeterProvider. Every counter.add(1) is observed by
    all readers automatically.

    **Dual export architecture:**

    ::

        Application -> MetricsManager -> OpenTelemetryBackend
                                             |
                                         MeterProvider
                                           /        \\
              PeriodicExportingMetricReader    PrometheusMetricReader
                        |                            |
                  OTLP Collector              /metrics endpoint
                   (push)                      (scrape)

    **Prometheus->OTEL Name Conversion:**

    Automatically converts Prometheus metric names to OTEL semantic conventions.
    Developers write Prometheus-style names, backend converts to OTEL standards.

    Example:
        - http_requests_total -> http.server.request.count
        - http_request_duration_seconds -> http.server.request.duration
        - task_execution_total -> task.execution.count
    """

    # Prometheus to OpenTelemetry Semantic Convention mappings
    PROMETHEUS_TO_OTEL = {
        # HTTP Server metrics
        "http_requests_total": "http.server.request.count",
        "http_request_duration_seconds": "http.server.request.duration",
        "http_requests_in_progress": "http.server.active_requests",
        "http_request_size_bytes": "http.server.request.size",
        "http_response_size_bytes": "http.server.response.size",
        # Task/Job metrics
        "task_execution_total": "task.execution.count",
        "task_execution_duration_seconds": "task.execution.duration",
        "task_queue_depth": "task.queue.depth",
        "task_failures_total": "task.execution.failures",
        # Worker pool metrics
        "worker_pool_busy": "worker.pool.busy",
        "worker_pool_idle": "worker.pool.idle",
        "worker_pool_size": "worker.pool.size",
        # Job metrics (oneshot)
        "job_execution_total": "job.execution.count",
        "job_execution_duration_seconds": "job.execution.duration",
        "job_last_success_timestamp": "job.last_success.time",
        # MCP metrics
        "mcp_requests_total": "rpc.server.request.count",
        "mcp_request_duration_seconds": "rpc.server.request.duration",
        # Database metrics
        "db_queries_total": "db.client.operation.count",
        "db_query_duration_seconds": "db.client.operation.duration",
        "db_connections_active": "db.client.connections.usage",
    }

    # Label name mappings (Prometheus -> OTEL)
    #
    # NOTE: this map is flat and keyed by the Prometheus label name, so it
    # cannot distinguish two families that use the same label. "status" is
    # exactly that case: HTTP metrics and task metrics both carry one. There
    # used to be a "status": "http.status_code" entry above the task block;
    # it was dead -- the later duplicate key silently overwrote it -- so
    # every HTTP metric has always been exported as task.status.
    #
    # The dead entry is removed rather than re-ordered: whichever wins is an
    # emitted attribute name, and flipping it renames a label that existing
    # dashboards and alerts query. Disambiguating properly means scoping the
    # map per instrument family.
    LABEL_MAP = {
        # HTTP labels
        "method": "http.method",
        "endpoint": "http.route",
        "path": "http.target",
        # Task labels
        "task": "task.name",
        "status": "task.status",
        "queue": "task.queue.name",
        # Job labels
        "job": "job.name",
        # Transport labels
        "transport": "rpc.transport",
    }

    def __init__(self, app_name: str, config: dict[str, Any] | None = None):
        """
        Initialise OpenTelemetry backend with dual export support.

        Reads configuration from the provided dict and falls back to standard
        OTel environment variables (OTEL_EXPORTER_OTLP_ENDPOINT, etc.).

        Args:
            app_name: Application name
            config: Backend configuration dict
        """
        super().__init__(app_name, config)

        if not OTEL_AVAILABLE:
            logger.error("OpenTelemetry not installed. Install with: pip install scalo[opentelemetry]")
            self.enabled = False
            return

        otel_config = config.get("opentelemetry", {}) if config else {}

        self.resolved = resolve_otel_config(otel_config)
        resolved = self.resolved
        prometheus_scrape = otel_config.get("prometheus_scrape", True)
        self.auto_convert_names = otel_config.get("auto_convert_names", True)

        # Create resource (the identity the app legitimately owns -- service.*).
        # Topology (pod/namespace/node) is left to the collector's k8sattributes
        # processor / Prometheus scrape relabeling, NOT self-stamped on metrics.
        import socket

        service_name = os.environ.get("OTEL_SERVICE_NAME") or app_name
        service_version = otel_config.get("service_version", "1.0.0")
        resource_attrs: dict[str, Any] = {
            "service.name": service_name,
            "service.version": service_version,
            "service.instance.id": socket.gethostname(),
        }

        # deployment.environment.name is the STABLE semconv key; the bare
        # deployment.environment is deprecated. Sourced from scalo's own env
        # detection, so telemetry carries the tier without per-app wiring.
        if resolved.deployment_environment:
            resource_attrs["deployment.environment.name"] = resolved.deployment_environment

        # Optional, opt-in (default OFF): fold k8s Downward-API env into the
        # resource. The collector's k8sattributes processor does this more
        # reliably, so this is a convenience only.
        if otel_config.get("resource_from_downward_api", False):
            for env_name, attr in (
                ("POD_NAME", "k8s.pod.name"),
                ("POD_NAMESPACE", "k8s.namespace.name"),
                ("NODE_NAME", "k8s.node.name"),
            ):
                value = os.getenv(env_name)
                if value:
                    resource_attrs[attr] = value

        # Configured attributes applied LAST so they win over the auto-set ones.
        resource_attrs.update(resolved.resource_attributes)

        resource = Resource.create(resource_attrs)

        try:
            metric_readers = []
            readers_desc = []

            # OTLP push reader, on unless disabled or the endpoint is blank.
            #
            # Its own try: losing the push path must never cost the scrape
            # endpoint. A bad endpoint or a missing transport extra degrades to
            # Prometheus-only rather than installing no metrics at all.
            if resolved.push_active:
                try:
                    otlp_exporter = _create_otlp_exporter(
                        resolved.protocol,
                        resolved.endpoint,
                        resolved.export_timeout_millis,
                        resolved.headers,
                    )
                    # Backoff starts at one export interval so the first retry is
                    # the next scheduled tick, then doubles while the collector
                    # stays unreachable.
                    from ..otel_backoff import GatedMetricExporter

                    otlp_exporter = GatedMetricExporter(otlp_exporter, resolved.export_interval_millis / 1000)
                    otlp_reader = PeriodicExportingMetricReader(
                        exporter=otlp_exporter,
                        export_interval_millis=resolved.export_interval_millis,
                        export_timeout_millis=resolved.export_timeout_millis,
                    )
                    metric_readers.append(otlp_reader)
                    readers_desc.append(f"otlp({resolved.protocol})->{resolved.endpoint}")
                except Exception as exc:
                    logger.warning(
                        f"OTLP metric push unavailable ({exc}) -- continuing with the Prometheus scrape endpoint"
                    )

            # Prometheus scrape reader (enabled by default)
            self._prometheus_reader = None
            if prometheus_scrape:
                self._prometheus_reader = PrometheusMetricReader()
                metric_readers.append(self._prometheus_reader)
                readers_desc.append("prometheus(/metrics)")

            if not metric_readers:
                logger.error("No metric readers configured -- at least one of OTLP or Prometheus required")
                self.enabled = False
                return

            # Single MeterProvider with all readers
            self._provider = MeterProvider(
                resource=resource,
                metric_readers=metric_readers,
            )

            # Set global meter provider
            metrics.set_meter_provider(self._provider)

            # Get meter for this app
            self._meter = metrics.get_meter(app_name)

            # Cache for created metrics
            self._metrics_cache: dict[str, Any] = {}

            self.enabled = True
            logger.info(
                f"OpenTelemetry metrics initialised: readers=[{', '.join(readers_desc)}], "
                f"env={resolved.deployment_environment}, "
                f"export_interval={resolved.export_interval_millis}ms, "
                f"export_timeout={resolved.export_timeout_millis}ms"
            )

            # Register graceful shutdown BEFORE OTel SDK's own atexit handler.
            # Python atexit runs LIFO -- registering last means we run first,
            # shutting down the provider cleanly before the SDK tries to flush.
            import atexit

            self._shut_down = False

            def _graceful_shutdown():
                # Idempotent: stop_auto_update() shuts the same provider down, and
                # the SDK writes "shutdown can only be called once" to stderr for
                # the second attempt.
                if self._shut_down:
                    return
                self._shut_down = True
                try:
                    # Bounded well under a Kubernetes termination grace period:
                    # the SDK default is 30s, so an unreachable collector would
                    # otherwise hold the process open until SIGKILL.
                    for reader in metric_readers:
                        try:
                            reader.shutdown(timeout_millis=SHUTDOWN_FLUSH_MILLIS)
                        except Exception:
                            pass
                    self._provider.shutdown(timeout_millis=SHUTDOWN_FLUSH_MILLIS)
                except Exception:
                    pass  # Suppress export errors at shutdown (collector may be unavailable)

            self._graceful_shutdown = _graceful_shutdown

            atexit.register(_graceful_shutdown)

        except Exception as e:
            logger.error(f"Failed to initialise OpenTelemetry backend: {e}")
            self.enabled = False

    def _convert_metric_name(self, prometheus_name: str) -> str:
        """
        Convert Prometheus metric name to OTEL semantic convention.

        Args:
            prometheus_name: Prometheus-style metric name (e.g., "http_requests_total")

        Returns:
            OTEL semantic convention name (e.g., "http.server.request.count")
            or original name if no mapping exists
        """
        if not self.auto_convert_names:
            return prometheus_name

        otel_name = self.PROMETHEUS_TO_OTEL.get(prometheus_name)

        if otel_name:
            logger.debug(f"Converted metric name: {prometheus_name} -> {otel_name}")
            return otel_name

        logger.debug(f"No OTEL mapping for '{prometheus_name}', using original name")
        return prometheus_name

    def _convert_labels(self, labels: dict[str, Any]) -> dict[str, Any]:
        """
        Convert Prometheus label names to OTEL attribute names.

        Args:
            labels: Prometheus-style labels (e.g., {{"method": "GET", "status": "200"}})

        Returns:
            OTEL-style attributes (e.g., {{"http.method": "GET", "http.status_code": "200"}})
        """
        if not self.auto_convert_names or not labels:
            return labels

        converted = {}
        for key, value in labels.items():
            otel_key = self.LABEL_MAP.get(key, key)
            converted[otel_key] = value

        return converted

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get an OpenTelemetry Counter.

        Automatically converts Prometheus metric names to OTEL semantic conventions.

        Args:
            name: Metric name (Prometheus format, e.g., "http_requests_total")
            description: Description
            labels: Label names (not used in OTel, labels set at observation time)

        Returns:
            Counter instance
        """
        if not self.enabled:
            return NoOpMetric()

        otel_name = self._convert_metric_name(name)

        cache_key = f"counter:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        counter = self._meter.create_counter(
            name=otel_name,
            description=description,
            unit="1",
        )

        adapter = OtelCounterAdapter(counter, self._convert_labels)
        self._metrics_cache[cache_key] = adapter
        return adapter

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> Any:
        """
        Create or get an OpenTelemetry Gauge (UpDownCounter).

        Automatically converts Prometheus metric names to OTEL semantic conventions.

        Args:
            name: Metric name (Prometheus format, e.g., "task_queue_depth")
            description: Description
            labels: Label names

        Returns:
            UpDownCounter instance
        """
        if not self.enabled:
            return NoOpMetric()

        otel_name = self._convert_metric_name(name)

        cache_key = f"gauge:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        gauge = self._meter.create_up_down_counter(
            name=otel_name,
            description=description,
            unit="1",
        )

        adapter = OtelGaugeAdapter(gauge, self._convert_labels)
        self._metrics_cache[cache_key] = adapter
        return adapter

    def histogram(
        self,
        name: str,
        description: str,
        labels: list[str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> Any:
        """
        Create or get an OpenTelemetry Histogram.

        Automatically converts Prometheus metric names to OTEL semantic conventions.

        Args:
            name: Metric name (Prometheus format, e.g., "http_request_duration_seconds")
            description: Description
            labels: Label names
            buckets: Bucket boundaries (handled by views in OTel)

        Returns:
            Histogram instance
        """
        if not self.enabled:
            return NoOpMetric()

        otel_name = self._convert_metric_name(name)

        cache_key = f"histogram:{otel_name}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        histogram = self._meter.create_histogram(
            name=otel_name,
            description=description,
            unit="1",
        )

        adapter = OtelHistogramAdapter(histogram, self._convert_labels)
        self._metrics_cache[cache_key] = adapter
        return adapter

    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus exposition format.

        When a PrometheusMetricReader is attached (prometheus_scrape: true),
        this returns actual Prometheus-format metrics via generate_latest().
        Applications can serve this from their own /metrics endpoint.

        When only OTLP is active, returns an informational message since
        metrics are pushed automatically to the collector.

        Returns:
            Metrics as bytes in Prometheus text format
        """
        if not self.enabled:
            return b"# OpenTelemetry metrics not available\n"

        # If Prometheus scrape reader is active, return real metrics
        if self._prometheus_reader is not None and generate_latest is not None:
            from prometheus_client import REGISTRY

            return generate_latest(REGISTRY)

        # OTLP-only mode
        return (
            b"# OpenTelemetry OTLP exporter active\n"
            b"# Metrics are pushed automatically to collector\n"
            b"# No scraping endpoint needed\n"
        )

    def get_content_type(self) -> str:
        """Get content type for metrics endpoint.

        ``getattr`` rather than a bare attribute read: ``_prometheus_reader``
        is only assigned inside the init try-block, so on the degraded paths
        (OTel SDK missing, or init raising and setting ``enabled = False``)
        it does not exist at all. The observability server calls this on
        every scrape, so an AttributeError here would turn a missing extra
        into a 500.
        """
        if getattr(self, "_prometheus_reader", None) is not None and CONTENT_TYPE_LATEST:
            return CONTENT_TYPE_LATEST
        return "text/plain; version=0.0.4"

    def start_auto_update(self) -> None:
        """
        Start automatic metric collection.

        OTel uses periodic exporting, so this is a no-op.
        """

    def stop_auto_update(self) -> None:
        """
        Stop automatic metric collection.

        Shuts down the MeterProvider which flushes and stops all readers.
        """
        if self.enabled and hasattr(self, "_graceful_shutdown"):
            try:
                # The same bounded, idempotent path the atexit handler runs, so
                # an explicit stop followed by process exit shuts down once.
                self._graceful_shutdown()
            except Exception as e:
                logger.error(f"Error shutting down OpenTelemetry: {e}")

    def update(self) -> None:
        """
        Update metrics immediately.

        Forces a flush of all metric readers.
        """
        if self.enabled and hasattr(self, "_provider"):
            try:
                self._provider.force_flush()
            except Exception as e:
                logger.debug(f"Force flush failed (may be expected during shutdown): {e}")
