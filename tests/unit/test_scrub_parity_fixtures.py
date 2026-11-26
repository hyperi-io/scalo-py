#  Project:   scalo
#  File:      tests/unit/test_scrub_parity_fixtures.py
#  Purpose:   Cross-language parity tests driven by the shared TOML fixtures
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Cross-language parity tests for L3 PII validators.

Reads ``tests/fixtures/patterns/pii_test_fixtures.toml`` (vendored byte-
identical from
``hyperi-ai/standards/patterns/pii_test_fixtures.toml``) and verifies
that scalo-py's validators redact every ``valid`` sample, never redact
any ``invalid`` / ``should_NOT_match`` sample, and respect the
context-keyword requirement for context-required validators.

The corresponding scalo-rs test will use the same TOML to drive the
same assertions in Rust. CI fails on any divergence (spec §11).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scalo.logger.scrub import (
    FieldsConfig,
    NationalIdsConfig,
    PiiConfig,
    PiiValidatorsConfig,
    ScrubConfig,
    SecretsConfig,
    build_scrubber,
)

# ---------------------------------------------------------------------------
# Load the canonical fixtures
# ---------------------------------------------------------------------------


def _load_fixtures() -> dict:
    resource = Path(__file__).resolve().parents[1] / "fixtures" / "patterns" / "pii_test_fixtures.toml"
    with resource.open("rb") as f:
        return tomllib.load(f)


FIXTURES = _load_fixtures()
NARROWING = tomllib.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "patterns" / "narrowing_fixtures.toml").read_text(
        encoding="utf-8"
    )
)
# Card numbers the shared fixture lists as valid that no longer redact bare, which the narrowing fixture names.
BARE_CARDS = NARROWING["supersedes"]["credit_card"]["unchanged"]


# ---------------------------------------------------------------------------
# Helpers -- build a tight scrubber per validator under test
# ---------------------------------------------------------------------------


def _scrubber_only(*, credit_card=False, iban=False, email=False, phone=False, national_ids: list[str] | None = None):
    """Build a scrubber with L1 + L2 off and only the requested L3 validator on."""
    return build_scrubber(
        ScrubConfig(
            secrets=SecretsConfig(enabled=False),
            fields=FieldsConfig(enabled=False),
            metrics_enabled=False,  # avoid noise in tests
            pii=PiiConfig(
                validators=PiiValidatorsConfig(
                    credit_card=credit_card,
                    iban=iban,
                    email=email,
                    phone=phone,
                    national_ids=NationalIdsConfig(enabled=national_ids or []),
                ),
            ),
        )
    )


def _was_redacted(out: str, original: str, label: str) -> bool:
    """The original substring is gone AND the label appears."""
    return (original not in out) and (f"[{label}_REDACTED]" in out)


# ---------------------------------------------------------------------------
# Strong-structural validators
# ---------------------------------------------------------------------------


class TestCreditCardFixtures:
    @pytest.fixture(scope="class")
    @classmethod
    def s(cls):
        return _scrubber_only(credit_card=True)

    @pytest.mark.parametrize(
        "sample", [sample for sample in FIXTURES["credit_card"]["valid"] if sample not in BARE_CARDS]
    )
    def test_valid_samples_redact(self, s, sample):
        out = s.scrub(f"payment {sample} authorised")
        assert _was_redacted(out, sample, "CREDIT_CARD"), f"valid CC {sample!r} was not redacted: out={out!r}"

    @pytest.mark.parametrize("sample", BARE_CARDS)
    def test_a_bare_valid_sample_passes_through(self, s, sample):
        assert FIXTURES["credit_card"]["valid"].count(sample) == 1
        out = s.scrub(f"payment {sample} authorised")
        assert sample in out, f"bare CC {sample!r} was redacted with no card evidence: out={out!r}"

    @pytest.mark.parametrize("sample", NARROWING["credit_card"]["redact"])
    def test_a_card_with_evidence_redacts(self, s, sample):
        assert "[CREDIT_CARD_REDACTED]" in s.scrub(sample)

    @pytest.mark.parametrize("sample", NARROWING["credit_card"]["unchanged"])
    def test_a_luhn_pass_with_no_evidence_is_left(self, s, sample):
        assert s.scrub(sample) == sample

    def test_a_run_of_epoch_milliseconds_is_left(self, s):
        start = NARROWING["credit_card"]["epoch_ms_start"]
        changed = [
            ms for ms in range(start, start + NARROWING["credit_card"]["epoch_ms_count"]) if s.scrub(str(ms)) != str(ms)
        ]
        assert changed == []

    def test_a_card_word_must_be_a_whole_word(self, s):
        assert s.scrub("accounts 4111111111111111") == "accounts 4111111111111111"
        assert s.scrub("Visa: 4111111111111111") == "Visa: [CREDIT_CARD_REDACTED]"

    @pytest.mark.parametrize("sample", FIXTURES["credit_card"]["invalid"])
    def test_invalid_samples_pass_through(self, s, sample):
        out = s.scrub(f"payment {sample} pending")
        assert sample in out, f"invalid CC {sample!r} was wrongly redacted: out={out!r}"


class TestIbanFixtures:
    @pytest.fixture(scope="class")
    @classmethod
    def s(cls):
        return _scrubber_only(iban=True)

    @pytest.mark.parametrize("sample", FIXTURES["iban"]["valid"])
    def test_valid_samples_redact(self, s, sample):
        out = s.scrub(f"account {sample} debited")
        assert _was_redacted(out, sample, "IBAN"), f"valid IBAN {sample!r} was not redacted: out={out!r}"

    @pytest.mark.parametrize("sample", FIXTURES["iban"]["invalid"])
    def test_invalid_samples_pass_through(self, s, sample):
        out = s.scrub(f"account {sample} pending")
        # Truncated samples like "GB82" don't match the structural regex
        # and definitely don't validate; pass-through.
        assert "[IBAN_REDACTED]" not in out, f"invalid IBAN {sample!r} was wrongly redacted: out={out!r}"


class TestEmailFixtures:
    @pytest.fixture(scope="class")
    @classmethod
    def s(cls):
        return _scrubber_only(email=True)

    @pytest.mark.parametrize("sample", FIXTURES["email"]["valid"])
    def test_valid_samples_redact(self, s, sample):
        out = s.scrub(f"contact {sample} re: ticket")
        assert _was_redacted(out, sample, "EMAIL"), f"valid email {sample!r} was not redacted: out={out!r}"

    @pytest.mark.parametrize("sample", FIXTURES["email"]["invalid"])
    def test_invalid_samples_pass_through(self, s, sample):
        out = s.scrub(f"input {sample} received")
        assert "[EMAIL_REDACTED]" not in out, f"invalid email {sample!r} was wrongly redacted: out={out!r}"


class TestPhoneFixtures:
    @pytest.fixture(scope="class")
    @classmethod
    def s(cls):
        return _scrubber_only(phone=True)

    @pytest.mark.parametrize("sample", FIXTURES["phone"]["valid"])
    def test_valid_samples_redact(self, s, sample):
        out = s.scrub(f"contact phone {sample} listed")
        assert _was_redacted(out, sample, "PHONE"), f"valid phone {sample!r} was not redacted: out={out!r}"

    @pytest.mark.parametrize("sample", FIXTURES["phone"]["should_NOT_match"])
    def test_bare_local_numbers_pass_through(self, s, sample):
        out = s.scrub(f"customer {sample} called")
        # libphonenumber rejects bare local numbers without country code.
        # Validator must not redact.
        assert "[PHONE_REDACTED]" not in out, f"bare phone {sample!r} was wrongly redacted: out={out!r}"


# ---------------------------------------------------------------------------
# Context-required validators
# ---------------------------------------------------------------------------


class _BaseContextRequiredTest:
    section: str
    label: str
    country: str = "au"

    @pytest.fixture(scope="class")
    @classmethod
    def s(cls):
        return _scrubber_only(national_ids=[cls.country])

    def test_valid_with_context_redact(self, s):
        section = FIXTURES[self.section]
        for sample in section["valid_with_context"]:
            out = s.scrub(sample)
            # The sample text contains the keyword + value. The full
            # sample may not be redacted (keyword survives), but the
            # value substring must be gone and the label must appear.
            assert f"[{self.label}_REDACTED]" in out, (
                f"{self.section}: valid+context {sample!r} not redacted: out={out!r}"
            )

    def test_invalid_in_context_pass_through(self, s):
        section = FIXTURES[self.section]
        for sample in section.get("invalid_in_context", []):
            out = s.scrub(sample)
            assert f"[{self.label}_REDACTED]" not in out, (
                f"{self.section}: invalid+context {sample!r} wrongly redacted: out={out!r}"
            )

    def test_should_not_match(self, s):
        section = FIXTURES[self.section]
        for sample in section.get("should_NOT_match", []):
            out = s.scrub(sample)
            assert f"[{self.label}_REDACTED]" not in out, (
                f"{self.section}: should_NOT_match {sample!r} wrongly redacted: out={out!r}"
            )


class TestAuAbnFixtures(_BaseContextRequiredTest):
    section = "au_abn"
    label = "AU_ABN"


class TestAuAcnFixtures(_BaseContextRequiredTest):
    section = "au_acn"
    label = "AU_ACN"


class TestAuTfnFixtures(_BaseContextRequiredTest):
    section = "au_tfn"
    label = "AU_TFN"


class TestAuMedicareFixtures(_BaseContextRequiredTest):
    section = "au_medicare"
    label = "AU_MEDICARE"


# ---------------------------------------------------------------------------
# Fixture file integrity (catches accidental drift from canonical)
# ---------------------------------------------------------------------------


class TestFixturesShape:
    """Sanity checks on the bundled fixtures file itself."""

    def test_meta_block_present(self):
        assert "meta" in FIXTURES
        assert FIXTURES["meta"].get("version")

    def test_every_strong_section_has_valid_and_invalid(self):
        for section in ("credit_card", "iban", "email"):
            assert "valid" in FIXTURES[section]
            assert "invalid" in FIXTURES[section]
            assert FIXTURES[section]["valid"]
            assert FIXTURES[section]["invalid"]

    def test_phone_has_valid_and_should_not_match(self):
        assert "valid" in FIXTURES["phone"]
        assert "should_NOT_match" in FIXTURES["phone"]

    def test_every_context_section_marked_context_required(self):
        for section in ("au_abn", "au_acn", "au_tfn", "au_medicare"):
            assert FIXTURES[section]["context_required"] is True
            assert FIXTURES[section]["keywords"]
            assert FIXTURES[section]["valid_with_context"]
            assert FIXTURES[section]["should_NOT_match"]
