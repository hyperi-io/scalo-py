#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_metrics.py
#  Purpose:   Tests for ScrubMetrics emission per spec §8
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the ScrubMetrics class and end-to-end metric emission."""

from __future__ import annotations

from collections import defaultdict

import pytest

from hyperi_pylib.logger.scrub import (
    NationalIdsConfig,
    PiiConfig,
    PiiValidatorsConfig,
    ScrubConfig,
    ScrubMetrics,
    SecretsConfig,
    build_scrubber,
)

# ---------------------------------------------------------------------------
# Fake metrics backend — records every call for assertion
# ---------------------------------------------------------------------------


class _FakeMetric:
    """Records labels()/inc()/set()/observe() calls for assertion."""

    def __init__(self, name: str, recorder: _FakeBackend) -> None:
        self.name = name
        self._recorder = recorder

    def labels(self, **kwargs: object) -> _FakeMetric:
        # Return a labelled child; record the label set lazily on call.
        return _FakeLabelled(self.name, dict(kwargs), self._recorder)


class _FakeLabelled:
    def __init__(self, name: str, labels: dict, recorder: _FakeBackend) -> None:
        self.name = name
        self.labels_ = labels
        self._recorder = recorder

    def inc(self, n: int = 1) -> None:
        self._recorder.events.append(("inc", self.name, self.labels_, n))

    def set(self, value: float) -> None:
        self._recorder.events.append(("set", self.name, self.labels_, value))

    def observe(self, value: float) -> None:
        self._recorder.events.append(("observe", self.name, self.labels_, value))


class _FakeBackend:
    """Minimal MetricsManager-like backend that ScrubMetrics can drive."""

    def __init__(self) -> None:
        self.events: list = []
        self.built: dict[str, str] = {}

    def counter(self, name: str, description: str, labels: list[str] | None = None) -> _FakeMetric:
        self.built[name] = "counter"
        return _FakeMetric(name, self)

    def gauge(self, name: str, description: str, labels: list[str] | None = None) -> _FakeMetric:
        self.built[name] = "gauge"
        return _FakeMetric(name, self)

    def histogram(
        self, name: str, description: str, labels: list[str] | None = None, buckets: tuple = None
    ) -> _FakeMetric:
        self.built[name] = "histogram"
        return _FakeMetric(name, self)


# ---------------------------------------------------------------------------
# ScrubMetrics — no-op contract
# ---------------------------------------------------------------------------


class TestScrubMetricsNoOp:
    def test_default_noop_construction(self):
        m = ScrubMetrics()
        # All emit methods are no-ops; no exceptions, no side effects
        m.inc_match("L1", "EMAIL")
        m.inc_redaction("L3", "AU_ABN")
        m.inc_error("LayeredScrubber", "ValueError")
        m.set_skipped("L1", "rule_x")
        m.observe_duration("L2", 0.001)
        m.set_pattern_version("gitleaks", "1.0.0")

    def test_noop_factory(self):
        m = ScrubMetrics.noop()
        assert "noop" in repr(m)

    def test_from_manager_with_none_is_noop(self):
        m = ScrubMetrics(backend=None)
        assert "noop" in repr(m)


# ---------------------------------------------------------------------------
# ScrubMetrics — wired to a fake backend
# ---------------------------------------------------------------------------


class TestScrubMetricsWiring:
    def test_register_six_handles_on_build(self):
        backend = _FakeBackend()
        ScrubMetrics(backend=backend)
        assert backend.built == {
            "log_scrub_matches_total": "counter",
            "log_scrub_redactions_total": "counter",
            "log_scrub_errors_total": "counter",
            "log_scrub_skipped_rules_total": "gauge",
            "log_scrub_duration_seconds": "histogram",
            "log_scrub_pattern_version": "gauge",
        }

    def test_inc_match_records_event(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend)
        m.inc_match("L1", "GITHUB_TOKEN")
        assert ("inc", "log_scrub_matches_total", {"layer": "L1", "type": "GITHUB_TOKEN"}, 1) in backend.events

    def test_inc_redaction_records_event(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend)
        m.inc_redaction("L3", "EMAIL", n=2)
        assert ("inc", "log_scrub_redactions_total", {"layer": "L3", "type": "EMAIL"}, 2) in backend.events

    def test_inc_error_records_event(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend)
        m.inc_error("LayeredScrubber", "ValueError")
        assert (
            "inc",
            "log_scrub_errors_total",
            {"layer": "LayeredScrubber", "error_type": "ValueError"},
            1,
        ) in backend.events

    def test_observe_duration(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend)
        m.observe_duration("L2", 0.005)
        assert ("observe", "log_scrub_duration_seconds", {"layer": "L2"}, 0.005) in backend.events

    def test_set_pattern_version(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend)
        m.set_pattern_version("gitleaks", "1.5.0")
        assert ("set", "log_scrub_pattern_version", {"source": "gitleaks", "version": "1.5.0"}, 1) in backend.events

    def test_backend_exception_swallowed(self):
        """Broken backend must not propagate — scrubber stays alive."""

        class _BrokenBackend:
            def counter(self, *a, **k):
                raise RuntimeError("kaboom")

            def gauge(self, *a, **k):
                raise RuntimeError("kaboom")

            def histogram(self, *a, **k):
                raise RuntimeError("kaboom")

        # Construction must not raise even though every handle fails.
        m = ScrubMetrics(backend=_BrokenBackend())
        # Every emit method is then a no-op.
        m.inc_match("L1", "EMAIL")
        m.observe_duration("L2", 0.001)


# ---------------------------------------------------------------------------
# End-to-end — factory wires metrics into all layers
# ---------------------------------------------------------------------------


class TestFactoryEmitsMetrics:
    @pytest.fixture
    def backend(self) -> _FakeBackend:
        return _FakeBackend()

    @pytest.fixture
    def metrics(self, backend: _FakeBackend) -> ScrubMetrics:
        return ScrubMetrics.from_manager(backend)

    def _events_by_name(self, backend: _FakeBackend) -> dict[str, list]:
        out = defaultdict(list)
        for ev in backend.events:
            out[ev[1]].append(ev)
        return out

    def test_email_redaction_emits_match_and_redaction(self, backend, metrics):
        s = build_scrubber(metrics=metrics)
        s.scrub("contact alice@example.com please")
        events = self._events_by_name(backend)
        # at least one L3 EMAIL match and one redaction
        emails_matched = [ev for ev in events["log_scrub_matches_total"] if ev[2] == {"layer": "L3", "type": "EMAIL"}]
        emails_redacted = [
            ev for ev in events["log_scrub_redactions_total"] if ev[2] == {"layer": "L3", "type": "EMAIL"}
        ]
        assert len(emails_matched) >= 1
        assert len(emails_redacted) >= 1

    def test_credit_card_redaction_emits_metrics(self, backend, metrics):
        s = build_scrubber(metrics=metrics)
        s.scrub("paid with 4111-1111-1111-1111")
        events = self._events_by_name(backend)
        cc = [ev for ev in events["log_scrub_redactions_total"] if ev[2] == {"layer": "L3", "type": "CREDIT_CARD"}]
        assert len(cc) >= 1

    def test_abn_redaction_with_context_emits_metrics(self, backend, metrics):
        s = build_scrubber(metrics=metrics)
        s.scrub("ABN: 53 004 085 616")
        events = self._events_by_name(backend)
        abn_match = [ev for ev in events["log_scrub_matches_total"] if ev[2] == {"layer": "L3", "type": "AU_ABN"}]
        abn_red = [ev for ev in events["log_scrub_redactions_total"] if ev[2] == {"layer": "L3", "type": "AU_ABN"}]
        assert len(abn_match) >= 1
        assert len(abn_red) >= 1

    def test_abn_without_context_emits_match_but_no_redaction(self, backend, metrics):
        # Context-required validator: regex matches but keyword absent →
        # match counter ticks, redaction counter does not.
        s = build_scrubber(
            ScrubConfig(
                secrets=SecretsConfig(enabled=False),
                pii=PiiConfig(
                    validators=PiiValidatorsConfig(
                        credit_card=False,
                        iban=False,
                        email=False,
                        phone=False,
                    ),
                ),
            ),
            metrics=metrics,
        )
        # No "abn" keyword — regex still matches the digit run though
        s.scrub("Request 53004085616 logged")
        events = self._events_by_name(backend)
        abn_match = [ev for ev in events["log_scrub_matches_total"] if ev[2] == {"layer": "L3", "type": "AU_ABN"}]
        abn_red = [ev for ev in events["log_scrub_redactions_total"] if ev[2] == {"layer": "L3", "type": "AU_ABN"}]
        assert len(abn_match) >= 1
        assert len(abn_red) == 0

    def test_aws_key_emits_l1_metrics(self, backend, metrics):
        s = build_scrubber(metrics=metrics)
        s.scrub("AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE leaked")
        events = self._events_by_name(backend)
        # Some L1 metric for an AWS-related key fired (detect-secrets
        # type names vary by version — assert at least one L1 redaction).
        l1_red = [ev for ev in events["log_scrub_redactions_total"] if ev[2].get("layer") == "L1"]
        assert len(l1_red) >= 1

    def test_duration_observed_per_layer(self, backend, metrics):
        s = build_scrubber(metrics=metrics)
        s.scrub("password=hunter2")
        events = self._events_by_name(backend)
        durations = events["log_scrub_duration_seconds"]
        # At least three layers ran (L1, L2, plus some L3 validators)
        assert len(durations) >= 3
        # Each duration is non-negative
        for _, _, _, v in durations:
            assert v >= 0

    def test_error_count_on_broken_layer(self, backend, metrics):
        # Inject a layer that raises to exercise the fail-safe path.
        from hyperi_pylib.logger.scrub import LayeredScrubber

        class _Boom:
            def scrub(self, text: str) -> str:
                raise ValueError("intentional")

        s = LayeredScrubber(layers=[_Boom()], metrics=metrics)
        s.scrub("payload")
        events = self._events_by_name(backend)
        errors = events["log_scrub_errors_total"]
        assert any(ev[2] == {"layer": "_Boom", "error_type": "ValueError"} for ev in errors)

    def test_pattern_version_emitted_on_build(self, backend, metrics):
        # build_scrubber calls set_pattern_version() for detect-secrets +
        # national_ids + phonenumbers at construction.
        build_scrubber(metrics=metrics)
        events = self._events_by_name(backend)
        sources = {ev[2]["source"] for ev in events["log_scrub_pattern_version"]}
        # detect-secrets and phonenumbers are guaranteed package deps;
        # national_ids registry version may or may not be present depending
        # on whether the TOML has a _meta block.
        assert "detect-secrets" in sources
        assert "phonenumbers" in sources


class TestMetricsEnabledKillSwitch:
    """ScrubConfig.metrics_enabled=False forces noop even if caller passes a backend."""

    def test_enabled_false_forces_noop(self):
        backend = _FakeBackend()
        metrics = ScrubMetrics.from_manager(backend)
        cfg = ScrubConfig(metrics_enabled=False)
        s = build_scrubber(cfg, metrics=metrics)
        s.scrub("alice@example.com password=hunter2")
        # No events recorded — the kill-switch dropped the backend.
        assert backend.events == []

    def test_enabled_true_records_events(self):
        backend = _FakeBackend()
        metrics = ScrubMetrics.from_manager(backend)
        cfg = ScrubConfig(metrics_enabled=True)
        s = build_scrubber(cfg, metrics=metrics)
        s.scrub("alice@example.com")
        assert len(backend.events) > 0


class TestCardinalityCap:
    """Soft cap on distinct `type` labels protects against label explosion."""

    def test_below_cap_passes_through(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend, type_cardinality_cap=5)
        for type_ in ("A", "B", "C"):
            m.inc_match("L1", type_)
        # All three recorded under their own type labels.
        recorded = [ev[2]["type"] for ev in backend.events if ev[1] == "log_scrub_matches_total"]
        assert sorted(recorded) == ["A", "B", "C"]

    def test_cap_collapses_to_over_cap(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend, type_cardinality_cap=2)

        m.inc_match("L1", "A")
        m.inc_match("L1", "B")
        # Third distinct type triggers the cap
        import warnings as _w

        with _w.catch_warnings(record=True) as warned:
            _w.simplefilter("always")
            m.inc_match("L1", "C")
        assert any(issubclass(w.category, RuntimeWarning) for w in warned)

        recorded = [ev[2]["type"] for ev in backend.events if ev[1] == "log_scrub_matches_total"]
        assert recorded.count("A") == 1
        assert recorded.count("B") == 1
        assert recorded.count("OVER_CAP") == 1
        assert "C" not in recorded

    def test_cap_warns_only_once(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend, type_cardinality_cap=1)

        import warnings as _w

        with _w.catch_warnings(record=True) as warned:
            _w.simplefilter("always")
            m.inc_match("L1", "A")  # accepted, under cap
            m.inc_match("L1", "B")  # over cap — warn
            m.inc_match("L1", "C")  # over cap — silent
            m.inc_match("L1", "D")  # over cap — silent
        cap_warns = [w for w in warned if "OVER_CAP" in str(w.message) or "cardinality" in str(w.message)]
        assert len(cap_warns) == 1

    def test_zero_cap_disables_cap_entirely(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend, type_cardinality_cap=0)
        for type_ in ("A", "B", "C", "D", "E", "F", "G", "H"):
            m.inc_match("L1", type_)
        recorded = [ev[2]["type"] for ev in backend.events if ev[1] == "log_scrub_matches_total"]
        assert set(recorded) == {"A", "B", "C", "D", "E", "F", "G", "H"}

    def test_cap_is_shared_across_match_and_redaction(self):
        backend = _FakeBackend()
        m = ScrubMetrics(backend=backend, type_cardinality_cap=2)
        m.inc_match("L1", "A")
        m.inc_match("L1", "B")
        # match counter already saw A,B — redaction with NEW type "C"
        # should now overflow.
        import warnings as _w

        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            m.inc_redaction("L1", "C")
        recorded = [ev[2]["type"] for ev in backend.events if ev[1] == "log_scrub_redactions_total"]
        assert recorded == ["OVER_CAP"]


class TestMetricsDoNotAffectOutput:
    """Metric emission must not change the scrubber's behaviour."""

    def test_with_metrics_yields_same_output_as_without(self):
        cfg = ScrubConfig()
        out_no_metrics = build_scrubber(cfg).scrub("alice@example.com")
        out_with_metrics = build_scrubber(
            cfg,
            metrics=ScrubMetrics(backend=_FakeBackend()),
        ).scrub("alice@example.com")
        assert out_no_metrics == out_with_metrics

    def test_observe_only_with_metrics_still_short_circuits(self):
        cfg = ScrubConfig(observe_only=True)
        backend = _FakeBackend()
        metrics = ScrubMetrics(backend=backend)
        s = build_scrubber(cfg, metrics=metrics)
        text = "alice@example.com"
        assert s.scrub(text) == text
        # But the match counter still increments (observe-mode visibility)
        events = [
            ev
            for ev in backend.events
            if ev[1] == "log_scrub_matches_total" and ev[2] == {"layer": "L3", "type": "EMAIL"}
        ]
        assert len(events) >= 1
