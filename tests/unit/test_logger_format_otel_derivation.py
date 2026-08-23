#  Project:   scalo
#  File:      tests/unit/test_logger_format_otel_derivation.py
#  Purpose:   Console format derives from otel presence when nothing sets it
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unset log format derives json iff the deployment ships telemetry to otel."""

from __future__ import annotations

from scalo.logger.logger import _resolve_console_format


def test_unset_format_with_otel_endpoint_is_json(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve_console_format(None, {}) == "json"


def test_unset_format_without_otel_endpoint_is_lines(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert _resolve_console_format(None, {}) == ""


def test_blank_otel_endpoint_does_not_flip_to_json(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")
    assert _resolve_console_format(None, {}) == ""


def test_explicit_caller_format_wins_over_otel(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve_console_format("text", {}) == "text"


def test_env_var_wins_over_otel_derivation(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve_console_format(None, {}) == "console"


def test_config_format_wins_over_otel_derivation(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
    assert _resolve_console_format(None, {"format": "text"}) == "text"
