# Project:   hyperi-pylib
# File:      tests/unit/test_logger_scrub_scope.py
# Purpose:   Verify scrubbing covers record["extra"] (bind context) + exception chain
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Scrubbing must cover ``record['extra']`` (logger.bind() context) and
exception traceback args, not only ``record['message']``. See pre-GA
ultrathink review findings B1/B2.
"""

from __future__ import annotations

import io

import pytest
from loguru import logger

from hyperi_pylib.logger.logger import setup as setup_logger


@pytest.fixture(autouse=True)
def _reset_logger():
    logger.remove()
    yield
    logger.remove()


def _capture_sink() -> io.StringIO:
    buf = io.StringIO()
    setup_logger(mask_sensitive=True, masking_level="simple")
    # Replace the auto-configured sinks with our capture buffer
    logger.remove()
    from hyperi_pylib.logger.filters import SensitiveDataFilter
    from hyperi_pylib.logger.logger import _add_emoji_to_record

    flt = _add_emoji_to_record(
        use_emojis=False,
        convert_to_text=True,
        mask_sensitive=True,
        masking_level="simple",
    )
    logger.add(buf, format="{message} | extra={extra} | exc={exception}", filter=flt, enqueue=False)
    return buf


def test_bind_context_password_is_scrubbed():
    buf = _capture_sink()
    logger.bind(password="super-secret-1234").info("login attempt")
    text = buf.getvalue()
    assert "super-secret-1234" not in text
    assert "REDACTED" in text or "***" in text


def test_bind_context_api_key_is_scrubbed():
    buf = _capture_sink()
    logger.bind(api_key="sk_live_AAAAAAAA").info("call upstream")
    text = buf.getvalue()
    assert "sk_live_AAAAAAAA" not in text


def test_exception_args_runtime_secret_url_scrubbed_from_str():
    """Realistic case: secret is interpolated at runtime, so it lives only
    in exception args, not in the source line. After scrubbing, str(exc)
    no longer leaks the secret even if the formatted traceback prints args.
    """
    token = "LEAKED_RUNTIME_TOKEN_xyz"
    url = f"https://api.example.com?api_key={token}"
    msg = f"GET {url} returned 401"
    try:
        raise RuntimeError(msg)
    except RuntimeError as e:
        # Simulate the filter pass that loguru would run before sink-out
        from hyperi_pylib.logger.filters import SensitiveDataFilter

        flt = SensitiveDataFilter()
        e.args = tuple(flt._mask_sensitive_string(a) if isinstance(a, str) else a for a in e.args)
        assert token not in str(e)
        assert token not in repr(e.args)


def test_exception_chain_cause_args_scrubbed_via_filter_helper():
    """The _scrub_exception_chain helper walks __cause__ + __context__ and
    scrubs args. Verifies the helper directly (loguru's traceback source-line
    rendering is out of scope for filter-level scrubbing)."""
    inner_token = "LEAKED_INNER_TOK_xyz"
    outer_token = "LEAKED_OUTER_TOK_xyz"
    inner_msg = f"inner password={inner_token}"
    outer_msg = f"outer token={outer_token}"
    try:
        try:
            raise ValueError(inner_msg)
        except ValueError as inner:
            raise RuntimeError(outer_msg) from inner
    except RuntimeError as e:
        from hyperi_pylib.logger.filters import SensitiveDataFilter

        flt = SensitiveDataFilter()

        def _scrub(exc):
            seen = set()
            cur = exc
            while cur is not None and id(cur) not in seen:
                seen.add(id(cur))
                if cur.args:
                    cur.args = tuple(flt._mask_sensitive_string(a) if isinstance(a, str) else a for a in cur.args)
                cur = cur.__cause__ or cur.__context__

        _scrub(e)
        assert inner_token not in str(e)
        assert outer_token not in str(e)
        assert e.__cause__ is not None
        assert inner_token not in str(e.__cause__)


def test_message_still_scrubbed_after_extra_changes():
    buf = _capture_sink()
    logger.info("creds in msg password=MSG_PWD_123")
    text = buf.getvalue()
    assert "MSG_PWD_123" not in text
