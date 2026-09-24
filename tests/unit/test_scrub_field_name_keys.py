#  Project:   scalo
#  File:      tests/unit/test_scrub_field_name_keys.py
#  Purpose:   L2 field-name matching on env-style, TOML and INI keys
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""L2 masks a sensitive field wherever it ends a key.

Every value is built at runtime, so no secret-shaped literal sits in source.
"""

import string

import pytest

from scalo.logger.filters import MASK_VALUE
from scalo.logger.scrub import FieldNameScrubber, FieldsConfig, ScrubConfig, SecretsConfig, build_scrubber

_ALNUM = string.ascii_letters + string.digits
_HEX = "0123456789abcdef"

# Mixed-case with 40 distinct characters: enough entropy for gitleaks generic-api-key to fire.
TOKEN = "".join(_ALNUM[(i * 7 + 3) % len(_ALNUM)] for i in range(40))
KEY_ID = "".join(_HEX[(i * 5 + 1) % len(_HEX)] for i in range(32))

_EXCLUDE_GENERIC = SecretsConfig(exclude_rules=frozenset({"generic-api-key"}))

DEPRECATION_LINE = "Renamed config keys in .hyperi-ci.yaml: publish.container -> release.container"

# (line, the value that must not survive, exact L2 output)
SIX_LINES = [
    pytest.param(
        f"CARGO_REGISTRY_TOKEN={TOKEN}", TOKEN, f"CARGO_REGISTRY_TOKEN={MASK_VALUE}", id="cargo-registry-token-env"
    ),
    pytest.param(
        f"R2_SECRET_ACCESS_KEY={TOKEN}", TOKEN, f"R2_SECRET_ACCESS_KEY={MASK_VALUE}", id="r2-secret-access-key-env"
    ),
    pytest.param(f"R2_ACCESS_KEY_ID={KEY_ID}", KEY_ID, f"R2_ACCESS_KEY_ID={MASK_VALUE}", id="r2-access-key-id-env"),
    pytest.param(f"JFROG_TOKEN={TOKEN}", TOKEN, f"JFROG_TOKEN={MASK_VALUE}", id="jfrog-token-env"),
    pytest.param(f'token = "{TOKEN}"', TOKEN, f"token = {MASK_VALUE}", id="cargo-credentials-toml"),
    pytest.param(
        f"aws_secret_access_key = {TOKEN}", TOKEN, f"aws_secret_access_key = {MASK_VALUE}", id="aws-credentials-ini"
    ),
]

UNTOUCHED = [
    pytest.param("token_count=5", id="token-count"),
    pytest.param("max_tokens=4096", id="max-tokens"),
    pytest.param("mapping=raw_events->events_load", id="mapping"),
    pytest.param(DEPRECATION_LINE, id="hyperi-ci-deprecation"),
    pytest.param('{"tokenizer":"whitespace"}', id="tokenizer-json"),
    pytest.param('{"token_type":"Bearer","expires_in":3600}', id="token-type-json"),
    pytest.param("oauth=enabled", id="oauth"),
    pytest.param("if token == expected_token:", id="comparison"),
    pytest.param("the password policy requires 12 characters", id="prose"),
]


@pytest.fixture(scope="module", params=["default", "exclude-generic-api-key"])
def chain(request):
    """The composed scrubber, with and without gitleaks generic-api-key."""
    if request.param == "default":
        return build_scrubber()
    return build_scrubber(ScrubConfig(secrets=_EXCLUDE_GENERIC))


class TestSixLinesMasked:
    @pytest.mark.parametrize(("line", "value", "expected"), SIX_LINES)
    def test_masked_through_the_chain(self, chain, line, value, expected):
        assert value not in chain.scrub(line)

    @pytest.mark.parametrize(("line", "value", "expected"), SIX_LINES)
    def test_l2_output_keeps_the_key(self, line, value, expected):
        assert FieldNameScrubber().scrub(line) == expected

    @pytest.mark.parametrize(("line", "value", "expected"), SIX_LINES)
    def test_leak_without_l2_when_generic_api_key_is_excluded(self, line, value, expected):
        # The control: proves L2 is what masks these once the generic rule is gone.
        no_fields = build_scrubber(ScrubConfig(secrets=_EXCLUDE_GENERIC, fields=FieldsConfig(enabled=False)))
        assert value in no_fields.scrub(line)


class TestKeyShapes:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            pytest.param(f'token = "{TOKEN[:12]} {TOKEN[12:]}"', f"token = {MASK_VALUE}", id="double-quoted-spaced"),
            pytest.param(f"token = '{TOKEN[:12]} {TOKEN[12:]}'", f"token = {MASK_VALUE}", id="single-quoted-spaced"),
            pytest.param(f'token="{TOKEN}"&page=2', f"token={MASK_VALUE}&page=2", id="quoted-form-value"),
            pytest.param(f'"token" = "{TOKEN}"', f'"token" = {MASK_VALUE}', id="toml-quoted-key"),
            pytest.param(f"--api-token={TOKEN}", f"--api-token={MASK_VALUE}", id="cli-flag"),
            pytest.param(f"token=\n{TOKEN[:8]}", f"token={MASK_VALUE}\n{TOKEN[:8]}", id="stops-at-newline"),
            pytest.param(f"token = \n{TOKEN[:8]}", f"token = {MASK_VALUE}\n{TOKEN[:8]}", id="spaced-stops-at-newline"),
            pytest.param("handler => 'token' => 'abc'", "handler => 'token' => 'abc'", id="fat-arrow-not-assignment"),
        ],
    )
    def test_equals_forms(self, line, expected):
        assert FieldNameScrubber().scrub(line) == expected

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            pytest.param(f"JFROG_TOKEN: {TOKEN}", f"JFROG_TOKEN: {MASK_VALUE}", id="yaml-env-key"),
            pytest.param(f"x-auth-token: {TOKEN}", f"x-auth-token: {MASK_VALUE}", id="http-header"),
            pytest.param(
                f'{{"CARGO_REGISTRY_TOKEN": "{TOKEN}"}}',
                f'{{"CARGO_REGISTRY_TOKEN": "{MASK_VALUE}"}}',
                id="json-env-key",
            ),
            pytest.param(f"{{'password': '{TOKEN}'}}", f"{{'password': {MASK_VALUE}}}", id="python-repr"),
        ],
    )
    def test_colon_forms(self, line, expected):
        assert FieldNameScrubber().scrub(line) == expected

    def test_field_ending_the_key_masks_whatever_the_value(self):
        # The rule is the key's last segments, not the value's shape: a count under max_token still goes.
        assert FieldNameScrubber().scrub("max_token=5") == f"max_token={MASK_VALUE}"


class TestOrdinaryTextUntouched:
    @pytest.mark.parametrize("line", UNTOUCHED)
    def test_l2_leaves_it(self, line):
        assert FieldNameScrubber().scrub(line) == line

    @pytest.mark.parametrize("line", UNTOUCHED)
    def test_chain_without_generic_api_key_leaves_it(self, line):
        assert build_scrubber(ScrubConfig(secrets=_EXCLUDE_GENERIC)).scrub(line) == line
