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
import os
import re
import sys

import pytest
from loguru import logger

from hyperi_pylib.logger.logger import setup


@pytest.fixture
def json_capture(monkeypatch):
    """Replicate prod setup() with LOG_FORMAT=json but capture stderr."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("HYPERI_LOG_ENQUEUE", "0")

    logger.remove()
    buf = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = buf
    try:
        setup(mask_sensitive=True)
        yield buf
    finally:
        sys.stderr = real_stderr
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
    secret = "LEAK_PASSWORD_xyz123"
    logger.bind(password=secret).info("login")
    rec = _parse_last_json(json_capture)
    extra = rec["record"]["extra"]
    assert "password" in extra, "key should still be present (redacted)"
    assert secret not in json.dumps(rec), f"secret leaked: {rec}"
    assert extra["password"] != secret


def test_bind_api_key_does_not_appear_in_record_extra(json_capture):
    secret = "LEAK_API_KEY_xyz"
    logger.bind(api_key=secret).info("call")
    rec = _parse_last_json(json_capture)
    assert secret not in json.dumps(rec)


def test_bind_token_does_not_appear_in_record_extra(json_capture):
    secret = "LEAK_TOKEN_xyz"
    logger.bind(token=secret).info("auth")
    rec = _parse_last_json(json_capture)
    assert secret not in json.dumps(rec)


def test_bind_authorization_does_not_appear_in_record_extra(json_capture):
    secret = "Bearer LEAK_AUTH_xyz"
    logger.bind(authorization=secret).info("request")
    rec = _parse_last_json(json_capture)
    assert "LEAK_AUTH_xyz" not in json.dumps(rec)


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
    url = "https://api.example.com?api_key=LEAK_URL_xyz"
    logger.bind(url=url).info("call upstream")
    rec = _parse_last_json(json_capture)
    text = json.dumps(rec)
    assert "LEAK_URL_xyz" not in text
