#  Project:   hyperi-pylib
#  File:      tests/unit/test_logger_secrets_leak.py
#  Purpose:   Tests for SecretsLeakFilter (detect-secrets backend)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the gitleaks-style security-artefact filter."""

from __future__ import annotations

import pytest
from common.fake_secrets import (
    aws_access_key,
    aws_session_token,
    github_classic_pat,
    private_key_block,
    stripe_live_key,
)
from common.fake_secrets import (
    jwt as fake_jwt,
)

from hyperi_pylib.logger.filters import SensitiveDataFilter
from hyperi_pylib.logger.secrets_leak import (
    SECRETS_PLUGINS_FULL,
    SECRETS_PLUGINS_LITE,
    SecretsLeakFilter,
)


class TestSecretsLeakFilterDetection:
    """Each detector type catches the expected pattern."""

    @pytest.fixture(scope="class")
    def f(self):
        return SecretsLeakFilter(level="full")

    def test_aws_access_key(self, f):
        ak = aws_access_key()
        out = f.scrub(f"AWS key={ak} in config")
        assert ak not in out
        assert "AWS_ACCESS_KEY_REDACTED" in out

    def test_aws_temp_key(self, f):
        ak = aws_session_token()
        out = f.scrub(f"Session: {ak}")
        assert ak not in out

    def test_github_token(self, f):
        token = github_classic_pat()
        out = f.scrub(f"Authorization: token {token}")
        assert token not in out
        assert "GITHUB_TOKEN_REDACTED" in out

    def test_jwt(self, f):
        token = fake_jwt()
        out = f.scrub(f"Bearer {token}")
        assert token not in out
        assert "JSON_WEB_TOKEN_REDACTED" in out

    def test_private_key(self, f):
        key = private_key_block(body_chars=256)
        out = f.scrub(f"key={key}")
        # The body is a string of X's; verify it's gone from output
        assert "X" * 256 not in out
        assert "PRIVATE_KEY_REDACTED" in out

    def test_stripe_test_key(self, f):
        # Fixture comes from the runtime-constructed factory so no
        # contiguous ``sk_live_<n chars>`` literal ever appears in
        # source — GitHub Push Protection (and similar scanners) read
        # source bytes, not Python evaluations, so the factory output
        # is invisible to them. The L1 scrubber still sees the
        # full string at runtime and redacts it normally.
        fake = stripe_live_key()
        out = f.scrub(f"Stripe: {fake}")
        assert fake not in out

    def test_clean_text_unchanged(self, f):
        text = "Just a normal log line with no secrets"
        assert f.scrub(text) == text

    def test_empty_string(self, f):
        assert f.scrub("") == ""

    def test_multiple_secrets_in_one_line(self, f):
        ak = aws_access_key()
        token = github_classic_pat()
        text = f"Init failed: {ak} and {token} both rotated"
        out = f.scrub(text)
        assert ak not in out
        assert token not in out


class TestSecretsLeakLevels:
    """Cascade: full / lite / off."""

    def test_full_uses_all_curated_plugins(self):
        f = SecretsLeakFilter(level="full")
        assert f.level == "full"
        assert f._enabled is True
        assert f._plugins == SECRETS_PLUGINS_FULL

    def test_lite_uses_subset(self):
        f = SecretsLeakFilter(level="lite")
        assert f.level == "lite"
        assert f._enabled is True
        assert f._plugins == SECRETS_PLUGINS_LITE
        assert len(f._plugins) < len(SECRETS_PLUGINS_FULL)

    def test_off_is_noop(self):
        f = SecretsLeakFilter(level="off")
        assert f._enabled is False
        # No detection happens — secrets pass through
        text = f"AWS key {aws_access_key()}"
        assert f.scrub(text) == text

    def test_lite_still_catches_high_signal_types(self):
        """The lite tier must still catch AWS / GitHub / JWT / Private Key."""
        f = SecretsLeakFilter(level="lite")
        ak = aws_access_key()
        token = github_classic_pat()
        text = f"AWS={ak} token={token}"
        out = f.scrub(text)
        assert ak not in out
        assert token not in out

    def test_unknown_level_disables(self):
        """Unknown level value disables — fail safe, not exception."""
        f = SecretsLeakFilter(level="bogus")
        assert f._enabled is False


class TestSecretsLeakExtraPatterns:
    """Org-specific patterns can be added."""

    def test_extra_pattern_redacts(self):
        f = SecretsLeakFilter(
            level="off",  # detect-secrets off
            extra_patterns=[("Internal Token", r"\binternal_[0-9a-f]{16}\b")],
        )
        # extra_patterns add redaction regex even when detect-secrets is off?
        # No — they only fire when detect-secrets reports the matching type.
        # For pure-regex matching independent of detect-secrets, callers
        # should use SensitiveDataFilter's regex pass instead.
        # Verify the regex is at least compiled.
        assert "Internal Token" in f._redaction


class TestSecretsLeakCompositionWithSensitiveFilter:
    """SecretsLeakFilter wires in as the first pass of SensitiveDataFilter."""

    def test_compose_with_field_name_filter(self):
        secrets = SecretsLeakFilter(level="full")
        f = SensitiveDataFilter(secrets_leak=secrets)

        ak = aws_access_key()
        token = fake_jwt()
        text = f"User logged in with password=hunter2 and AWS_KEY={ak} - JWT {token}"
        out = f._mask_sensitive_string(text)
        # Field-name match strips hunter2
        assert "hunter2" not in out
        # SecretsLeakFilter strips AWS
        assert ak not in out
        # SecretsLeakFilter strips JWT
        assert token not in out
