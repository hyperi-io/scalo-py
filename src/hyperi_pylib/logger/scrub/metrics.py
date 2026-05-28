#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/metrics.py
#  Purpose:   Metric emission for scrub events (spec §8)
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Metric emission per spec §8.

Five metrics, identical names in both pylib and rustlib so operator
dashboards work across implementations:

- ``log_scrub_matches_total`` -- counter, labels ``layer``/``type``
- ``log_scrub_redactions_total`` -- counter, labels ``layer``/``type``
- ``log_scrub_errors_total`` -- counter, labels ``layer``/``error_type``
- ``log_scrub_skipped_rules_total`` -- gauge, labels ``layer``/``rule_id``
- ``log_scrub_duration_seconds`` -- histogram, label ``layer``

Plus a label-set emitted once per scrubber build:

- ``log_scrub_pattern_version`` -- labels ``source``/``version``

The scrubber takes a :class:`ScrubMetrics` instance (or its no-op
default). This keeps it decoupled from any specific metrics-manager
implementation: tests pass ``ScrubMetrics()`` (no-op) and production
passes ``ScrubMetrics.from_manager(metrics_manager)``.

Per spec §8: scrub-metric emission is best-effort. Failures here must
NEVER break logging -- every method wraps backend calls and swallows
exceptions silently. The scrubber's own logging suppression already
prevents storms from a misbehaving backend.
"""

from __future__ import annotations

from typing import Any, Protocol


class _MetricHandle(Protocol):
    """Backend-agnostic counter/gauge/histogram surface.

    Real metrics backends (Prometheus, OpenTelemetry) all satisfy this
    via duck-typing. We don't import :class:`MetricsManager` so the
    scrub module stays decoupled.
    """

    def labels(self, *args: Any, **kwargs: Any) -> Any: ...  # pragma: no cover


class ScrubMetrics:
    """Thin wrapper around a MetricsManager-like backend.

    Pre-builds the five metric handles at construction so per-call
    emission is one labels-lookup-and-method-call (cheap). Designed
    to be safe to call from the scrubber's hot path.

    Args:
        backend: an object exposing ``counter()``, ``gauge()``, and
            ``histogram()`` methods returning Prometheus-style metric
            handles. ``None`` (default) yields a no-op instance -- every
            emit is a cheap branch with no side effects.

    Example:
        >>> from hyperi_pylib.metrics import create_metrics
        >>> mm = create_metrics("myapp")
        >>> scrub_metrics = ScrubMetrics.from_manager(mm)
        >>> scrubber = build_scrubber(config, metrics=scrub_metrics)
    """

    def __init__(
        self,
        backend: Any | None = None,
        type_cardinality_cap: int = 64,
    ) -> None:
        self._backend = backend
        self._matches: _MetricHandle | None = None
        self._redactions: _MetricHandle | None = None
        self._errors: _MetricHandle | None = None
        self._skipped: _MetricHandle | None = None
        self._duration: _MetricHandle | None = None
        self._pattern_version: _MetricHandle | None = None

        # Cardinality cap for the `type` label. Tracked per instance --
        # tests that build fresh scrubbers get fresh caps. The seen set
        # is shared across matches+redactions so they cap together.
        self._type_cap = type_cardinality_cap
        self._seen_types: set[str] = set()
        self._cap_warned = False

        if backend is not None:
            self._build()

    @classmethod
    def from_manager(cls, manager: Any, type_cardinality_cap: int = 64) -> ScrubMetrics:
        """Build :class:`ScrubMetrics` from a :class:`MetricsManager`."""
        return cls(backend=manager, type_cardinality_cap=type_cardinality_cap)

    @classmethod
    def noop(cls) -> ScrubMetrics:
        """Return a no-op instance for tests / when metrics are off."""
        return cls(backend=None)

    def _gate_type(self, type_: str) -> str:
        """Return the type-label to record after applying cardinality cap.

        Below the cap, returns ``type_`` unchanged and records it as
        seen. At/above the cap, returns ``"OVER_CAP"`` and emits a
        one-shot warning so operators know the cap fired.
        """
        if self._type_cap <= 0 or type_ in self._seen_types:
            return type_
        if len(self._seen_types) < self._type_cap:
            self._seen_types.add(type_)
            return type_
        if not self._cap_warned:
            import warnings as _w

            _w.warn(
                f"ScrubMetrics: distinct 'type' label cardinality reached "
                f"{self._type_cap}. Further new types are collapsed under "
                f"'OVER_CAP'. Raise ScrubConfig.metrics_type_cardinality_cap "
                f"or audit extra_patterns for unbounded operator-supplied "
                f"type names.",
                RuntimeWarning,
                stacklevel=4,
            )
            self._cap_warned = True
        return "OVER_CAP"

    def _build(self) -> None:
        """Register all six handles. Swallow any backend error silently."""
        try:
            self._matches = self._backend.counter(
                "log_scrub_matches_total",
                "Scrub matches found (whether redacted or observe-mode)",
                labels=["layer", "type"],
            )
            self._redactions = self._backend.counter(
                "log_scrub_redactions_total",
                "Scrub redactions actually applied to log text",
                labels=["layer", "type"],
            )
            self._errors = self._backend.counter(
                "log_scrub_errors_total",
                "Scrub layer failures (fail-safe trigger)",
                labels=["layer", "error_type"],
            )
            self._skipped = self._backend.gauge(
                "log_scrub_skipped_rules_total",
                "Scrub rules that couldn't compile in this implementation",
                labels=["layer", "rule_id"],
            )
            self._duration = self._backend.histogram(
                "log_scrub_duration_seconds",
                "Per-layer scrub time",
                labels=["layer"],
            )
            self._pattern_version = self._backend.gauge(
                "log_scrub_pattern_version",
                "Pattern-set version installed in this scrubber",
                labels=["source", "version"],
            )
        except Exception:
            # Defensive: a half-built ScrubMetrics still emits no-ops
            # because each .inc_* method checks for None handles.
            self._matches = None
            self._redactions = None
            self._errors = None
            self._skipped = None
            self._duration = None
            self._pattern_version = None

    def inc_match(self, layer: str, type_: str, n: int = 1) -> None:
        """Increment ``log_scrub_matches_total`` once per detected candidate."""
        if self._matches is None:
            return
        try:
            self._matches.labels(layer=layer, type=self._gate_type(type_)).inc(n)
        except Exception:
            pass

    def inc_redaction(self, layer: str, type_: str, n: int = 1) -> None:
        """Increment ``log_scrub_redactions_total`` once per applied redaction."""
        if self._redactions is None:
            return
        try:
            self._redactions.labels(layer=layer, type=self._gate_type(type_)).inc(n)
        except Exception:
            pass

    def inc_error(self, layer: str, error_type: str) -> None:
        """Increment ``log_scrub_errors_total`` on fail-safe trigger."""
        if self._errors is None:
            return
        try:
            self._errors.labels(layer=layer, error_type=error_type).inc()
        except Exception:
            pass

    def set_skipped(self, layer: str, rule_id: str, value: int = 1) -> None:
        """Set ``log_scrub_skipped_rules_total`` for rules that didn't compile."""
        if self._skipped is None:
            return
        try:
            self._skipped.labels(layer=layer, rule_id=rule_id).set(value)
        except Exception:
            pass

    def observe_duration(self, layer: str, seconds: float) -> None:
        """Observe a layer's scrub duration in ``log_scrub_duration_seconds``."""
        if self._duration is None:
            return
        try:
            self._duration.labels(layer=layer).observe(seconds)
        except Exception:
            pass

    def set_pattern_version(self, source: str, version: str) -> None:
        """Emit ``log_scrub_pattern_version{source, version}`` once at startup."""
        if self._pattern_version is None:
            return
        try:
            self._pattern_version.labels(source=source, version=version).set(1)
        except Exception:
            pass

    def __repr__(self) -> str:
        if self._backend is None:
            return "ScrubMetrics(noop)"
        return f"ScrubMetrics(backend={type(self._backend).__name__!s})"
