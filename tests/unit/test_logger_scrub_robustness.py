#  Project:   scalo
#  File:      tests/unit/test_logger_scrub_robustness.py
#  Purpose:   The scrub filter never raises, bounds its work, and scrubs tracebacks, keys and pairs
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A field the filter cannot handle still yields one scrubbed line, and nothing reaches stderr raw."""

import io
import json
import logging
import math
import subprocess
import sys
import threading

import pytest
from common.fake_secrets import github_classic_pat, opaque_secret
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.config import config as config_module
from scalo.logger.logger import (
    _FIELD_SCRUB_BUDGET,
    _MAX_FIELD_DEPTH,
    _add_emoji_to_record,
    _get_log_format,
    _unrecognised_format,
    setup,
)
from scalo.logger.scrub import build_scrubber

LOGURU_ERROR = "Logging error in Loguru"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    with preserved_stdlib_logging():
        yield
        logger.remove()


def _setup(monkeypatch, log_format: str | None = "json", **kwargs) -> StreamDouble:
    stream = StreamDouble(False)
    monkeypatch.setattr(sys, "stderr", stream)
    setup(otel_tracing=False, log_format=log_format, **kwargs)
    return stream


def _only_json(stream: StreamDouble) -> dict:
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1, lines
    return json.loads(lines[0])


class _UnprintableRow:
    """An object whose str() raises, as a detached ORM row does."""

    def __str__(self) -> str:
        raise RuntimeError("detached instance")


class _CountingScrubber:
    """A real scrubber that counts its calls."""

    def __init__(self) -> None:
        self._inner = build_scrubber()
        self.calls = 0

    def scrub(self, text: str) -> str:
        self.calls += 1
        return self._inner.scrub(text)


class _BrokenScrubber:
    """A scrubber whose every call fails."""

    def scrub(self, text: str) -> str:
        raise RuntimeError("scrubber down")


class _AuthError(Exception):
    """An exception whose str() is built from an attribute, not from args."""

    def __init__(self, token: str) -> None:
        super().__init__("auth failed")
        self.token = token

    def __str__(self) -> str:
        return f"auth failed token={self.token}"


# ---------------------------------------------------------------------------
# a field the filter cannot handle still gives one scrubbed line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_a_cyclic_field_is_logged_and_a_later_secret_stays_masked(monkeypatch, log_format):
    stream = _setup(monkeypatch, log_format)
    secret = opaque_secret("aftercycle")
    ctx = {"name": "job-1"}
    ctx["self"] = ctx

    logger.warning("cyclic", ctx=ctx, password=secret)

    output = stream.getvalue()
    assert LOGURU_ERROR not in output
    assert secret not in output
    assert len(output.splitlines()) == 1
    assert "<cycle>" in output


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_a_field_nested_past_the_depth_limit_is_logged(monkeypatch, log_format):
    stream = _setup(monkeypatch, log_format)
    node: list = []
    for _ in range(3000):
        node = [node]

    logger.warning("deep", tree=node, sigma_id="abc123")

    output = stream.getvalue()
    assert LOGURU_ERROR not in output
    assert "sigma_id" in output
    assert "<depth limit>" in output


def test_the_depth_limit_keeps_the_levels_above_it(monkeypatch):
    stream = _setup(monkeypatch)
    node: list = ["leaf"]
    for _ in range(_MAX_FIELD_DEPTH + 5):
        node = [node]

    logger.warning("deep", tree=node)

    tree = _only_json(stream)["fields"]["tree"]
    for _ in range(_MAX_FIELD_DEPTH):
        assert isinstance(tree, list)
        (tree,) = tree
    assert tree == "<depth limit>"


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_a_field_whose_str_raises_is_a_placeholder_and_the_traceback_stays_scrubbed(monkeypatch, log_format):
    stream = _setup(monkeypatch, log_format)
    secret = opaque_secret("excinrecord")

    try:
        raise ValueError(f"password={secret}")
    except ValueError:
        logger.exception("row save failed", row=_UnprintableRow(), sigma_id="abc123")

    output = stream.getvalue()
    assert LOGURU_ERROR not in output
    assert secret not in output
    assert "<unprintable _UnprintableRow>" in output
    assert "sigma_id" in output
    assert "ValueError" in output


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_a_failing_scrubber_never_lets_the_record_out_raw(monkeypatch, log_format):
    stream = _setup(monkeypatch, log_format, scrubber=_BrokenScrubber())
    secret = opaque_secret("brokenscrubber")

    try:
        raise ValueError(f"password={secret}")
    except ValueError:
        logger.exception(f"login password={secret}", url=f"https://h/?token={secret}", password=secret)

    output = stream.getvalue()
    assert LOGURU_ERROR not in output
    assert secret not in output
    assert "<message not logged: RuntimeError while scrubbing it>" in output
    assert "<traceback not logged: RuntimeError while rendering it>" in output


# ---------------------------------------------------------------------------
# tracebacks are scrubbed in every format
# ---------------------------------------------------------------------------


def _raise_auth_error(token: str) -> None:
    raise _AuthError(token)


def _raise_group(token: str) -> None:
    raise ExceptionGroup("batch", [ValueError(f"password={token}")])


def _raise_with_note(token: str) -> None:
    err = ValueError("bad")
    err.add_note(f"token={token}")
    raise err


_RAISERS = {
    "str-from-attribute": _raise_auth_error,
    "exception-group": _raise_group,
    "notes": _raise_with_note,
}

_TRACEBACK_FORMATS = {
    "json": ({}, "json"),
    "text": ({}, "text"),
    "ci": ({"CI": "true"}, None),
    "github-actions": ({"GITHUB_ACTIONS": "true"}, None),
}


@pytest.mark.parametrize("raiser", _RAISERS.values(), ids=_RAISERS.keys())
@pytest.mark.parametrize(("env", "log_format"), _TRACEBACK_FORMATS.values(), ids=_TRACEBACK_FORMATS.keys())
def test_traceback_text_is_scrubbed(monkeypatch, raiser, env, log_format):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    stream = _setup(monkeypatch, log_format)
    secret = opaque_secret("traceback")

    try:
        raiser(secret)
    except Exception:
        logger.exception("failed")

    output = stream.getvalue()
    assert secret not in output
    assert "Traceback" in output
    assert "REDACTED" in output


def test_traceback_text_is_scrubbed_in_the_file_format():
    buffer = io.StringIO()
    flt = _add_emoji_to_record(False, convert_to_text=True, mask_sensitive=True, masking_level="simple")
    logger.add(buffer, format=_get_log_format(is_file=True), filter=flt, enqueue=False, colorize=False)
    secret = opaque_secret("filetraceback")

    try:
        _raise_auth_error(secret)
    except _AuthError:
        logger.exception("failed")

    output = buffer.getvalue()
    assert secret not in output
    assert "_AuthError" in output


def test_a_stdlib_traceback_is_scrubbed(monkeypatch):
    stream = _setup(monkeypatch)
    secret = opaque_secret("stdlibtraceback")

    try:
        _raise_auth_error(secret)
    except _AuthError:
        logging.getLogger("lib").exception("library caught it")

    record = _only_json(stream)
    assert secret not in stream.getvalue()
    assert "_AuthError" in record["exception"]


def test_an_enqueued_record_keeps_its_scrubbed_traceback(monkeypatch):
    monkeypatch.setenv("LOG_ENQUEUE", "1")
    stream = _setup(monkeypatch)
    secret = opaque_secret("enqueuedtraceback")

    try:
        _raise_auth_error(secret)
    except _AuthError:
        logger.exception("failed")
    logger.complete()

    record = _only_json(stream)
    assert secret not in stream.getvalue()
    assert "_AuthError" in record["exception"]


# ---------------------------------------------------------------------------
# field scrubbing work is bounded
# ---------------------------------------------------------------------------


def test_a_large_field_scrubs_at_most_the_budget_and_says_what_it_elided(monkeypatch):
    scrubber = _CountingScrubber()
    stream = _setup(monkeypatch, scrubber=scrubber)

    logger.info("probe", data=[f"value-{i}" for i in range(10_000)], sigma_id="abc123")

    fields = _only_json(stream)["fields"]
    assert scrubber.calls <= _FIELD_SCRUB_BUDGET + 4
    assert len(fields["data"]) == _FIELD_SCRUB_BUDGET + 1
    assert fields["data"][-1] == f"<elided: {10_000 - _FIELD_SCRUB_BUDGET} more items>"
    assert fields["sigma_id"] == "abc123"


def test_a_large_mapping_elides_its_remaining_entries(monkeypatch):
    stream = _setup(monkeypatch)

    logger.info("probe", data={f"k{i}": f"value-{i}" for i in range(10_000)})

    data = _only_json(stream)["fields"]["data"]
    assert data["<elided>"].endswith("more entries")
    assert len(data) < 100


def test_a_small_field_is_logged_whole(monkeypatch):
    stream = _setup(monkeypatch)
    hosts = [f"host-{i}.example.com" for i in range(20)]

    logger.info("probe", hosts=hosts)

    assert _only_json(stream)["fields"]["hosts"] == hosts


# ---------------------------------------------------------------------------
# keys, header pairs and line breaks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_a_token_used_as_a_key_is_scrubbed(monkeypatch, log_format):
    stream = _setup(monkeypatch, log_format)
    token = github_classic_pat()

    logger.warning("cache", sessions={token: "alice"})
    logger.bind(**{token: 1}).warning("bound")

    output = stream.getvalue()
    assert token not in output
    assert "alice" in output


@pytest.mark.parametrize(
    "pair",
    [
        ("authorization", "Basic {secret}"),
        (b"authorization", b"Basic {secret}"),
        ["Authorization", "Basic {secret}"],
    ],
    ids=["str", "bytes", "list"],
)
def test_a_sensitive_header_pair_masks_its_value(monkeypatch, pair):
    stream = _setup(monkeypatch)
    secret = opaque_secret("headerpair")
    name, template = pair
    value = (
        template.replace(b"{secret}", secret.encode())
        if isinstance(template, bytes)
        else template.format(secret=secret)
    )

    logger.warning("upstream", headers=[(name, value), ("accept", "application/json")])

    headers = _only_json(stream)["fields"]["headers"]
    assert secret not in stream.getvalue()
    assert headers[0][1] == "***REDACTED***"
    assert headers[1] == ["accept", "application/json"]


def test_non_finite_floats_keep_the_json_line_strict(monkeypatch):
    stream = _setup(monkeypatch)

    logger.warning("ratio", ratio=math.nan, ceiling=math.inf, floor=-math.inf)

    def reject(token):
        raise ValueError(f"non-RFC-8259 token {token}")

    record = json.loads(stream.getvalue(), parse_constant=reject)
    assert record["fields"] == {"ratio": "NaN", "ceiling": "Infinity", "floor": "-Infinity"}


def test_a_newline_in_a_text_field_key_cannot_start_a_line(monkeypatch):
    stream = _setup(monkeypatch, "text")

    logger.bind(**{"k\nFORGED-LINE key": 1}).warning("key with a newline")

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert lines[0].endswith('"k\\nFORGED-LINE key"=1')


@pytest.mark.parametrize("log_format", ["json", "text"])
def test_line_and_paragraph_separators_in_fields_do_not_split_the_line(monkeypatch, log_format):
    stream = _setup(monkeypatch, log_format)

    logger.warning("sep", note="a\u2028b", para="c\u2029d", nel="e\x85f")

    assert len(stream.getvalue().splitlines()) == 1
    assert "\\u2028" in stream.getvalue()


def test_the_json_line_escapes_separators_in_the_message(monkeypatch):
    stream = _setup(monkeypatch)

    logger.warning("sep\u2028forged")

    assert len(stream.getvalue().splitlines()) == 1
    assert _only_json(stream)["message"] == "sep\u2028forged"


# ---------------------------------------------------------------------------
# enqueue and the stdlib bridge
# ---------------------------------------------------------------------------


def test_an_unpicklable_stdlib_field_does_not_lose_the_record_under_enqueue(monkeypatch):
    monkeypatch.setenv("LOG_ENQUEUE", "1")
    stream = _setup(monkeypatch)

    logging.getLogger("lib").warning("stdlib with a lock", extra={"lock": threading.Lock(), "sigma_id": "abc123"})
    logger.complete()

    output = stream.getvalue()
    assert LOGURU_ERROR not in output
    record = _only_json(stream)
    assert record["fields"]["sigma_id"] == "abc123"
    assert isinstance(record["fields"]["lock"], str)


def test_uvicorns_colour_message_is_not_a_field(monkeypatch):
    stream = _setup(monkeypatch)

    logging.getLogger("uvicorn.error").info(
        "Started server process [%d]", 42, extra={"color_message": "Started server process [\x1b[36m%d\x1b[0m]"}
    )

    record = _only_json(stream)
    assert record["message"] == "Started server process [42]"
    assert record["fields"] == {}


def test_detect_secrets_loses_its_own_handler(monkeypatch):
    raw = io.StringIO()
    library_logger = logging.getLogger("detect-secrets")
    library_logger.addHandler(logging.StreamHandler(raw))
    stream = _setup(monkeypatch)

    library_logger.error("password=%s", opaque_secret("detectsecrets"))

    assert raw.getvalue() == ""
    assert library_logger.handlers == []
    assert "REDACTED" in _only_json(stream)["message"]


# ---------------------------------------------------------------------------
# configuration edges
# ---------------------------------------------------------------------------


@pytest.fixture
def logging_settings():
    """Set ``logging.*`` keys on the process-wide settings for one test."""
    settings = config_module.settings
    previous = settings.get("logging")
    try:
        yield settings
    finally:
        settings.unset("logging")
        if previous is not None:
            settings.set("logging", previous)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("on", True), ("ON", True), ("true", True), ("yes", True), ("off", False), ("false", False), ("no", False)],
)
def test_intercept_stdlib_reads_on_and_off_words(logging_settings, value, expected):
    logging_settings.set("logging.intercept_stdlib", value)

    assert config_module.get_logging_config()["intercept_stdlib"] is expected


def test_an_unrecognised_intercept_stdlib_value_keeps_the_bridge_on_and_says_so(logging_settings):
    logging_settings.set("logging.intercept_stdlib", "enabled")

    with pytest.warns(UserWarning, match="intercept_stdlib"):
        assert config_module.get_logging_config()["intercept_stdlib"] is True


@pytest.mark.parametrize(
    ("caller", "config_format", "named"),
    [
        ("json", "logfmt", None),
        ("logfmt", "json", "logfmt"),
        (None, "logfmt", "logfmt"),
        ("auto", "logfmt", "logfmt"),
    ],
)
def test_the_unrecognised_format_warning_names_only_a_selector_consulted(monkeypatch, caller, config_format, named):
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    assert _unrecognised_format(caller, {"format": config_format}) == named


def test_setup_fails_when_the_console_sink_has_no_stderr(monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)

    with pytest.raises(RuntimeError, match="sys.stderr"):
        setup(otel_tracing=False)


def test_a_curl_command_in_a_traceback_is_scrubbed_like_a_message(monkeypatch):
    stream = _setup(monkeypatch)
    secret = opaque_secret("curlpw")
    command = ["curl", "-H", f"Authorization: Bearer {secret}", "https://h"]

    try:
        raise subprocess.CalledProcessError(1, command)
    except subprocess.CalledProcessError:
        logger.exception("fetch failed")

    assert secret not in stream.getvalue()
