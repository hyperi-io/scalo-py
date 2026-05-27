#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_parity_fixtures.py
#  Purpose:   Cross-language parity tests driven by the shared TOML fixtures
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Cross-language parity tests for L3 PII validators.

Reads ``hyperi_pylib/data/pii_test_fixtures.toml`` (vendored byte-
identical from
``hyperi-ai/standards/patterns/pii_test_fixtures.toml``) and verifies
that pylib's validators redact every ``valid`` sample, never redact
any ``invalid`` / ``should_NOT_match`` sample, and respect the
context-keyword requirement for context-required validators.

The corresponding rustlib test will use the same TOML to drive the
same assertions in Rust. CI fails on any divergence (spec §11).
"""

from __future__ import annotations

import tomllib
from importlib import resources

import pytest

from hyperi_pylib.logger.scrub import (
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
    resource = resources.files("hyperi_pylib") / "data" / "pii_test_fixtures.toml"
    with resource.open("rb") as f:
        return tomllib.load(f)


FIXTURES = _load_fixtures()


# ---------------------------------------------------------------------------
# Helpers -- build a tight scrubber per validator under test
# ---------------------------------------------------------------------------


def _scrubber_only(*, credit_card=False, iban=False, email=False, phone=False, national_ids: list[str] | None = None):
    """Build a scrubber with L1 + L2 off and only the requested L3 validator on."""
    return build_scrubber(
        ScrubConfig(
            secrets=SecretsConfig(enabled=False),
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
    def s(self):
        return _scrubber_only(credit_card=True)

    @pytest.mark.parametrize("sample", FIXTURES["credit_card"]["valid"])
    def test_valid_samples_redact(self, s, sample):
        out = s.scrub(f"payment {sample} authorised")
        assert _was_redacted(out, sample, "CREDIT_CARD"), f"valid CC {sample!r} was not redacted: out={out!r}"

    @pytest.mark.parametrize("sample", FIXTURES["credit_card"]["invalid"])
    def test_invalid_samples_pass_through(self, s, sample):
        out = s.scrub(f"payment {sample} pending")
        assert sample in out, f"invalid CC {sample!r} was wrongly redacted: out={out!r}"


class TestIbanFixtures:
    @pytest.fixture(scope="class")
    def s(self):
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
    def s(self):
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
    def s(self):
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
    def s(self):
        return _scrubber_only(national_ids=[self.country])

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
