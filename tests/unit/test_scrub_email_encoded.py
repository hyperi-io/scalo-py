#  Project:   scalo
#  File:      tests/unit/test_scrub_email_encoded.py
#  Purpose:   Vector table for literal and percent-encoded email redaction
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Email redaction in the forms a URL or HTTP error carries an address.

One vector table drives the validator, the default scrub chain and a logger
record. Every row carries at least one encoded address that must be redacted,
so each row fails against a pattern that only knows the literal ``@``. A
lookalike row also checks that a ``%40`` with no address shape is left alone.
"""

import io
from collections.abc import Iterator

import pytest
from loguru import logger

from scalo.logger.logger import _add_emoji_to_record
from scalo.logger.scrub import build_scrubber
from scalo.logger.scrub.pii import EmailValidator

# (id, input, expected output)
VECTORS: tuple[tuple[str, str, str], ...] = (
    (
        "literal_and_encoded",
        "login sentinel.user@example.com via userKey=sentinel.user%40example.com",
        "login [EMAIL_REDACTED] via userKey=[EMAIL_REDACTED]",
    ),
    ("pct40_standalone", "sentinel.user%40example.com", "[EMAIL_REDACTED]"),
    ("pct2540_double_encoded", "userKey=sentinel.user%2540example.com", "userKey=[EMAIL_REDACTED]"),
    ("mixed_case_address", "Sentinel.User%40Example.COM", "[EMAIL_REDACTED]"),
    (
        "mixed_case_hex_plus",
        "a=user%2btag%40example.com&b=user%2Btag%40example.com&c=user%252btag%2540example.com",
        "a=[EMAIL_REDACTED]&b=[EMAIL_REDACTED]&c=[EMAIL_REDACTED]",
    ),
    ("encoded_plus_literal_at", "user%2Btag@example.com", "[EMAIL_REDACTED]"),
    (
        "url_query",
        "GET /api/v1/users?filter=profile.login%20eq%20%22sentinel.user%40example.com%22&limit=1 failed",
        "GET /api/v1/users?filter=profile.login%20eq%20%22[EMAIL_REDACTED]%22&limit=1 failed",
    ),
    (
        "json",
        '{"error":"not found","userKey":"sentinel.user%40example.com"}',
        '{"error":"not found","userKey":"[EMAIL_REDACTED]"}',
    ),
    (
        "nested_url",
        "redirect=https%3A%2F%2Fapp.test%2Fcb%3Fuser%3Dsentinel.user%40example.com",
        "redirect=https%3A%2F%2Fapp.test%2Fcb%3Fuser%3D[EMAIL_REDACTED]",
    ),
    (
        "nested_url_double_encoded",
        "next=%253Fuser%253Dsentinel.user%2540example.com",
        "next=%253Fuser%253D[EMAIL_REDACTED]",
    ),
    ("leading_escape_kept", "%2Bsentinel.user%40example.com", "%2B[EMAIL_REDACTED]"),
    (
        "lookalike_no_dot_in_domain",
        "discount=50%40off for sentinel.user%40example.com",
        "discount=50%40off for [EMAIL_REDACTED]",
    ),
    (
        "lookalike_no_local_part",
        "%40example.com and %2540example.com from sentinel.user%40example.com",
        "%40example.com and %2540example.com from [EMAIL_REDACTED]",
    ),
    (
        "lookalike_path_segment",
        "GET /icons%40v2/x.png?u=sentinel.user%40example.com",
        "GET /icons%40v2/x.png?u=[EMAIL_REDACTED]",
    ),
    (
        "lookalike_digest",
        "image%40sha256%3Aabc123 pulled by sentinel.user%40example.com",
        "image%40sha256%3Aabc123 pulled by [EMAIL_REDACTED]",
    ),
    (
        "lookalike_number",
        "progress 100%40.5 for sentinel.user%40example.com",
        "progress 100%40.5 for [EMAIL_REDACTED]",
    ),
    (
        "opaque_id_not_detected",
        "user 00u1sentinel2abc3 (sentinel.user%40example.com) not found",
        "user 00u1sentinel2abc3 ([EMAIL_REDACTED]) not found",
    ),
)

_PARAMS = [pytest.param(text, expected, id=vector_id) for vector_id, text, expected in VECTORS]


@pytest.mark.parametrize(("text", "expected"), _PARAMS)
def test_validator_redacts_only_the_address(text: str, expected: str) -> None:
    assert EmailValidator().scrub(text) == expected


@pytest.mark.parametrize(("text", "expected"), _PARAMS)
def test_default_chain_redacts_only_the_address(text: str, expected: str) -> None:
    assert build_scrubber().scrub(text) == expected


@pytest.fixture
def log_capture() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    logger.remove()
    record_filter = _add_emoji_to_record(use_emojis=False, convert_to_text=True, scrubber=build_scrubber())
    logger.add(buf, format="{message} | {extra}", filter=record_filter, enqueue=False)
    yield buf
    logger.remove()


def test_logger_redacts_encoded_email_in_message_and_field(log_capture: io.StringIO) -> None:
    logger.bind(error="GET /users?userKey=sentinel.user%40example.com returned 404").error(
        "IdP lookup failed for sentinel.user%2540example.com"
    )
    out = log_capture.getvalue()
    assert "sentinel.user" not in out
    assert out.count("[EMAIL_REDACTED]") == 2
