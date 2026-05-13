#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_labeler.py
#  Purpose:   Tests for redaction-label formatting (static + deterministic-hash)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the labeler module — static and deterministic-hash redaction."""

from __future__ import annotations

import re

import pytest

from hyperi_pylib.logger.scrub import (
    PiiConfig,
    PiiValidatorsConfig,
    ScrubConfig,
    SecretsConfig,
    build_scrubber,
    make_hash_labeler,
    resolve_labeler,
)
from hyperi_pylib.logger.scrub.labeler import _static_label


# ---------------------------------------------------------------------------
# Static labeler
# ---------------------------------------------------------------------------


class TestStaticLabeler:
    def test_static_collapses_to_redacted(self):
        assert _static_label("EMAIL", "alice@example.com") == "[EMAIL_REDACTED]"

    def test_static_ignores_value(self):
        # Same label, different value -> same output
        assert _static_label("EMAIL", "alice@x") == _static_label("EMAIL", "bob@y")


# ---------------------------------------------------------------------------
# Hash labeler
# ---------------------------------------------------------------------------


class TestHashLabeler:
    def test_format_is_label_hex6(self):
        labeler = make_hash_labeler(secret_hash_key=b"test-key")
        out = labeler("EMAIL", "alice@example.com")
        assert re.fullmatch(r"\[EMAIL_[0-9a-f]{6}\]", out)

    def test_determinism_within_labeler(self):
        labeler = make_hash_labeler(secret_hash_key=b"test-key")
        a = labeler("EMAIL", "alice@example.com")
        b = labeler("EMAIL", "alice@example.com")
        assert a == b  # same value -> same label

    def test_distinct_values_distinct_labels(self):
        labeler = make_hash_labeler(secret_hash_key=b"test-key")
        a = labeler("EMAIL", "alice@example.com")
        b = labeler("EMAIL", "bob@example.com")
        assert a != b

    def test_key_changes_output(self):
        l1 = make_hash_labeler(secret_hash_key=b"key1")
        l2 = make_hash_labeler(secret_hash_key=b"key2")
        assert l1("EMAIL", "alice@example.com") != l2("EMAIL", "alice@example.com")

    def test_env_var_key_used(self, monkeypatch):
        monkeypatch.setenv("HYPERI_LOG_SCRUB_HASH_KEY", "operator-cross-process-key")
        labeler = make_hash_labeler()  # None -> read env
        out = labeler("EMAIL", "alice@example.com")
        # Same env, same value -> deterministic
        again = make_hash_labeler()
        assert out == again("EMAIL", "alice@example.com")

    def test_no_key_uses_per_process_random(self, monkeypatch):
        monkeypatch.delenv("HYPERI_LOG_SCRUB_HASH_KEY", raising=False)
        l1 = make_hash_labeler()
        l2 = make_hash_labeler()
        # Independent instances with random keys -> different outputs
        assert l1("EMAIL", "alice@x") != l2("EMAIL", "alice@x")

    def test_oversized_key_truncated(self):
        # blake2b accepts key up to 64 bytes; longer keys are truncated.
        big_key = b"x" * 200
        labeler = make_hash_labeler(secret_hash_key=big_key)
        out = labeler("EMAIL", "alice@example.com")
        assert re.fullmatch(r"\[EMAIL_[0-9a-f]{6}\]", out)

    def test_unicode_value(self):
        labeler = make_hash_labeler(secret_hash_key=b"k")
        out = labeler("PERSON", "山田 太郎")
        assert re.fullmatch(r"\[PERSON_[0-9a-f]{6}\]", out)

    def test_empty_label(self):
        labeler = make_hash_labeler(secret_hash_key=b"k")
        out = labeler("", "alice@example.com")
        assert re.fullmatch(r"\[_[0-9a-f]{6}\]", out)


# ---------------------------------------------------------------------------
# resolve_labeler
# ---------------------------------------------------------------------------


class TestResolveLabeler:
    def test_hash_disabled_returns_static(self):
        labeler = resolve_labeler(hash_redaction=False)
        assert labeler is _static_label

    def test_hash_enabled_returns_hash_labeler(self):
        labeler = resolve_labeler(hash_redaction=True)
        out = labeler("EMAIL", "alice@example.com")
        assert re.fullmatch(r"\[EMAIL_[0-9a-f]{6}\]", out)


# ---------------------------------------------------------------------------
# Factory wiring — end to end
# ---------------------------------------------------------------------------


class TestFactoryHashRedaction:
    def test_default_uses_static_labels(self):
        s = build_scrubber()
        out = s.scrub("contact alice@example.com please")
        assert "[EMAIL_REDACTED]" in out

    def test_hash_redaction_replaces_email(self):
        s = build_scrubber(ScrubConfig(hash_redaction=True))
        out = s.scrub("contact alice@example.com please")
        # Email label now carries a 6-hex suffix, not _REDACTED
        assert re.search(r"\[EMAIL_[0-9a-f]{6}\]", out)
        assert "[EMAIL_REDACTED]" not in out
        assert "alice@example.com" not in out

    def test_hash_correlates_same_value(self):
        s = build_scrubber(ScrubConfig(hash_redaction=True))
        out = s.scrub("from alice@example.com to alice@example.com")
        labels = re.findall(r"\[EMAIL_[0-9a-f]{6}\]", out)
        assert len(labels) == 2
        assert labels[0] == labels[1]  # same value -> same suffix

    def test_hash_distinguishes_different_values(self):
        s = build_scrubber(ScrubConfig(hash_redaction=True))
        out = s.scrub("from alice@example.com to bob@example.com")
        labels = re.findall(r"\[EMAIL_[0-9a-f]{6}\]", out)
        assert len(labels) == 2
        assert labels[0] != labels[1]

    def test_hash_redaction_on_credit_card(self):
        s = build_scrubber(ScrubConfig(hash_redaction=True))
        out = s.scrub("paid with 4111-1111-1111-1111")
        assert re.search(r"\[CREDIT_CARD_[0-9a-f]{6}\]", out)
        assert "4111-1111-1111-1111" not in out

    def test_hash_redaction_on_abn_with_context(self):
        s = build_scrubber(ScrubConfig(hash_redaction=True))
        out = s.scrub("ABN: 53 004 085 616")
        assert re.search(r"\[AU_ABN_[0-9a-f]{6}\]", out)

    def test_l2_field_redaction_unchanged_by_hash_mode(self):
        # L2 field names use the static ***REDACTED*** mask regardless of
        # hash_redaction — field name carries the type signal, value-
        # correlation isn't useful when the schema is already visible.
        s = build_scrubber(ScrubConfig(hash_redaction=True))
        out = s.scrub("user logged in with password=hunter2")
        assert "hunter2" not in out
        assert "***REDACTED***" in out

    def test_observe_only_overrides_hash_redaction(self):
        # observe_only short-circuits BEFORE labels matter — the input
        # passes through unchanged regardless of hash mode.
        s = build_scrubber(ScrubConfig(observe_only=True, hash_redaction=True))
        text = "alice@example.com"
        assert s.scrub(text) == text


class TestHashRedactionDeterministicAcrossInstances:
    """Same hash key + same value should yield the same label across
    scrubber instances. Operators set HYPERI_LOG_SCRUB_HASH_KEY for
    cross-process correlation."""

    def test_explicit_env_key_yields_stable_labels(self, monkeypatch):
        monkeypatch.setenv("HYPERI_LOG_SCRUB_HASH_KEY", "ops-correlation-key")

        s1 = build_scrubber(ScrubConfig(hash_redaction=True))
        s2 = build_scrubber(ScrubConfig(hash_redaction=True))

        out1 = s1.scrub("alice@example.com")
        out2 = s2.scrub("alice@example.com")
        assert out1 == out2

    def test_no_env_key_yields_unstable_labels(self, monkeypatch):
        monkeypatch.delenv("HYPERI_LOG_SCRUB_HASH_KEY", raising=False)

        s1 = build_scrubber(ScrubConfig(hash_redaction=True))
        s2 = build_scrubber(ScrubConfig(hash_redaction=True))

        out1 = s1.scrub("alice@example.com")
        out2 = s2.scrub("alice@example.com")
        # Per-process random key -> different labels across instances
        assert out1 != out2
