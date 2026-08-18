# Project:   scalo
# File:      otel_tracing.py
# Purpose:   OTLP span export, wired at logger setup
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""OpenTelemetry span export.

Enabling metrics composes the exporters in: Prometheus scrape, OTLP metric push
and OTLP span export, pointed at localhost by default. An app that calls
:func:`scalo.logger.setup` and nothing else gets distributed tracing; opting out
is a config line (``otel_tracing.enabled: false`` or a blank endpoint), not a
feature you had to know about.

Configuration (settings.yaml), all env-overridable::

    otel_tracing:
      enabled: true
      endpoint: http://localhost:4317        # OTEL_EXPORTER_OTLP_ENDPOINT
      protocol: grpc                          # OTEL_EXPORTER_OTLP_PROTOCOL
      service_name: ""                        # OTEL_SERVICE_NAME
      sample_ratio: 0.05                      # OTEL_TRACES_SAMPLER_ARG
      batch_scheduled_delay_millis: 5000
      batch_max_queue_size: 2048
      batch_max_export_batch_size: 512
      export_timeout_millis: 10000

Mirrors ``scalo-rs/src/otel_tracing/mod.rs``, with one deliberate difference.
scalo-rs filters its own export path (tonic, hyper, h2) out of the OTel layer,
because those crates emit ``tracing`` spans and feeding them to the exporter
makes every export generate the spans for the next one. The Python SDK already
prevents that: ``BatchSpanProcessor`` attaches
``_SUPPRESS_INSTRUMENTATION_KEY`` around every export, so instrumentation on the
transport does not re-enter. No equivalent filter is needed here.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Any

# loguru directly rather than ``scalo.logger``: this module is imported from
# inside ``logger.setup()``, so importing back through the package would run
# during its own initialisation. It is the same singleton object either way.
from loguru import logger

from .otel_backoff import DEFAULT_ENDPOINTS, normalise_protocol

__all__ = [
    "OtelTracingConfig",
    "config_from_cascade",
    "resolve",
    "setup_tracing",
    "shutdown",
    "tracer",
]

# Flush deadline on exit, short enough to stay well inside a Kubernetes
# termination grace period when the collector is unreachable.
SHUTDOWN_TIMEOUT_MILLIS = 2_000


@dataclass
class OtelTracingConfig:
    """Span-export settings, defaults matching scalo-rs ``OtelTracingConfig``."""

    enabled: bool = True
    """Master switch for span export. False, or a blank endpoint, exports nothing."""

    endpoint: str = DEFAULT_ENDPOINTS["grpc"]
    """OTLP endpoint. A blank value is the off switch for an operator who cannot reach the config."""

    protocol: str = "grpc"
    """Wire protocol, "grpc" or "http"."""

    service_name: str = ""
    """``service.name`` resource attribute.

    Empty on purpose: the caller supplies the app's name. A package-name default
    would report every service in the fleet as "scalo".
    """

    sample_ratio: float = 0.05
    """Fraction of new traces to sample, 0.0 to 1.0.

    Applied under a parent-based sampler, so a request already sampled upstream
    is always kept and distributed traces stay whole. The default is well below
    1.0 because a busy service creates spans at request rate and exporting all
    of them costs more than the traces are worth.
    """

    batch_scheduled_delay_millis: int = 5_000
    """Batch exporter scheduled delay."""

    batch_max_queue_size: int = 2_048
    """Memory ceiling for un-exported spans.

    Once full, new spans are dropped rather than buffered, so an unreachable
    collector costs spans instead of growing without bound.
    """

    batch_max_export_batch_size: int = 512
    """Maximum spans per export request."""

    export_timeout_millis: int = 10_000
    """Per-export deadline, applied to the exporter itself.

    ``BatchSpanProcessor`` accepts an ``export_timeout_millis`` and does not use
    it -- the SDK has no way to pass a timeout through to ``export()`` -- so the
    deadline that bites is the one on the exporter.
    """

    def is_active(self) -> bool:
        """Whether span export should be wired up, after env-var resolution."""
        resolved = resolve(self)
        return resolved.enabled and bool(resolved.endpoint)


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce a config value that may arrive as a string from an env var."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if value is None:
        return default
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def config_from_cascade(settings: Any | None = None) -> OtelTracingConfig:
    """Load span-export settings from the config cascade's ``otel_tracing`` key.

    Falls back to defaults when config is unavailable or the key is absent, so a
    consumer without the section still gets the same behaviour as scalo-rs.
    """
    section: dict[str, Any] = {}
    try:
        if settings is None:
            from .config import get_settings

            settings = get_settings()
        raw = settings.get("otel_tracing", {})
        section = dict(raw) if raw else {}
    except Exception:
        section = {}

    defaults = OtelTracingConfig()
    protocol = normalise_protocol(section.get("protocol"), defaults.protocol)
    # `.get(key, fallback)` is not enough: a YAML `endpoint: ~` yields an
    # explicit None, and str(None) would build the endpoint "None" -- truthy,
    # so export would come up pointed at a hostname that does not exist.
    endpoint = section.get("endpoint")
    service_name = section.get("service_name")
    return OtelTracingConfig(
        enabled=_as_bool(section.get("enabled"), defaults.enabled),
        endpoint=str(endpoint) if endpoint is not None else DEFAULT_ENDPOINTS[protocol],
        protocol=protocol,
        service_name=str(service_name) if service_name is not None else defaults.service_name,
        sample_ratio=_as_float(section.get("sample_ratio"), defaults.sample_ratio),
        batch_scheduled_delay_millis=_as_int(
            section.get("batch_scheduled_delay_millis"), defaults.batch_scheduled_delay_millis
        ),
        batch_max_queue_size=_as_int(section.get("batch_max_queue_size"), defaults.batch_max_queue_size),
        batch_max_export_batch_size=_as_int(
            section.get("batch_max_export_batch_size"), defaults.batch_max_export_batch_size
        ),
        export_timeout_millis=_as_int(section.get("export_timeout_millis"), defaults.export_timeout_millis),
    )


def resolve(config: OtelTracingConfig) -> OtelTracingConfig:
    """Apply the standard ``OTEL_*`` env-var overrides to a config."""
    import os

    protocol = normalise_protocol(os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL"), config.protocol)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", config.endpoint)
    service_name = os.environ.get("OTEL_SERVICE_NAME") or config.service_name
    # The spec's sampler knob, so an operator can turn sampling up on one
    # service without a config change.
    sample_ratio = _as_float(os.environ.get("OTEL_TRACES_SAMPLER_ARG"), config.sample_ratio)

    return OtelTracingConfig(
        enabled=config.enabled,
        endpoint=(endpoint or "").strip(),
        protocol=protocol,
        service_name=service_name,
        sample_ratio=sample_ratio,
        batch_scheduled_delay_millis=config.batch_scheduled_delay_millis,
        batch_max_queue_size=config.batch_max_queue_size,
        batch_max_export_batch_size=config.batch_max_export_batch_size,
        export_timeout_millis=config.export_timeout_millis,
    )


def _build_span_exporter(resolved: OtelTracingConfig) -> Any:
    """Build the OTLP span exporter for the resolved protocol and endpoint."""
    timeout_seconds = max(resolved.export_timeout_millis / 1000, 1)
    if resolved.protocol == "http":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        from .otel_backoff import append_signal_path

        return OTLPSpanExporter(endpoint=append_signal_path(resolved.endpoint, "v1/traces"), timeout=timeout_seconds)

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=resolved.endpoint, timeout=timeout_seconds)


# Tracer provider and its processor, retained for the bounded flush on shutdown.
_PROVIDER: Any = None
_PROCESSOR: Any = None
_PROVIDER_LOCK = threading.Lock()


def setup_tracing(config: OtelTracingConfig | None = None, service_name: str | None = None) -> bool:
    """Wire OTLP span export, if config asks for it.

    Returns True when a tracer provider was installed. A collector that is
    missing or misconfigured degrades telemetry and never stops the service
    starting, so every failure path returns False rather than raising.

    Args:
        config: Settings to use. Defaults to the config cascade.
        service_name: Overrides ``config.service_name`` when the caller knows
            the app's name and config does not.
    """
    global _PROVIDER

    # Resolved ONCE, and onto a copy: env is read during resolution, so
    # resolving repeatedly could yield different answers within one setup, and
    # `service_name` would otherwise mutate a config object the caller owns.
    resolved = resolve(replace(config or config_from_cascade()))
    if service_name:
        resolved.service_name = service_name

    if not (resolved.enabled and resolved.endpoint):
        logger.debug("OTLP span export disabled (otel_tracing.enabled=false or blank endpoint)")
        return False

    with _PROVIDER_LOCK:
        if _PROVIDER is not None:
            return True
        try:
            provider = _build_provider(resolved)
        except ImportError:
            # Not a misconfiguration: the base install simply has no OTel SDK.
            # Warning on every setup() would punish a deliberate choice.
            logger.debug("OTLP span export needs the [opentelemetry] extra; continuing without it")
            return False
        except Exception as exc:
            logger.warning(f"OTLP span export unavailable, continuing without it: {exc}")
            return False
        _PROVIDER = provider

    logger.info(
        f"OTLP span export enabled -> {resolved.endpoint} "
        f"(protocol {resolved.protocol}, sample_ratio {resolved.sample_ratio}, "
        f"max_queue {resolved.batch_max_queue_size})"
    )
    return True


def _build_provider(resolved: OtelTracingConfig) -> Any:
    """Build and install the tracer provider for a resolved config."""
    import atexit

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    from .otel_backoff import GatedSpanExporter

    exporter = _build_span_exporter(resolved)
    # Backoff starts at one scheduled delay so the first retry is the next
    # batch, then doubles while the collector stays unreachable.
    exporter = GatedSpanExporter(exporter, resolved.batch_scheduled_delay_millis / 1000)

    processor = BatchSpanProcessor(
        exporter,
        max_queue_size=resolved.batch_max_queue_size,
        schedule_delay_millis=resolved.batch_scheduled_delay_millis,
        max_export_batch_size=resolved.batch_max_export_batch_size,
    )

    resource_attrs: dict[str, Any] = {}
    if resolved.service_name:
        resource_attrs["service.name"] = resolved.service_name
    environment = _app_env()
    if environment:
        # The STABLE semconv key; the bare deployment.environment is deprecated.
        resource_attrs["deployment.environment.name"] = environment

    provider = TracerProvider(
        resource=Resource.create(resource_attrs),
        # Parent-based so an upstream sampling decision is honoured; the ratio
        # only governs traces that start here.
        sampler=ParentBased(TraceIdRatioBased(resolved.sample_ratio)),
        # The SDK's own atexit handler shuts processors down with a 30s
        # timeout, which an unreachable collector would spend in full. This
        # module registers a bounded one instead.
        shutdown_on_exit=False,
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    global _PROCESSOR
    _PROCESSOR = processor
    atexit.register(shutdown)
    return provider


def _app_env() -> str:
    """Deployment tier for the OTel resource, from scalo's own env detection."""
    try:
        from .config import get_app_env

        return get_app_env()
    except Exception:
        return ""


def tracer(name: str = "scalo") -> Any:
    """A tracer from the installed provider, or a no-op one when export is off."""
    from opentelemetry import trace

    return trace.get_tracer(name)


def shutdown() -> None:
    """Flush and stop the tracer provider, if one was built.

    Bounded so an unreachable collector cannot eat a termination grace period:
    queued spans are dropped rather than waited on. The bound has to be applied
    to the processor -- ``TracerProvider.shutdown()`` takes no timeout and lets
    the processor's 30s default stand.
    """
    global _PROCESSOR, _PROVIDER

    with _PROVIDER_LOCK:
        provider, processor = _PROVIDER, _PROCESSOR
        _PROVIDER = _PROCESSOR = None
    if provider is None:
        return
    try:
        if processor is not None:
            processor.shutdown(timeout_millis=SHUTDOWN_TIMEOUT_MILLIS)
        provider.shutdown()
    except Exception as exc:
        logger.debug(f"OTel tracer provider shutdown: {exc}")
