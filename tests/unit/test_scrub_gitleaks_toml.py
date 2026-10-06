#  Project:   scalo
#  File:      tests/unit/test_scrub_gitleaks_toml.py
#  Purpose:   Tests for the TOML-driven L1 gitleaks scrubber
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for ``scalo.logger.scrub.gitleaks_toml``."""

import random
import re
import string

import pytest

from scalo.logger.scrub import (
    ScrubConfig,
    SecretsConfig,
    SecretsScrubber,
    build_scrubber,
    make_hash_labeler,
)
from scalo.logger.scrub.gitleaks_toml import (
    GitleaksTomlScrubber,
    load_gitleaks_rules,
)

# ---------------------------------------------------------------------------
# Registry load
# ---------------------------------------------------------------------------


class TestLoadGitleaksRules:
    def test_loads_bundled_toml(self):
        rules, meta = load_gitleaks_rules()
        assert isinstance(rules, list)
        # Upstream gitleaks ships ~222 rules; assert a healthy lower bound
        # in case future syncs add or drop a few.
        assert len(rules) >= 200, f"unexpectedly few rules: {len(rules)}"
        assert isinstance(meta, dict)
        # Either the upstream's `title`/`minVersion` makes it through, or an
        # explicit [meta] does
        assert meta.get("title") or meta.get("version")

    def test_every_rule_has_an_id(self):
        """All upstream rules carry an id; regex is usually present but
        path-only rules (e.g. ``pkcs12-file``) legitimately don't."""
        rules, _ = load_gitleaks_rules()
        for r in rules:
            assert isinstance(r, dict)
            assert r.get("id"), f"rule missing id: {r}"

    def test_most_rules_have_regex(self):
        """Path-only / extends-only rules are exceptions; the vast
        majority of upstream rules carry a regex."""
        rules, _ = load_gitleaks_rules()
        with_regex = sum(1 for r in rules if r.get("regex"))
        # At least 95% of rules should have a regex
        assert with_regex / len(rules) >= 0.95

    def test_known_upstream_rules_present(self):
        rules, _ = load_gitleaks_rules()
        ids = {r["id"] for r in rules}
        for required in (
            "aws-access-token",
            "github-pat",
            "jwt",
            "private-key",
            "openai-api-key",
            "stripe-access-token",
        ):
            assert required in ids, f"missing canonical upstream rule {required}"


# ---------------------------------------------------------------------------
# GitleaksTomlScrubber
# ---------------------------------------------------------------------------


class TestGitleaksTomlScrubberBasic:
    def test_default_loads_bundled_rules(self):
        s = GitleaksTomlScrubber()
        # Upstream ships ~222 rules; we should compile the vast majority
        # via the `regex` package. Exact count may shift on sync.
        assert s.rule_count >= 200, f"too few rules compiled: {s.rule_count}"

    def test_satisfies_scrubber_protocol(self):
        from scalo.logger.scrub import Scrubber

        s = GitleaksTomlScrubber()
        assert isinstance(s, Scrubber)

    def test_scrubs_aws_key(self):
        from common.fake_secrets import aws_access_key

        s = GitleaksTomlScrubber()
        ak = aws_access_key()
        out = s.scrub(f"{ak} leaked")
        assert ak not in out
        # Label derived from rule id "aws-access-token"
        assert "[AWS_ACCESS_TOKEN_REDACTED]" in out

    def test_scrubs_github_token(self):
        from common.fake_secrets import github_classic_pat

        s = GitleaksTomlScrubber()
        # Upstream github-pat regex: ghp_ + 36 alphanumeric chars (exact).
        # Note: the broader ``generic-api-key`` rule may fire first when
        # the token is in a ``key=value`` shape -- both outcomes count as
        # a successful redaction. Assert only that the secret is gone.
        token = github_classic_pat()
        out = s.scrub(f"random text {token} more text")
        assert token not in out
        # Should produce some redaction label
        assert "_REDACTED]" in out

    def test_scrubs_jwt(self):
        from common.fake_secrets import jwt as fake_jwt

        s = GitleaksTomlScrubber()
        token = fake_jwt()
        out = s.scrub(f"Authorization: Bearer {token}")
        assert token not in out
        assert "[JWT_REDACTED]" in out

    def test_scrubs_private_key_block(self):
        from common.fake_secrets import private_key_block

        s = GitleaksTomlScrubber()
        # Upstream private-key regex requires {64,} body between BEGIN
        # and END. The factory builds a long-body block to satisfy that.
        key = private_key_block(body_chars=256)
        out = s.scrub(f"key={key}")
        # The body should be gone (redacted)
        assert "X" * 256 not in out
        assert "[PRIVATE_KEY_REDACTED]" in out

    def test_passes_through_clean_text(self):
        s = GitleaksTomlScrubber()
        text = "Normal log message with nothing sensitive"
        assert s.scrub(text) == text

    def test_empty_text_returns_empty(self):
        s = GitleaksTomlScrubber()
        assert s.scrub("") == ""


class TestGitleaksTomlScrubberRuleFilter:
    def test_rule_ids_filter_restricts_set(self):
        from common.fake_secrets import aws_access_key, github_classic_pat

        s = GitleaksTomlScrubber(rule_ids={"aws-access-token"})
        assert s.rule_count == 1
        # AWS key is caught
        ak = aws_access_key()
        out = s.scrub(ak)
        assert ak not in out
        # GitHub token (different rule) passes through -- rule not loaded
        gh_token = github_classic_pat()
        out2 = s.scrub(gh_token)
        assert gh_token in out2


def _real_shaped_github_pat() -> str:
    """A classic PAT shape (``ghp_`` + 36 mixed-case alphanumerics), built at runtime."""
    rng = random.Random(20260924)
    body = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))
    return "gh" + "p_" + body


# hyperi-ci's deprecation warning, verbatim from a dfe-ui CI job log.
_DEPRECATION_LINE = (
    "Renamed config keys in .hyperi-ci.yaml: publish.container -> release.container, "
    "publish.enabled -> release.enabled. The old spelling keeps working; rename when convenient."
)


class TestExcludeRules:
    """``exclude_rules`` narrows a false positive without dropping the rest of the set."""

    def _excluding(self, *rule_ids: str) -> ScrubConfig:
        return ScrubConfig(secrets=SecretsConfig(exclude_rules=frozenset(rule_ids)))

    def test_default_set_eats_the_deprecation_warning(self):
        # The control: without it the survival test below proves nothing.
        out = build_scrubber().scrub(_DEPRECATION_LINE)
        assert "[GENERIC_API_KEY_REDACTED]" in out
        assert "publish.container" not in out

    def test_deprecation_warning_survives_with_generic_api_key_excluded(self):
        scrubber = build_scrubber(self._excluding("generic-api-key"))
        assert scrubber.scrub(_DEPRECATION_LINE) == _DEPRECATION_LINE

    def test_real_github_pat_still_redacted_by_its_own_rule(self):
        pat = _real_shaped_github_pat()
        scrubber = build_scrubber(self._excluding("generic-api-key"))
        out = scrubber.scrub(f"pushing with token {pat} to origin")
        assert pat not in out
        assert out == "pushing with token [GITHUB_PAT_REDACTED] to origin"

    def test_no_exclusion_keeps_every_rule(self):
        assert SecretsScrubber()._inner.rule_count == GitleaksTomlScrubber().rule_count
        assert SecretsConfig().exclude_rules == frozenset()

    def test_exclusion_drops_exactly_the_named_rule(self):
        full = GitleaksTomlScrubber()
        narrowed = GitleaksTomlScrubber(exclude_rule_ids={"generic-api-key"})
        assert narrowed.rule_count == full.rule_count - 1
        assert "generic-api-key" not in {r.id for r in narrowed._compiled}

    def test_exclusion_composes_with_minimal(self):
        minimal = SecretsScrubber(patterns="minimal")
        narrowed = SecretsScrubber(patterns="minimal", exclude_rules=frozenset({"github-pat"}))
        assert narrowed._inner.rule_count == minimal._inner.rule_count - 1

    def test_unknown_rule_id_warns_and_excludes_nothing(self):
        with pytest.warns(RuntimeWarning, match="generic-api-kee"):
            narrowed = GitleaksTomlScrubber(exclude_rule_ids={"generic-api-kee"})
        assert narrowed.rule_count == GitleaksTomlScrubber().rule_count

    def test_detect_secrets_path_warns_and_ignores(self):
        with pytest.warns(RuntimeWarning, match="IGNORED"):
            SecretsScrubber(patterns="detect-secrets", exclude_rules=frozenset({"generic-api-key"}))


class TestGitleaksTomlScrubberLabeler:
    def test_static_labeler_default(self):
        from common.fake_secrets import aws_access_key

        s = GitleaksTomlScrubber()
        out = s.scrub(aws_access_key())
        assert "[AWS_ACCESS_TOKEN_REDACTED]" in out

    def test_hash_labeler_yields_per_value_suffix(self):
        from common.fake_secrets import aws_access_key

        labeler = make_hash_labeler(secret_hash_key=b"k")
        s = GitleaksTomlScrubber(labeler=labeler)
        out = s.scrub(aws_access_key())
        assert re.search(r"\[AWS_ACCESS_TOKEN_[0-9a-f]{6}\]", out)


class TestGitleaksTomlScrubberBadRules:
    def test_uncompilable_regex_skipped_with_warning(self):
        bad = [
            {"id": "good-rule", "regex": r"\bgoodval\b", "label": "GOOD"},
            {"id": "bad-rule", "regex": r"[invalid(regex", "label": "BAD"},
        ]
        with pytest.warns(RuntimeWarning, match="did not compile"):
            s = GitleaksTomlScrubber(rules=bad)
        # Good rule loaded; bad rule skipped
        assert s.rule_count == 1
        assert "bad-rule" in s.skipped_rules

    def test_missing_required_fields_silently_skipped(self):
        rules = [
            {"id": "good", "regex": r"\bX\b", "label": "X"},
            {"regex": r"\bY\b", "label": "Y"},  # missing id
            {"id": "no-regex", "label": "Z"},  # missing regex
        ]
        s = GitleaksTomlScrubber(rules=rules)
        assert s.rule_count == 1


class TestSecretsScrubberRouting:
    """SecretsScrubber must pick the right backend per `patterns`."""

    def test_gitleaks_uses_toml_path(self):
        s = SecretsScrubber(patterns="gitleaks")
        assert isinstance(s._inner, GitleaksTomlScrubber)

    def test_minimal_uses_toml_path_with_subset(self):
        s = SecretsScrubber(patterns="minimal")
        assert isinstance(s._inner, GitleaksTomlScrubber)
        # Only minimal-subset rules loaded (~13 IDs in _MINIMAL_RULES)
        assert s._inner.rule_count <= 15

    def test_detect_secrets_routes_to_legacy(self):
        from scalo.logger.secrets_leak import SecretsLeakFilter

        s = SecretsScrubber(patterns="detect-secrets")
        assert isinstance(s._inner, SecretsLeakFilter)

    def test_unknown_patterns_falls_back_to_gitleaks(self):
        s = SecretsScrubber(patterns="nonsense-value")
        assert isinstance(s._inner, GitleaksTomlScrubber)

    def test_off_uses_legacy_noop(self):
        from common.fake_secrets import aws_access_key

        from scalo.logger.secrets_leak import SecretsLeakFilter

        s = SecretsScrubber(patterns="off")
        # off routes via the detect-secrets level map (level="off")
        assert isinstance(s._inner, SecretsLeakFilter)
        # And acts as a no-op
        text = aws_access_key()
        assert s.scrub(text) == text


class TestBuildScrubberUsesTomlByDefault:
    def test_default_factory_uses_toml(self):
        """build_scrubber() with defaults loads the TOML-driven L1."""
        s = build_scrubber()
        # Find the L1 layer
        l1 = next(
            (layer for layer in s.layers if isinstance(layer, SecretsScrubber)),
            None,
        )
        assert l1 is not None
        assert isinstance(l1._inner, GitleaksTomlScrubber)

    def test_detect_secrets_opt_in_via_config(self):
        from scalo.logger.secrets_leak import SecretsLeakFilter

        s = build_scrubber(ScrubConfig(secrets=SecretsConfig(patterns="detect-secrets")))
        l1 = next(
            (layer for layer in s.layers if isinstance(layer, SecretsScrubber)),
            None,
        )
        assert l1 is not None
        assert isinstance(l1._inner, SecretsLeakFilter)


class TestEndToEndAgainstRealSecrets:
    """Full LayeredScrubber default path still catches the canonical fixtures."""

    @pytest.fixture(scope="class")
    @classmethod
    def s(cls):
        return build_scrubber()

    def test_aws_key_via_toml(self, s):
        from common.fake_secrets import aws_access_key

        ak = aws_access_key()
        out = s.scrub(f"AWS_KEY={ak}")
        assert ak not in out

    def test_github_token_via_toml(self, s):
        from common.fake_secrets import github_classic_pat

        token = github_classic_pat()
        out = s.scrub(f"github_token={token}")
        assert token not in out

    def test_stripe_test_key_via_toml(self, s):
        from common.fake_secrets import stripe_test_key

        key = stripe_test_key()
        out = s.scrub(f"stripe={key}")
        assert key not in out
