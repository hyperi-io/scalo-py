#  Project:   scalo
#  File:      tests/unit/test_logger_format_otel_derivation.py
#  Purpose:   Console format derives from otel presence when nothing sets it
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""An auto or unset log format derives json when the deployment ships telemetry to otel."""

import pytest

from scalo.logger.logger import _resolve_console_format


def _resolve(log_format, config, *, is_tty=True):
    return _resolve_console_format(log_format, config, is_tty=is_tty, ci_mode=False)


@pytest.mark.parametrize("unset", [None, "", "auto", "AUTO"])
def test_unset_or_auto_format_with_otel_endpoint_is_json_even_on_a_tty(monkeypatch, unset):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve(unset, {"format": "auto"}) == "json"


def test_unset_format_without_otel_endpoint_follows_the_tty(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert _resolve(None, {}, is_tty=True) == "text"
    assert _resolve(None, {}, is_tty=False) == "json"


def test_blank_otel_endpoint_does_not_flip_to_json(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")
    assert _resolve(None, {}, is_tty=True) == "text"


def test_explicit_caller_format_wins_over_otel(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve("text", {}) == "text"


def test_env_var_wins_over_otel_derivation(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve(None, {}) == "text"


def test_config_format_wins_over_otel_derivation(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve(None, {"format": "text"}) == "text"
