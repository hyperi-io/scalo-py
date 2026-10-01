#  Project:   scalo
#  File:      tests/unit/test_logger_third_party_cap.py
#  Purpose:   setup() keeps payload-logging third-party loggers at WARNING
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""setup() caps boto3/botocore/s3transfer/urllib3/httpx/httpcore at WARNING whatever the app level.

botocore writes request params and raw response bodies at DEBUG, so a Secrets
Manager SecretString reaches any stdlib handler an app has opened to DEBUG.
httpx writes every request URL at INFO, presigned query strings included.
"""

import logging
import sys

import pytest
from common.fake_secrets import opaque_secret
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.logger.logger import setup

CAPPED = ("boto3", "botocore", "s3transfer", "urllib3", "httpx", "httpcore")


@pytest.fixture
def debug_app(monkeypatch, caplog):
    """An app with the stdlib root and scalo both at DEBUG; levels restored after."""
    saved = {name: logging.getLogger(name).level for name in CAPPED}
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    caplog.set_level(logging.DEBUG)
    try:
        yield caplog
    finally:
        logger.remove()
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


@pytest.fixture
def routed(monkeypatch):
    """Clear the format selectors and put the stdlib loggers setup() rewires back afterwards."""
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    with preserved_stdlib_logging():
        yield


def _scalo_stderr(monkeypatch) -> StreamDouble:
    """Point stderr at a buffer from the test body, where pytest's own capture no longer swaps it.

    setup() routes stdlib records to the scalo console sink, past caplog's handler.
    """
    stream = StreamDouble(False)
    monkeypatch.setattr(sys, "stderr", stream)
    return stream


@pytest.mark.parametrize("name", CAPPED)
def test_debug_app_level_leaves_third_party_at_warning(debug_app, name):
    setup(level="DEBUG", otel_tracing=False)
    assert logging.getLogger(name).getEffectiveLevel() == logging.WARNING
    assert not logging.getLogger(f"{name}.child").isEnabledFor(logging.DEBUG)
    assert not logging.getLogger(f"{name}.child").isEnabledFor(logging.INFO)
    assert logging.getLogger(f"{name}.child").isEnabledFor(logging.WARNING)


def test_explicit_level_below_warning_is_raised(debug_app):
    logging.getLogger("botocore").setLevel(logging.DEBUG)
    setup(level="DEBUG", otel_tracing=False)
    assert logging.getLogger("botocore").level == logging.WARNING


def test_stricter_app_level_is_left_alone(debug_app):
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    setup(level="DEBUG", otel_tracing=False)
    assert logging.getLogger("urllib3").level == logging.ERROR


def test_botocore_debug_record_does_not_reach_root_handler(debug_app, routed, monkeypatch):
    marker = "response-body-marker-7f3a9c"
    stream = _scalo_stderr(monkeypatch)
    setup(level="DEBUG", otel_tracing=False)
    logging.getLogger("botocore.parsers").debug("Response body:\n%r", marker)
    logging.getLogger("botocore.parsers").warning("still routed")
    assert marker not in debug_app.text
    assert marker not in stream.getvalue()
    assert "still routed" in stream.getvalue()


def test_httpx_request_line_with_a_signed_url_is_not_logged(debug_app, routed, monkeypatch):
    signature = opaque_secret("presigned")
    stream = _scalo_stderr(monkeypatch)
    setup(otel_tracing=False)
    logging.getLogger("httpx").info(
        'HTTP Request: GET https://bucket.example.com/obj?X-Amz-Signature=%s "HTTP/1.1 200 OK"', signature
    )
    logging.getLogger("httpx").warning("still routed")
    assert signature not in stream.getvalue()
    assert "still routed" in stream.getvalue()


def test_aws_secret_value_not_logged_at_debug(debug_app, routed, monkeypatch):
    """Real boto3 round trip against moto: the value never reaches a DEBUG handler."""
    moto = pytest.importorskip("moto")
    from scalo.secrets.providers.aws import BOTO3_AVAILABLE, AWSProvider
    from scalo.secrets.types import AWSConfig

    if not BOTO3_AVAILABLE:
        pytest.skip("boto3 not installed")
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(var, "testing")
    region = "ap-southeast-2"
    monkeypatch.setenv("AWS_DEFAULT_REGION", region)
    secret = opaque_secret("secretstring")
    stream = _scalo_stderr(monkeypatch)

    setup(level="DEBUG", otel_tracing=False)
    with moto.mock_aws():
        provider = AWSProvider(AWSConfig(region=region))
        provider.create_sync("cap-probe", secret.encode())
        assert provider.get_sync("cap-probe").data == secret.encode()

    assert secret not in debug_app.text
    assert secret not in stream.getvalue()
