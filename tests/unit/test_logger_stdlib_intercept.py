#  Project:   scalo
#  File:      tests/unit/test_logger_stdlib_intercept.py
#  Purpose:   Stdlib logging records reach the scalo sinks formatted and scrubbed, exactly once
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""After setup(), stdlib logging goes through the scalo sinks: same format, fields and scrubbing."""

import io
import json
import logging
import sys

import pytest
from common.fake_secrets import opaque_secret
from common.log_capture import LOGGER_ENV_VARS, SELF_HANDLING_LOGGERS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.logger.logger import _InterceptHandler, setup


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    with preserved_stdlib_logging():
        yield
        logger.remove()


def _setup(monkeypatch, *, tty: bool = False, **kwargs) -> StreamDouble:
    stream = StreamDouble(tty)
    monkeypatch.setattr(sys, "stderr", stream)
    setup(otel_tracing=False, **kwargs)
    return stream


def _json_lines(stream: StreamDouble) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_a_stdlib_record_is_scalo_formatted_and_scrubbed_in_json(monkeypatch):
    stream = _setup(monkeypatch)
    secret = opaque_secret("stdlibtoken")

    logging.getLogger("x").warning("token=%s", secret)

    (record,) = _json_lines(stream)
    assert secret not in stream.getvalue()
    assert record["level"] == "WARNING"
    assert "REDACTED" in record["message"]
    assert record["target"] == __name__
    assert record["function"] == "test_a_stdlib_record_is_scalo_formatted_and_scrubbed_in_json"


def test_a_stdlib_record_is_scalo_formatted_and_scrubbed_in_text(monkeypatch):
    stream = _setup(monkeypatch, log_format="text")
    secret = opaque_secret("stdlibtext")

    logging.getLogger("x").warning("token=%s", secret)

    line = stream.getvalue().rstrip("\n")
    assert secret not in line
    assert "\n" not in line
    assert f"| WARNING  | {__name__}:" in line
    assert "REDACTED" in line


def test_stdlib_extra_becomes_fields_and_is_scrubbed(monkeypatch):
    stream = _setup(monkeypatch)
    secret = opaque_secret("extrapassword")

    logging.getLogger("x").info("job done", extra={"job": "j1", "password": secret})

    (record,) = _json_lines(stream)
    assert record["fields"]["job"] == "j1"
    assert record["fields"]["password"] == "***REDACTED***"
    assert secret not in stream.getvalue()


def test_stdlib_exception_carries_the_traceback(monkeypatch):
    stream = _setup(monkeypatch)

    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("x").exception("failed")

    (record,) = _json_lines(stream)
    assert record["level"] == "ERROR"
    assert "ValueError: boom" in record["exception"]


def test_an_existing_root_handler_is_replaced_so_nothing_is_written_twice(monkeypatch):
    elsewhere = io.StringIO()
    logging.getLogger().addHandler(logging.StreamHandler(elsewhere))
    stream = _setup(monkeypatch)

    logging.getLogger("x").warning("once")

    assert elsewhere.getvalue() == ""
    assert [record["message"] for record in _json_lines(stream)] == ["once"]
    assert [type(handler) for handler in logging.getLogger().handlers] == [_InterceptHandler]


def test_calling_setup_twice_leaves_one_intercept_handler(monkeypatch):
    _setup(monkeypatch)
    stream = _setup(monkeypatch)

    logging.getLogger("x").warning("once")

    assert [record["message"] for record in _json_lines(stream)] == ["once"]


def test_uvicorn_loggers_lose_their_own_handlers_and_propagate(monkeypatch):
    elsewhere = io.StringIO()
    for name in SELF_HANDLING_LOGGERS:
        library_logger = logging.getLogger(name)
        library_logger.addHandler(logging.StreamHandler(elsewhere))
        library_logger.propagate = False
    stream = _setup(monkeypatch)

    logging.getLogger("uvicorn.error").warning("Started server process")
    logging.getLogger("uvicorn.access").warning("GET / 200")

    assert elsewhere.getvalue() == ""
    assert [record["message"] for record in _json_lines(stream)] == ["Started server process", "GET / 200"]
    for name in SELF_HANDLING_LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True


def test_the_root_level_follows_the_scalo_level(monkeypatch):
    stream = _setup(monkeypatch, level="WARNING")

    logging.getLogger("x").info("dropped")
    logging.getLogger("x").warning("kept")

    assert logging.getLogger().level == logging.WARNING
    assert [record["message"] for record in _json_lines(stream)] == ["kept"]


def test_opting_out_leaves_stdlib_logging_alone_and_removes_a_previous_handler(monkeypatch):
    _setup(monkeypatch)
    stream = _setup(monkeypatch, intercept_stdlib=False)

    logging.getLogger("x").warning("not routed")

    # With no root handler left, stdlib's lastResort writes the bare message to stderr.
    assert stream.getvalue() == "not routed\n"
    assert not any(isinstance(handler, _InterceptHandler) for handler in logging.getLogger().handlers)
