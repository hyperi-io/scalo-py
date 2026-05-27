#  Project:   hyperi-pylib
#  File:      tests/unit/test_logger_json_extra_leak.py
#  Purpose:   E2E: real setup() + JSON output must not leak bind() secrets
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""JSON logger + bind(password=...) must not leak under record.extra."""

from __future__ import annotations

import io
import json

import pytest
from common.fake_secrets import opaque_secret
from loguru import logger

from hyperi_pylib.logger.logger import _add_emoji_to_record
from hyperi_pylib.logger.scrub_resolver import resolve_scrubber


@pytest.fixture
def json_capture():
    """JSON sink straight to a buffer with the production scrub filter.

    Avoids the sys.stderr swap (fragile under pytest capture in the full
    suite); adds a serialize=True sink so we assert on real JSON output.
    """
    logger.remove()
    buf = io.StringIO()
    scrubber = resolve_scrubber(mask_sensitive=True, config_dict={})
    flt = _add_emoji_to_record(use_emojis=False, mask_sensitive=True, scrubber=scrubber)
    logger.add(buf, serialize=True, filter=flt, enqueue=False, level="DEBUG")
    try:
        yield buf
    finally:
        logger.remove()


def _parse_last_json(buf: io.StringIO) -> dict:
    """Pull the most recent JSON record from the captured stream."""
    text = buf.getvalue()
    # Last non-empty line that parses as JSON
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"no JSON record found in:\n{text}")


def test_bind_password_does_not_appear_in_record_extra(json_capture):
    secret = opaque_secret("password")
    logger.bind(password=secret).info("login")
    rec = _parse_last_json(json_capture)
    extra = rec["record"]["extra"]
    assert "password" in extra, "key should still be present (redacted)"
    assert secret not in json.dumps(rec), f"secret leaked: {rec}"
    assert extra["password"] != secret


def test_bind_api_key_does_not_appear_in_record_extra(json_capture):
    secret = opaque_secret("apikey")
    logger.bind(api_key=secret).info("call")
    rec = _parse_last_json(json_capture)
    assert secret not in json.dumps(rec)


def test_bind_token_does_not_appear_in_record_extra(json_capture):
    secret = opaque_secret("token")
    logger.bind(token=secret).info("auth")
    rec = _parse_last_json(json_capture)
    assert secret not in json.dumps(rec)


def test_bind_authorization_does_not_appear_in_record_extra(json_capture):
    secret = opaque_secret("auth")
    logger.bind(authorization=f"Bearer {secret}").info("request")
    rec = _parse_last_json(json_capture)
    assert secret not in json.dumps(rec)


def test_non_sensitive_extras_pass_through(json_capture):
    """User context fields that aren't credentials must still surface."""
    logger.bind(user_id=42, request_id="r-001").info("request")
    rec = _parse_last_json(json_capture)
    extra = rec["record"]["extra"]
    assert extra["user_id"] == 42
    assert extra["request_id"] == "r-001"


def test_value_scrubber_still_catches_credentials_in_legitimate_fields(json_capture):
    """logger.bind(url=...) with a credentialed URL: key is fine, but the
    URL value contains a credential -- value scrubber must still catch it."""
    secret = opaque_secret("urltoken")
    url = f"https://api.example.com?api_key={secret}"
    logger.bind(url=url).info("call upstream")
    rec = _parse_last_json(json_capture)
    text = json.dumps(rec)
    assert secret not in text
