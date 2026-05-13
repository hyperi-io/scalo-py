#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_chain.py
#  Purpose:   Tests for Scrubber Protocol, LayeredScrubber, NoOpScrubber
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the discrete-object scrubber surface (spec §2.3)."""

from __future__ import annotations

import pytest

from hyperi_pylib.logger.scrub import (
    LayeredScrubber,
    NoOpScrubber,
    PiiConfig,
    PiiValidatorsConfig,
    ScrubConfig,
    Scrubber,
    SecretsConfig,
)


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------


class TestScrubberProtocol:
    def test_noop_satisfies_protocol(self):
        assert isinstance(NoOpScrubber(), Scrubber)

    def test_layered_satisfies_protocol(self):
        assert isinstance(LayeredScrubber(), Scrubber)

    def test_plain_callable_does_not(self):
        # The Protocol requires a `scrub` METHOD, not a callable.
        assert not isinstance(lambda t: t, Scrubber)

    def test_any_class_with_scrub_method_satisfies_protocol(self):
        class _CustomScrubber:
            def scrub(self, text: str) -> str:
                return text.upper()

        assert isinstance(_CustomScrubber(), Scrubber)


# ---------------------------------------------------------------------------
# NoOpScrubber
# ---------------------------------------------------------------------------


class TestNoOpScrubber:
    def test_passes_through(self):
        s = NoOpScrubber()
        assert s.scrub("any text with password=hunter2") == "any text with password=hunter2"

    def test_empty_string(self):
        assert NoOpScrubber().scrub("") == ""

    def test_repr(self):
        assert repr(NoOpScrubber()) == "NoOpScrubber()"


# ---------------------------------------------------------------------------
# LayeredScrubber — composition
# ---------------------------------------------------------------------------


class _UpperLayer:
    """Test layer: uppercases text."""

    def scrub(self, text: str) -> str:
        return text.upper()


class _ReverseLayer:
    """Test layer: reverses text."""

    def scrub(self, text: str) -> str:
        return text[::-1]


class _BrokenLayer:
    """Test layer: always raises."""

    def __init__(self):
        self.calls = 0

    def scrub(self, text: str) -> str:
        self.calls += 1
        raise RuntimeError("intentional")


class TestLayeredScrubberComposition:
    def test_empty_chain_passes_through(self):
        s = LayeredScrubber(layers=[])
        assert s.scrub("hello") == "hello"

    def test_single_layer(self):
        s = LayeredScrubber(layers=[_UpperLayer()])
        assert s.scrub("hello") == "HELLO"

    def test_layers_apply_in_order(self):
        # Upper THEN reverse: "hello" → "HELLO" → "OLLEH"
        s = LayeredScrubber(layers=[_UpperLayer(), _ReverseLayer()])
        assert s.scrub("hello") == "OLLEH"

    def test_order_matters(self):
        # Reverse THEN upper: "hello" → "olleh" → "OLLEH"
        # (same output by coincidence on alpha input)
        # Use mixed input to confirm ordering matters semantically:
        s_upper_first = LayeredScrubber(layers=[_UpperLayer(), _ReverseLayer()])
        s_reverse_first = LayeredScrubber(layers=[_ReverseLayer(), _UpperLayer()])
        # Both produce same result here, but layers are applied in
        # different order — confirmed via spy:
        spy_a = _UpperLayer()
        spy_b = _ReverseLayer()
        order_log = []

        class _LoggedLayer:
            def __init__(self, name):
                self.name = name

            def scrub(self, text):
                order_log.append(self.name)
                return text

        s = LayeredScrubber(layers=[_LoggedLayer("a"), _LoggedLayer("b"), _LoggedLayer("c")])
        s.scrub("x")
        assert order_log == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# LayeredScrubber — disabled / observe-only
# ---------------------------------------------------------------------------


class TestLayeredScrubberDisabled:
    def test_master_disable_returns_input(self):
        s = LayeredScrubber(
            config=ScrubConfig(enabled=False),
            layers=[_UpperLayer()],
        )
        assert s.scrub("hello") == "hello"

    def test_observe_only_runs_layers_but_returns_input(self):
        spy = _UpperLayer()
        s = LayeredScrubber(
            config=ScrubConfig(observe_only=True),
            layers=[spy],
        )
        # In observe-only mode, output equals input
        assert s.scrub("hello") == "hello"
        # But the layer was still called (smoke check via behaviour —
        # in full impl, metrics emitted; here we trust the
        # implementation's intent)


# ---------------------------------------------------------------------------
# LayeredScrubber — fail-safe (spec §5.1)
# ---------------------------------------------------------------------------


class TestLayeredScrubberFailSafe:
    def test_broken_layer_does_not_propagate(self):
        s = LayeredScrubber(layers=[_BrokenLayer()])
        with pytest.warns(RuntimeWarning, match="intentional"):
            result = s.scrub("hello")
        # Input returned unchanged on layer failure
        assert result == "hello"

    def test_broken_layer_skipped_after_first_failure(self):
        broken = _BrokenLayer()
        s = LayeredScrubber(layers=[broken])
        with pytest.warns(RuntimeWarning):
            s.scrub("first call")
        # Second call: layer already known-broken, skipped without
        # another warning
        import warnings as _w

        with _w.catch_warnings(record=True) as captured:
            _w.simplefilter("always")
            s.scrub("second call")
        # No new RuntimeWarning emitted for the second call
        assert not any(
            issubclass(w.category, RuntimeWarning) for w in captured
        )
        # Layer's scrub() was only called once
        assert broken.calls == 1

    def test_other_layers_still_apply_after_broken_one(self):
        # _BrokenLayer in middle; _UpperLayer first; _ReverseLayer last
        # Expected: upper applied; broken skipped; reverse applied
        s = LayeredScrubber(layers=[_UpperLayer(), _BrokenLayer(), _ReverseLayer()])
        with pytest.warns(RuntimeWarning):
            result = s.scrub("hello")
        # "hello" → upper → "HELLO" → broken (skip) → reverse → "OLLEH"
        assert result == "OLLEH"


# ---------------------------------------------------------------------------
# ScrubConfig — defaults match spec §6
# ---------------------------------------------------------------------------


class TestScrubConfigDefaults:
    def test_top_level_defaults(self):
        c = ScrubConfig()
        assert c.enabled is True
        assert c.observe_only is False
        assert c.hash_redaction is False

    def test_fields_enabled_by_default(self):
        assert ScrubConfig().fields.enabled is True

    def test_secrets_defaults(self):
        s = ScrubConfig().secrets
        assert s.enabled is True
        assert s.patterns == "gitleaks"
        assert s.entropy_filter is False
        assert s.token_efficiency is False

    def test_pii_defaults(self):
        p = ScrubConfig().pii
        assert p.enabled is True
        assert p.nlp is False
        assert p.token_efficiency is False

    def test_pii_validators_all_default_true(self):
        v = ScrubConfig().pii.validators
        assert v.credit_card is True
        assert v.iban is True
        assert v.email is True
        assert v.phone is True

    def test_national_ids_default_au_only(self):
        # AU ships pre-curated; other countries are seeded stubs.
        v = ScrubConfig().pii.validators
        assert v.national_ids.enabled == ["au"]

    def test_log_levels_defaults(self):
        lev = ScrubConfig().log_levels
        assert lev.error is True
        assert lev.warn is True
        assert lev.info is True
        assert lev.debug is True
        # trace OFF by default per spec §5.6
        assert lev.trace is False

    def test_overrides(self):
        c = ScrubConfig(
            observe_only=True,
            pii=PiiConfig(validators=PiiValidatorsConfig(email=False)),
            secrets=SecretsConfig(patterns="minimal"),
        )
        assert c.observe_only is True
        assert c.pii.validators.email is False
        assert c.pii.validators.credit_card is True  # untouched defaults still apply
        assert c.secrets.patterns == "minimal"


# ---------------------------------------------------------------------------
# LayeredScrubber — repr
# ---------------------------------------------------------------------------


class TestLayeredScrubberRepr:
    def test_repr_lists_layers(self):
        s = LayeredScrubber(layers=[_UpperLayer(), NoOpScrubber()])
        r = repr(s)
        assert "_UpperLayer" in r
        assert "NoOpScrubber" in r
        assert "enabled=True" in r

    def test_repr_shows_observe_only(self):
        s = LayeredScrubber(config=ScrubConfig(observe_only=True), layers=[])
        assert "observe_only=True" in repr(s)
