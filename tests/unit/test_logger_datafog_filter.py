#  Project:   hyperi-pylib
#  File:      tests/unit/test_logger_datafog_filter.py
#  Purpose:   Tests for DataFogSensitiveDataFilter
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the DataFog-backed PII filter."""

from __future__ import annotations

import pytest

from hyperi_pylib.logger.filters import (
    DataFogSensitiveDataFilter,
    SensitiveDataFilter,
    get_sensitive_filter,
)


class TestDataFogFilterRegex:
    """The regex-only DataFog tier should catch PII *values*, not just field names."""

    def test_email_in_prose(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        out = f._mask_sensitive_string("Sent confirmation to alice@example.com")
        assert "alice@example.com" not in out
        assert "[EMAIL_" in out or "REDACTED" in out

    def test_phone_in_prose(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        out = f._mask_sensitive_string("Call us on (555) 123-4567 anytime")
        assert "555" not in out or "[PHONE_" in out

    def test_ssn(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        out = f._mask_sensitive_string("ssn 123-45-6789 on file")
        assert "123-45-6789" not in out

    def test_credit_card(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        out = f._mask_sensitive_string("paid with 4532-1488-0343-6467")
        # DataFog should detect the credit card pattern
        assert "4532-1488-0343-6467" not in out

    def test_field_name_also_masked(self):
        """Parent class regex still catches field-name patterns."""
        f = DataFogSensitiveDataFilter(engine="regex")
        out = f._mask_sensitive_string("password=hunter2 token=abc123")
        assert "hunter2" not in out
        assert "abc123" not in out

    def test_empty_string(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        assert f._mask_sensitive_string("") == ""

    def test_non_string_passthrough(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        assert f._mask_sensitive_string(None) is None  # type: ignore[arg-type]


class TestGetSensitiveFilterDispatch:
    """get_sensitive_filter() returns the right class for each tier."""

    def test_simple_returns_baseline_regex(self):
        f = get_sensitive_filter(level="simple")
        assert type(f) is SensitiveDataFilter

    def test_advanced_returns_datafog_regex(self):
        f = get_sensitive_filter(level="advanced")
        assert isinstance(f, DataFogSensitiveDataFilter)
        assert f._engine == "regex"

    def test_advanced_ner_returns_datafog_nlp(self):
        f = get_sensitive_filter(level="advanced-ner")
        assert isinstance(f, DataFogSensitiveDataFilter)
        # Either spacy (if installed) or regex (graceful degradation
        # when [pii-ner] isn't installed). Both are correct outcomes.
        assert f._engine in {"spacy", "regex"}

    def test_unknown_level_falls_back_to_simple(self):
        """Unknown level shouldn't crash — silently downgrade to simple."""
        f = get_sensitive_filter(level="bogus")
        assert type(f) is SensitiveDataFilter

    def test_extra_fields_threaded_through(self):
        f = get_sensitive_filter(level="advanced", extra_fields={"employee_id"})
        assert "employee_id" in f._instance_fields


class TestDataFogFilterIntegration:
    """End-to-end: DataFog filter catches both PII values AND secret field names."""

    def test_combined_pii_and_secrets(self):
        f = DataFogSensitiveDataFilter(engine="regex")
        text = (
            "User alice@example.com authenticated with password=hunter2 "
            "and token=eyJhbGciOiJIUzI1NiJ9.payload from IP 192.168.1.1"
        )
        out = f._mask_sensitive_string(text)
        # PII values gone
        assert "alice@example.com" not in out
        assert "192.168.1.1" not in out
        # Secret field values gone
        assert "hunter2" not in out
        assert "eyJhbGciOiJIUzI1NiJ9.payload" not in out
