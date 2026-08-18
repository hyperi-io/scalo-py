# Project:   scalo
# File:      otel_backoff.py
# Purpose:   Backoff gate wrapping the OTLP exporters
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Exponential backoff with jitter for the OTLP exporters.

The OTel Python SDK retries INSIDE one export call -- the gRPC exporter makes up
to six attempts bounded by its own timeout -- but nothing governs the schedule
between calls. A collector that is down is dialled again at the next tick,
forever, at the same rate: every 60s each service burns its full export timeout
and logs a handful of transient-error warnings, for as long as the outage lasts.

The gate wraps an exporter and suppresses attempts while backing off, doubling
the wait after each consecutive failure up to a ceiling and spreading it with
jitter so a fleet that lost its collector together does not come back in
lockstep. One success resets it.

Suppressed exports report success to the SDK. For metrics that costs nothing --
OTLP is cumulative by default, so the next export that lands carries the full
value. For spans it drops the batch, which is the same outcome as the bounded
queue overflowing, only cheaper.

Mirrors ``scalo-rs/src/otel_backoff.rs``; the constants are the shared contract.

This module is also where the pieces both OTLP signals need live -- the default
endpoints, protocol normalisation, and signal-path handling -- so metrics and
tracing share one answer rather than each carrying a copy.
"""

from __future__ import annotations

import random
import sys
import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

# loguru directly rather than ``scalo.logger``: ``logger.setup()`` composes the
# span exporter, so importing back through the package would run during its own
# initialisation. It is the same singleton object either way.
from loguru import logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from opentelemetry.sdk.metrics.export import MetricExportResult, MetricsData
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExportResult

__all__ = [
    "DEFAULT_ENDPOINTS",
    "JITTER_PCT",
    "MAX_BACKOFF_SECONDS",
    "BackoffGate",
    "GatedMetricExporter",
    "GatedSpanExporter",
    "append_signal_path",
    "normalise_protocol",
]

# Default OTLP endpoint per protocol, shared by every signal.
DEFAULT_ENDPOINTS = {
    "grpc": "http://localhost:4317",
    "http": "http://localhost:4318",
}


# Ceiling on the wait between attempts.
MAX_BACKOFF_SECONDS = 900.0

# Jitter applied either side of the computed wait, as a percentage.
JITTER_PCT = 20

# Consecutive failures after which the wait stops doubling.
MAX_DOUBLINGS = 16

# Floor on the base wait, so a misconfigured interval cannot spin.
MIN_BASE_SECONDS = 0.1


def normalise_protocol(value: str | None, fallback: str) -> str:
    """Map an OTLP protocol name onto "grpc" or "http".

    Accepts the spec's ``http/protobuf`` and ``http/json`` spellings. An
    unrecognised value falls back rather than raising: a typo in one env var
    should not stop a service starting.
    """
    if not value:
        return fallback
    lowered = value.strip().lower()
    if lowered in ("http", "http/protobuf", "http/json"):
        return "http"
    if lowered == "grpc":
        return "grpc"
    return fallback


def append_signal_path(endpoint: str, signal_path: str) -> str:
    """Append the OTLP signal path to a BASE endpoint, for the HTTP protocol.

    ``OTEL_EXPORTER_OTLP_ENDPOINT`` is defined as a base URL that each signal
    appends its own path to; a per-signal endpoint is used verbatim. The SDK
    only does that appending for the endpoint IT reads from the environment --
    one passed to a constructor is used exactly as given. scalo resolves the
    base endpoint itself, so it has to append the path itself too, or every
    HTTP-protocol export POSTs to the collector's root.

    gRPC has no per-signal path, so this applies to the HTTP protocol only.
    """
    trimmed = endpoint.rstrip("/")
    if trimmed.endswith(f"/{signal_path}"):
        return trimmed
    return f"{trimmed}/{signal_path}"


def _log(level: str, message: str) -> None:
    """Report a gate event, and never let reporting it become the problem.

    The exporters run on their own threads and keep running while the process
    winds down, so a line can be emitted after the sinks are gone -- loguru then
    prints its own "I/O operation on closed file" traceback where the useful
    message should be. Nothing reads a log line during interpreter finalisation,
    so there is nothing to lose by staying quiet.
    """
    if sys.is_finalizing():
        return
    try:
        getattr(logger.bind(target="scalo.otel"), level)(message)
    except Exception:
        pass  # Telemetry must never take the app down, least of all its own logging.


class BackoffGate:
    """Tracks consecutive export failures and how long to stay quiet.

    Safe to share across threads: the metric reader exports on a timer thread
    and the span processor on its own worker, and both may touch one gate.
    """

    def __init__(self, base_seconds: float) -> None:
        """Build a gate whose first wait after a failure is ``base_seconds``."""
        self._base = max(float(base_seconds), MIN_BASE_SECONDS)
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._blocked_until: float | None = None
        # Failures suppressed since the last log line, so the recovery message
        # can say what the outage actually cost.
        self._suppressed = 0

    @property
    def consecutive_failures(self) -> int:
        """Failures since the last success. Advisory; for tests and reporting."""
        with self._lock:
            return self._consecutive_failures

    @property
    def suppressed(self) -> int:
        """Attempts skipped since the last log line."""
        with self._lock:
            return self._suppressed

    def should_skip(self) -> bool:
        """Whether this attempt should be skipped."""
        with self._lock:
            if self._blocked_until is not None and time.monotonic() < self._blocked_until:
                self._suppressed += 1
                return True
            return False

    def record_success(self, what: str) -> None:
        """Clear the backoff after a successful export."""
        with self._lock:
            failures = self._consecutive_failures
            suppressed = self._suppressed
            self._consecutive_failures = 0
            self._blocked_until = None
            self._suppressed = 0
        if failures:
            _log(
                "info",
                f"OTLP {what} export recovered after {failures} failures ({suppressed} attempts suppressed)",
            )

    def record_failure(self, what: str, error: str) -> None:
        """Record a failed export and start (or extend) the backoff."""
        with self._lock:
            self._consecutive_failures += 1
            failures = self._consecutive_failures
            wait = self._wait_for(failures)
            self._blocked_until = time.monotonic() + wait

        # Only the first failure of an outage is logged at warn: the rest are the
        # same fact repeated, and a fleet-wide outage would otherwise flood every
        # service's logs for its duration.
        if failures == 1:
            _log("warning", f"OTLP {what} export failed, backing off {wait:.0f}s: {error}")
        else:
            _log(
                "debug",
                f"OTLP {what} export still failing after {failures} attempts, retrying in {wait:.0f}s: {error}",
            )

    def _wait_for(self, failures: int) -> float:
        """Exponential wait for the given failure count, with jitter."""
        doublings = min(max(failures - 1, 0), MAX_DOUBLINGS)
        scaled = min(self._base * (2**doublings), MAX_BACKOFF_SECONDS)
        # Clamped again after jitter: jitter widens either side, so applying it
        # to a value already at the ceiling would push past it.
        return min(_jitter(scaled), MAX_BACKOFF_SECONDS)


def _jitter(base: float) -> float:
    """Spread a wait by +/-:data:`JITTER_PCT` so a fleet does not retry in lockstep.

    ``random`` rather than ``secrets``: this schedules a retry, it does not
    protect anything.
    """
    span = base * JITTER_PCT / 100
    if span <= 0:
        return base
    return max(base + random.uniform(-span, span), 0.0)


class GatedMetricExporter:
    """Wraps an OTLP metric exporter so failures back off.

    Not a :class:`~opentelemetry.sdk.metrics.export.MetricExporter` subclass:
    ``PeriodicExportingMetricReader`` reads ``_preferred_temporality`` and
    ``_preferred_aggregation`` off whatever it is given, and those must be the
    INNER exporter's, so they are mirrored here rather than re-declared.
    """

    def __init__(self, inner: Any, base_seconds: float) -> None:
        self._inner = inner
        self._gate = BackoffGate(base_seconds)
        self._preferred_temporality = getattr(inner, "_preferred_temporality", None)
        self._preferred_aggregation = getattr(inner, "_preferred_aggregation", None)

    @property
    def gate(self) -> BackoffGate:
        """The backoff gate, for tests and for reporting export health."""
        return self._gate

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any) -> MetricExportResult:
        from opentelemetry.sdk.metrics.export import MetricExportResult

        if self._gate.should_skip():
            return MetricExportResult.SUCCESS
        try:
            result = self._inner.export(metrics_data, timeout_millis=timeout_millis, **kwargs)
        except Exception as exc:
            # Broad on purpose: an exporter runs on the reader's thread and must
            # never take the app down, whatever the transport raises.
            self._gate.record_failure("metric", str(exc))
            return MetricExportResult.SUCCESS
        if result == MetricExportResult.SUCCESS:
            self._gate.record_success("metric")
            return result
        self._gate.record_failure("metric", "exporter reported failure")
        # Reported as handled: the SDK logs every failure it is given, and the
        # gate has already said what happened, once.
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self._inner.force_flush(timeout_millis=timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        # PeriodicExportingMetricReader spends its shutdown budget joining the
        # export thread and then passes what is left as `timeout`, not
        # `timeout_millis`, so the deadline lands in **kwargs and the exporter
        # falls back to its own 30s default. Honour whichever name the caller
        # used, or the bound the service set never reaches the wire.
        remaining = kwargs.pop("timeout", None)
        if remaining is not None:
            timeout_millis = min(timeout_millis, float(remaining))
        self._inner.shutdown(timeout_millis=max(timeout_millis, 0), **kwargs)


class GatedSpanExporter:
    """Wraps an OTLP span exporter so failures back off."""

    def __init__(self, inner: Any, base_seconds: float) -> None:
        self._inner = inner
        self._gate = BackoffGate(base_seconds)

    @property
    def gate(self) -> BackoffGate:
        """The backoff gate, for tests and for reporting export health."""
        return self._gate

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        from opentelemetry.sdk.trace.export import SpanExportResult

        if self._gate.should_skip():
            return SpanExportResult.SUCCESS
        try:
            result = self._inner.export(spans)
        except Exception as exc:
            # Broad on purpose, same reason as the metric exporter above.
            self._gate.record_failure("span", str(exc))
            return SpanExportResult.SUCCESS
        if result == SpanExportResult.SUCCESS:
            self._gate.record_success("span")
            return result
        self._gate.record_failure("span", "exporter reported failure")
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis=timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        # `timeout_millis` is declared because BatchSpanProcessor inspects the
        # argspec and only forwards its remaining budget to an exporter that
        # names it. The base SpanExporter.shutdown() takes none, so a signature
        # copied from the ABC silently drops the bound.
        try:
            self._inner.shutdown(timeout_millis=timeout_millis)
        except TypeError:
            self._inner.shutdown()
