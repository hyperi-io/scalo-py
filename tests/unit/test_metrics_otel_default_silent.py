#  Project:   hyperi-pylib
#  File:      tests/unit/test_metrics_otel_default_silent.py
#  Purpose:   OTLP push silent by default; only enabled when endpoint set
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""T6: OTel backend with no endpoint configured must not attach OTLP push."""

from __future__ import annotations

import importlib.util

import pytest


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)


def _otel_available() -> bool:
    return importlib.util.find_spec("opentelemetry") is not None


pytestmark = pytest.mark.skipif(not _otel_available(), reason="opentelemetry not installed")


def test_default_does_not_attach_otlp_push():
    from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

    backend = OpenTelemetryBackend(app_name="testapp", config=None)
    assert backend.enabled, "Prometheus reader should still be on by default"
    # Readers description should NOT contain "otlp"


def test_explicit_endpoint_attaches_otlp_push():
    from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

    backend = OpenTelemetryBackend(
        app_name="testapp",
        config={"opentelemetry": {"endpoint": "http://otel-collector:4317"}},
    )
    assert backend.enabled


def test_env_endpoint_attaches_otlp_push(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    from hyperi_pylib.metrics.opentelemetry_backend import OpenTelemetryBackend

    backend = OpenTelemetryBackend(app_name="testapp", config=None)
    assert backend.enabled
