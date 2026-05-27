#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_factory.py
#  Purpose:   Tests for build_scrubber() and the L1+L2 adapter scrubbers
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the scrubber factory (Step 4 of the implementation plan).

Verifies that :func:`build_scrubber` composes a working LayeredScrubber
from a ScrubConfig, honours the per-layer toggles, and that the L1
(SecretsScrubber) and L2 (FieldNameScrubber) adapters delegate to their
underlying implementations correctly.
"""

from __future__ import annotations

import pytest

from hyperi_pylib.logger.scrub import (
    FieldNameScrubber,
    FieldsConfig,
    LayeredScrubber,
    PiiConfig,
    PiiValidatorsConfig,
    Scrubber,
    ScrubConfig,
    SecretsConfig,
    SecretsScrubber,
    build_scrubber,
)

# ---------------------------------------------------------------------------
# build_scrubber -- composition
# ---------------------------------------------------------------------------


class TestBuildScrubberDefaults:
    def test_returns_layered_scrubber(self):
        s = build_scrubber()
        assert isinstance(s, LayeredScrubber)
        assert isinstance(s, Scrubber)

    def test_includes_l1_l2_l3_with_default_config(self):
        s = build_scrubber()
        # Default: 1 L1 secrets + 1 L2 fields + 8 L3 validators = 10
        # (L4 NLP not wired yet -- see factory.py comment)
        assert len(s.layers) == 10

    def test_none_config_uses_defaults(self):
        s = build_scrubber(None)
        assert isinstance(s, LayeredScrubber)


class TestBuildScrubberTogglesAtLayerLevel:
    def test_secrets_off_skips_l1(self):
        s = build_scrubber(ScrubConfig(secrets=SecretsConfig(enabled=False)))
        assert not any(isinstance(layer, SecretsScrubber) for layer in s.layers)

    def test_secrets_patterns_off_also_skips_l1(self):
        s = build_scrubber(ScrubConfig(secrets=SecretsConfig(patterns="off")))
        assert not any(isinstance(layer, SecretsScrubber) for layer in s.layers)

    def test_fields_off_skips_l2(self):
        s = build_scrubber(ScrubConfig(fields=FieldsConfig(enabled=False)))
        assert not any(isinstance(layer, FieldNameScrubber) for layer in s.layers)

    def test_pii_off_skips_l3_entirely(self):
        s = build_scrubber(ScrubConfig(pii=PiiConfig(enabled=False)))
        # Only L1 + L2 should remain
        assert len(s.layers) == 2

    def test_all_layers_off_yields_empty_chain(self):
        s = build_scrubber(
            ScrubConfig(
                secrets=SecretsConfig(enabled=False),
                fields=FieldsConfig(enabled=False),
                pii=PiiConfig(enabled=False),
            )
        )
        assert s.layers == ()


class TestBuildScrubberPerValidatorToggles:
    def test_disable_specific_validator(self):
        s = build_scrubber(
            ScrubConfig(
                secrets=SecretsConfig(enabled=False),
                fields=FieldsConfig(enabled=False),
                pii=PiiConfig(validators=PiiValidatorsConfig(email=False)),
            )
        )
        # 7 validators (8 minus email)
        assert len(s.layers) == 7

    def test_disable_all_national_ids(self):
        from hyperi_pylib.logger.scrub import NationalIdsConfig

        s = build_scrubber(
            ScrubConfig(
                secrets=SecretsConfig(enabled=False),
                fields=FieldsConfig(enabled=False),
                pii=PiiConfig(
                    validators=PiiValidatorsConfig(
                        national_ids=NationalIdsConfig(enabled=[]),
                    )
                ),
            )
        )
        # 4 strong-structural remain (CC, IBAN, email, phone)
        assert len(s.layers) == 4

    def test_only_email_enabled(self):
        from hyperi_pylib.logger.scrub import NationalIdsConfig

        s = build_scrubber(
            ScrubConfig(
                secrets=SecretsConfig(enabled=False),
                fields=FieldsConfig(enabled=False),
                pii=PiiConfig(
                    validators=PiiValidatorsConfig(
                        credit_card=False,
                        iban=False,
                        phone=False,
                        national_ids=NationalIdsConfig(enabled=[]),
                    )
                ),
            )
        )
        # Only email enabled
        assert len(s.layers) == 1

    def test_au_default_active(self):
        """AU national IDs ship pre-active (enabled=true in TOML)."""
        s = build_scrubber(
            ScrubConfig(
                secrets=SecretsConfig(enabled=False),
                fields=FieldsConfig(enabled=False),
                pii=PiiConfig(
                    validators=PiiValidatorsConfig(
                        credit_card=False,
                        iban=False,
                        email=False,
                        phone=False,
                    )
                ),
            )
        )
        # AU has 4 enabled entries: abn, acn, tfn, medicare
        assert len(s.layers) == 4


class TestBuildScrubberEndToEnd:
    """Real text through a default scrubber -- every layer fires."""

    @pytest.fixture(scope="class")
    def s(self):
        return build_scrubber()

    def test_l1_aws_key_redacted(self, s):
        from common.fake_secrets import aws_access_key

        ak = aws_access_key()
        out = s.scrub(f"AWS_ACCESS_KEY={ak}")
        assert ak not in out

    def test_l2_password_field_redacted(self, s):
        out = s.scrub("user logged in with password=hunter2")
        assert "hunter2" not in out

    def test_l3_email_redacted(self, s):
        from common.fake_pii import email

        e = email()
        out = s.scrub(f"contact {e} please")
        assert e not in out

    def test_l3_credit_card_redacted(self, s):
        from common.fake_pii import visa_card

        # Use hyphen-separator form (drop-in for original "4111-1111-1111-1111")
        cc = visa_card().replace(" ", "-")
        out = s.scrub(f"paid with {cc}")
        assert cc not in out

    def test_l3_context_required_abn_with_keyword_redacted(self, s):
        from common.fake_pii import au_abn_bare, au_abn_with_context

        text = au_abn_with_context()
        out = s.scrub(text)
        assert au_abn_bare() not in out

    def test_l3_context_required_abn_without_keyword_passes_through(self, s):
        from common.fake_pii import au_abn_bare

        # Bare digit run without context -- should NOT redact
        bare = au_abn_bare().replace(" ", "")
        text = f"Request {bare} logged"
        out = s.scrub(text)
        assert bare in out

    def test_observe_only_mode(self):
        s = build_scrubber(ScrubConfig(observe_only=True))
        text = "password=hunter2"
        assert s.scrub(text) == text  # unchanged in observe-only

    def test_master_disable(self):
        from common.fake_pii import email

        s = build_scrubber(ScrubConfig(enabled=False))
        text = f"password=hunter2 {email()}"
        assert s.scrub(text) == text


# ---------------------------------------------------------------------------
# L1 / L2 adapter sanity
# ---------------------------------------------------------------------------


class TestSecretsScrubberAdapter:
    def test_satisfies_protocol(self):
        assert isinstance(SecretsScrubber(), Scrubber)

    def test_scrubs_aws_key(self):
        from common.fake_secrets import aws_access_key

        s = SecretsScrubber()
        ak = aws_access_key()
        out = s.scrub(f"{ak} leaked")
        assert ak not in out

    def test_off_mode_passes_through(self):
        from common.fake_secrets import aws_access_key

        s = SecretsScrubber(patterns="off")
        text = f"{aws_access_key()} leaked"
        assert s.scrub(text) == text

    def test_minimal_subset(self):
        from common.fake_secrets import aws_access_key

        s = SecretsScrubber(patterns="minimal")
        ak = aws_access_key()
        # minimal still catches AWS keys
        out = s.scrub(ak)
        assert ak not in out

    def test_repr_shows_patterns(self):
        s = SecretsScrubber(patterns="minimal")
        assert "minimal" in repr(s)


class TestFieldNameScrubberAdapter:
    def test_satisfies_protocol(self):
        assert isinstance(FieldNameScrubber(), Scrubber)

    def test_scrubs_password_field(self):
        s = FieldNameScrubber()
        out = s.scrub("password=hunter2 logged in")
        assert "hunter2" not in out

    def test_scrubs_json_token_field(self):
        s = FieldNameScrubber()
        out = s.scrub('config: {"token":"abc123"}')
        assert "abc123" not in out

    def test_extra_fields(self):
        s = FieldNameScrubber(extra_fields={"employee_id"})
        out = s.scrub("employee_id=12345")
        assert "12345" not in out

    def test_passes_through_unrecognised(self):
        s = FieldNameScrubber()
        text = "Just a normal log line"
        assert s.scrub(text) == text
