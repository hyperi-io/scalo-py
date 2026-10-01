#  Project:   scalo
#  File:      tests/unit/test_logger_output_formats.py
#  Purpose:   Console format, colour, keyword fields and scrubbing across TTY and non-TTY output
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Every console format renders keyword fields, scrubs them, and picks format and colour from the stream."""

import io
import json
import re
import sys

import pytest
from common.fake_secrets import github_classic_pat, opaque_secret
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.logger.logger import (
    _add_emoji_to_record,
    _get_log_format,
    _render_field_value,
    _render_fields,
    setup,
)

ANSI = re.compile(r"\x1b\[[0-9;]*m")
PROBE_FIELDS = 'stderr="openssl: bad key" sigma_id=abc123'
JSON_KEYS = {"timestamp", "level", "target", "function", "line_number", "message", "fields"}


class _Connection:
    """An object whose str() carries a credential."""

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def __str__(self) -> str:
        return f"Connection(user=svc password={self._secret})"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    with preserved_stdlib_logging():
        yield
        logger.remove()


def _setup(monkeypatch, *, tty: bool, **kwargs) -> StreamDouble:
    stream = StreamDouble(tty)
    monkeypatch.setattr(sys, "stderr", stream)
    setup(otel_tracing=False, **kwargs)
    return stream


def _probe() -> None:
    logger.warning("probe line", stderr="openssl: bad key", sigma_id="abc123")


def _only_json(stream: StreamDouble) -> dict:
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1, lines
    return json.loads(lines[0])


def _only_text(stream: StreamDouble) -> str:
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1, lines
    return lines[0]


# ---------------------------------------------------------------------------
# auto resolves both ways
# ---------------------------------------------------------------------------


def test_auto_on_a_pipe_writes_one_flat_json_object_with_fields(monkeypatch):
    stream = _setup(monkeypatch, tty=False)
    _probe()

    record = _only_json(stream)
    assert set(record) == JSON_KEYS
    assert record["fields"] == {"stderr": "openssl: bad key", "sigma_id": "abc123"}
    assert record["level"] == "WARNING"
    assert record["message"] == "probe line"
    assert record["target"] == __name__
    assert record["function"] == "_probe"
    assert isinstance(record["line_number"], int)
    assert record["timestamp"].endswith("Z")
    assert "\x1b" not in stream.getvalue()


def test_auto_on_a_tty_writes_coloured_text_with_fields(monkeypatch):
    stream = _setup(monkeypatch, tty=True)
    _probe()

    line = _only_text(stream)
    assert "\x1b[" in line
    assert ANSI.sub("", line).endswith(f"probe line {PROBE_FIELDS}")


@pytest.mark.parametrize("tty", [False, True])
def test_json_record_has_empty_fields_object_when_none_are_given(monkeypatch, tty):
    stream = _setup(monkeypatch, tty=tty, log_format="json")
    logger.info("bare")

    record = _only_json(stream)
    assert record["fields"] == {}
    assert "exception" not in record


@pytest.mark.parametrize("tty", [False, True])
def test_text_line_ends_at_the_message_when_there_are_no_fields(monkeypatch, tty):
    stream = _setup(monkeypatch, tty=tty, log_format="text")
    logger.info("bare")

    assert ANSI.sub("", _only_text(stream)).endswith(" - bare")


# ---------------------------------------------------------------------------
# explicit selectors win
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("selector", ["text", "console", "pretty", "human", "TEXT", " text "])
def test_text_selectors_on_a_pipe_write_plain_text_with_fields(monkeypatch, selector):
    stream = _setup(monkeypatch, tty=False, log_format=selector)
    _probe()

    line = _only_text(stream)
    assert "\x1b" not in line
    assert line.endswith(f"probe line {PROBE_FIELDS}")


@pytest.mark.parametrize("selector", ["text", "console"])
def test_text_selectors_from_the_environment_win_on_a_pipe(monkeypatch, selector):
    monkeypatch.setenv("LOG_FORMAT", selector)
    stream = _setup(monkeypatch, tty=False)
    _probe()

    line = _only_text(stream)
    assert "\x1b" not in line
    assert line.endswith(f"probe line {PROBE_FIELDS}")


def test_explicit_json_argument_wins_on_a_tty(monkeypatch):
    stream = _setup(monkeypatch, tty=True, log_format="json")
    _probe()

    assert _only_json(stream)["fields"]["sigma_id"] == "abc123"


def test_json_from_the_environment_wins_on_a_tty(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    stream = _setup(monkeypatch, tty=True)
    _probe()

    assert _only_json(stream)["fields"]["sigma_id"] == "abc123"


def test_caller_format_beats_the_environment(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    stream = _setup(monkeypatch, tty=False, log_format="text")
    _probe()

    assert _only_text(stream).endswith(PROBE_FIELDS)


def test_caller_auto_defers_to_the_environment(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    stream = _setup(monkeypatch, tty=False, log_format="auto")
    _probe()

    assert _only_text(stream).endswith(PROBE_FIELDS)


def test_otel_endpoint_makes_auto_json_on_a_tty(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    stream = _setup(monkeypatch, tty=True, log_format="auto")
    _probe()

    assert _only_json(stream)["fields"]["sigma_id"] == "abc123"


def test_unrecognised_format_falls_back_to_auto_and_says_which(monkeypatch):
    stream = _setup(monkeypatch, tty=False, log_format="logfmt")
    _probe()

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 2
    assert lines[0]["message"] == "Unrecognised log format, using auto"
    assert lines[0]["fields"]["log_format"] == "logfmt"
    assert lines[1]["fields"]["sigma_id"] == "abc123"


# ---------------------------------------------------------------------------
# CI output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tty", [False, True])
def test_ci_turns_auto_into_plain_text_with_fields(monkeypatch, tty):
    monkeypatch.setenv("CI", "true")
    stream = _setup(monkeypatch, tty=tty)
    _probe()

    line = _only_text(stream)
    assert "\x1b" not in line
    assert line.startswith("[WARNING ]")
    assert line.endswith(f"probe line {PROBE_FIELDS}")


def test_explicit_json_wins_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    stream = _setup(monkeypatch, tty=False, log_format="json")
    _probe()

    assert _only_json(stream)["fields"]["sigma_id"] == "abc123"


def test_github_actions_workflow_command_carries_fields(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    stream = _setup(monkeypatch, tty=False)
    _probe()

    line = _only_text(stream)
    assert line.startswith("::warning::")
    assert line.endswith(f"probe line {PROBE_FIELDS}")


# ---------------------------------------------------------------------------
# colour
# ---------------------------------------------------------------------------


def test_log_color_true_colours_text_on_a_pipe(monkeypatch):
    monkeypatch.setenv("LOG_COLOR", "true")
    stream = _setup(monkeypatch, tty=False, log_format="text")
    _probe()

    assert "\x1b[" in stream.getvalue()


@pytest.mark.parametrize(("name", "value"), [("LOG_COLOR", "false"), ("NO_COLOR", "1")])
def test_colour_off_switches_keep_a_tty_on_plain_text(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    stream = _setup(monkeypatch, tty=True)
    _probe()

    line = _only_text(stream)
    assert "\x1b" not in line
    assert line.endswith(f"probe line {PROBE_FIELDS}")


# ---------------------------------------------------------------------------
# scrubbing reaches the fields in every format
# ---------------------------------------------------------------------------

_SCRUB_CASES = {
    "json-pipe-auto": ({}, False, None),
    "json-tty-explicit": ({}, True, "json"),
    "text-pipe-explicit": ({}, False, "text"),
    "text-tty-auto": ({}, True, None),
    "ci-pipe": ({"CI": "true"}, False, None),
    "ci-tty": ({"CI": "true"}, True, None),
    "github-actions": ({"GITHUB_ACTIONS": "true"}, False, None),
}


@pytest.mark.parametrize(("env", "tty", "log_format"), _SCRUB_CASES.values(), ids=_SCRUB_CASES.keys())
def test_secrets_in_fields_are_masked(monkeypatch, env, tty, log_format):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    stream = _setup(monkeypatch, tty=tty, log_format=log_format)

    by_key = opaque_secret("bykey")
    in_url = opaque_secret("inurl")
    nested_key = opaque_secret("nestedkey")
    nested_value = opaque_secret("nestedvalue")
    in_object = opaque_secret("inobject")
    provider_shaped = github_classic_pat()
    logger.warning(
        "probe",
        password=by_key,
        url=f"https://api.example.com/v1?api_key={in_url}",
        cfg={"token": nested_key, "notes": [f"password={nested_value}"]},
        conn=_Connection(in_object),
        note=provider_shaped,
        sigma_id="abc123",
    )

    output = stream.getvalue()
    for secret in (by_key, in_url, nested_key, nested_value, in_object, provider_shaped):
        assert secret not in output, f"{secret} leaked: {output}"
    assert "REDACTED" in output
    assert "sigma_id" in output
    assert "abc123" in output


def test_secrets_in_fields_are_masked_in_the_file_format():
    buffer = io.StringIO()
    flt = _add_emoji_to_record(False, convert_to_text=True, mask_sensitive=True, masking_level="simple")
    logger.add(buffer, format=_get_log_format(is_file=True), filter=flt, enqueue=False, colorize=False)
    secret = opaque_secret("file")
    nested = opaque_secret("filenested")

    logger.warning("probe", password=secret, cfg={"token": nested}, sigma_id="abc123")

    output = buffer.getvalue()
    assert secret not in output
    assert nested not in output
    assert "sigma_id=abc123" in output


# ---------------------------------------------------------------------------
# JSON details
# ---------------------------------------------------------------------------


def test_json_exception_stays_on_one_line_with_the_traceback(monkeypatch):
    stream = _setup(monkeypatch, tty=False)
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed", job="j1")

    record = _only_json(stream)
    assert record["fields"] == {"job": "j1"}
    assert "Traceback" in record["exception"]
    assert "ValueError: boom" in record["exception"]


def test_enqueued_json_keeps_fields_across_the_writer_thread(monkeypatch):
    monkeypatch.setenv("LOG_ENQUEUE", "1")
    stream = _setup(monkeypatch, tty=False)
    _probe()
    logger.complete()

    assert _only_json(stream)["fields"] == {"stderr": "openssl: bad key", "sigma_id": "abc123"}


def test_non_json_values_are_rendered_as_json_types_or_strings(monkeypatch):
    stream = _setup(monkeypatch, tty=False)
    logger.info("types", count=3, ratio=0.5, ok=True, missing=None, tags=("a", "b"), conn=_Connection("x"))

    fields = _only_json(stream)["fields"]
    assert fields["count"] == 3
    assert fields["ratio"] == 0.5
    assert fields["ok"] is True
    assert fields["missing"] is None
    assert fields["tags"] == ["a", "b"]
    assert isinstance(fields["conn"], str)


# ---------------------------------------------------------------------------
# other sinks still see a plain dict
# ---------------------------------------------------------------------------


def test_a_user_sink_still_sees_extra_as_a_dict(monkeypatch):
    _setup(monkeypatch, tty=False)
    captured = []
    logger.add(captured.append, format="{extra}", enqueue=False)
    _probe()

    extra = captured[0].record["extra"]
    assert isinstance(extra, dict)
    assert extra["sigma_id"] == "abc123"
    assert captured[0].startswith("{'stderr': 'openssl: bad key', 'sigma_id': 'abc123'}")


# ---------------------------------------------------------------------------
# text value quoting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        ("plain", "plain"),
        ("a b", '"a b"'),
        ("k=v", '"k=v"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("", '""'),
        ("line1\nline2", '"line1\\nline2"'),
        ("\x1b[31mred", '"\\u001b[31mred"'),
        ("caf\N{LATIN SMALL LETTER E WITH ACUTE}", "caf\N{LATIN SMALL LETTER E WITH ACUTE}"),
        (3, "3"),
        (0.5, "0.5"),
        (True, "true"),
        (None, "null"),
        (["a", "b"], '"[\\"a\\", \\"b\\"]"'),
    ],
)
def test_field_values_are_quoted_only_when_they_would_not_parse_back(value, rendered):
    assert _render_field_value(value) == rendered


def test_fields_render_as_space_led_pairs_and_empty_renders_nothing():
    assert _render_fields({}) == ""
    assert _render_fields({"a": 1, "b": "x y"}) == ' a=1 b="x y"'
