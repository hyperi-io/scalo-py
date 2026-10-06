#  Project:   scalo
#  File:      tests/unit/test_metrics_otel_defaults.py
#  Purpose:   OTLP push on by default, with the documented ways to switch it off
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""OTLP metric-push resolution.

The contract is shared with scalo-rs: push is ON by default and aimed at a local
collector, the master switch and a blank endpoint are the two ways off, and the
standard ``OTEL_*`` env vars outrank config. These assert the resolution rather
than standing up a MeterProvider, so they say what they mean.
"""

from __future__ import annotations

import importlib.util

import pytest

from scalo.metrics.opentelemetry_backend import (
    DEFAULT_OTLP_ENDPOINTS,
    resolve_otel_config,
)
from scalo.otel_backoff import append_signal_path


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch):
    """Start from no OTel env, including the suite-wide off switch in conftest."""
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_METRIC_EXPORT_INTERVAL",
        "OTEL_METRIC_EXPORT_TIMEOUT",
        "OTEL_SERVICE_NAME",
        "APP_ENV",
        "ENVIRONMENT",
        "ENV",
    ):
        monkeypatch.delenv(name, raising=False)


def _otel_available() -> bool:
    return importlib.util.find_spec("opentelemetry") is not None


class TestDefaults:
    def test_push_is_on_and_aimed_at_a_local_collector(self):
        resolved = resolve_otel_config({})
        assert resolved.enabled
        assert resolved.endpoint == DEFAULT_OTLP_ENDPOINTS["grpc"] == "http://localhost:4317"
        assert resolved.protocol == "grpc"
        assert resolved.push_active, "OTLP push must be on out of the box"

    def test_http_protocol_defaults_to_the_http_port(self):
        resolved = resolve_otel_config({"protocol": "http"})
        assert resolved.endpoint == "http://localhost:4318"

    def test_export_deadline_is_bounded(self):
        """A collector that accepts and never answers must not hold the exporter."""
        resolved = resolve_otel_config({})
        assert 0 < resolved.export_timeout_millis <= resolved.export_interval_millis

    def test_deployment_environment_defaults_to_development(self):
        assert resolve_otel_config({}).deployment_environment == "development"

    def test_deployment_environment_comes_from_app_env(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        assert resolve_otel_config({}).deployment_environment == "production"


class TestSwitchingItOff:
    def test_master_switch(self):
        resolved = resolve_otel_config({"enabled": False})
        assert not resolved.push_active

    def test_blank_endpoint_in_config(self):
        assert not resolve_otel_config({"endpoint": ""}).push_active

    def test_blank_endpoint_in_env(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        assert not resolve_otel_config({"endpoint": "http://collector:4317"}).push_active

    def test_whitespace_endpoint_reads_as_off_not_as_a_uri(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")
        assert not resolve_otel_config({}).push_active


class TestEnvOutranksConfig:
    def test_endpoint(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://from-env:4317")
        assert resolve_otel_config({"endpoint": "http://from-config:4317"}).endpoint == "http://from-env:4317"

    @pytest.mark.parametrize("value", ["http", "http/protobuf"])
    def test_protocol(self, monkeypatch, value):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", value)
        assert resolve_otel_config({"protocol": "grpc"}).protocol == "http"

    def test_unknown_protocol_falls_back_rather_than_failing(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "carrier-pigeon")
        assert resolve_otel_config({"protocol": "http"}).protocol == "http"

    def test_interval_and_timeout(self, monkeypatch):
        monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "15000")
        monkeypatch.setenv("OTEL_METRIC_EXPORT_TIMEOUT", "3000")
        resolved = resolve_otel_config({"export_interval_millis": 60000, "export_timeout_millis": 10000})
        assert resolved.export_interval_millis == 15000
        assert resolved.export_timeout_millis == 3000

    def test_a_non_numeric_interval_does_not_take_the_process_down(self, monkeypatch):
        monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", "soon")
        assert resolve_otel_config({"export_interval_millis": 60000}).export_interval_millis == 60000


class TestPassThrough:
    def test_headers_survive_resolution(self):
        resolved = resolve_otel_config({"headers": {"x-api-key": "s3cret"}})
        assert resolved.headers == {"x-api-key": "s3cret"}

    def test_resource_attributes_survive_resolution(self):
        resolved = resolve_otel_config({"resource_attributes": {"team": "control-plane"}})
        assert resolved.resource_attributes == {"team": "control-plane"}


class TestSignalPath:
    """The HTTP protocol needs the signal path; the SDK only appends it to the
    endpoint IT reads from the environment, and scalo passes one in."""

    def test_path_is_appended_to_a_base_endpoint(self):
        assert append_signal_path("http://localhost:4318", "v1/metrics") == "http://localhost:4318/v1/metrics"

    def test_trailing_slash_does_not_double_up(self):
        assert append_signal_path("http://localhost:4318/", "v1/traces") == "http://localhost:4318/v1/traces"

    def test_an_endpoint_that_already_names_the_signal_is_left_alone(self):
        endpoint = "http://collector:4318/v1/metrics"
        assert append_signal_path(endpoint, "v1/metrics") == endpoint


@pytest.fixture
def otel_backend():
    """Build backends and shut them down.

    A backend with a real OTLP reader keeps a thread exporting to a collector
    that is not there long after the test returns, which surfaces at session end
    as a loguru write to a stream pytest has already closed.
    """
    from scalo.metrics.opentelemetry_backend import OpenTelemetryBackend

    built = []

    def _build(app_name: str, config: dict | None = None):
        backend = OpenTelemetryBackend(app_name=app_name, config=config)
        built.append(backend)
        return backend

    yield _build

    for backend in built:
        try:
            backend.stop_auto_update()
        except Exception:
            pass


@pytest.mark.skipif(not _otel_available(), reason="opentelemetry not installed")
class TestBackendComposition:
    def test_prometheus_scrape_survives_a_broken_otlp_endpoint(self, otel_backend):
        """Losing the push path must never cost the scrape endpoint."""
        backend = otel_backend(
            "degraded",
            {"opentelemetry": {"endpoint": "not a url at all", "protocol": "grpc"}},
        )
        assert backend.enabled, "the Prometheus reader must still be installed"

    def test_configured_resource_attributes_win_over_the_auto_set_ones(self, otel_backend):
        backend = otel_backend(
            "attrs",
            {
                "opentelemetry": {
                    "endpoint": "",
                    "resource_attributes": {"deployment.environment.name": "canary"},
                }
            },
        )
        attributes = backend._provider._sdk_config.resource.attributes
        assert attributes["deployment.environment.name"] == "canary"

    def test_the_push_exporter_is_actually_gated(self, monkeypatch, otel_backend):
        """The backoff is worth nothing if the wiring silently comes undone."""
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        from scalo.otel_backoff import GatedMetricExporter

        backend = otel_backend("gated", {"opentelemetry": {"endpoint": "http://localhost:4317"}})
        readers = backend._provider._metric_readers
        periodic = [r for r in readers if isinstance(r, PeriodicExportingMetricReader)]
        assert periodic, "no OTLP push reader was installed"
        assert isinstance(periodic[0]._exporter, GatedMetricExporter), (
            "the OTLP exporter is not behind the backoff gate, so a dead collector is dialled every tick again"
        )

    def test_the_export_deadline_reaches_the_exporter(self, otel_backend):
        backend = otel_backend(
            "deadline",
            {"opentelemetry": {"endpoint": "http://localhost:4317", "export_timeout_millis": 3000}},
        )
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        periodic = [r for r in backend._provider._metric_readers if isinstance(r, PeriodicExportingMetricReader)]
        # The SDK exporter takes seconds; scalo configures milliseconds.
        assert periodic[0]._exporter._inner._timeout == 3.0

    def test_deployment_environment_is_tagged_on_the_resource(self, monkeypatch, otel_backend):
        monkeypatch.setenv("APP_ENV", "staging")
        backend = otel_backend("tagged", {"opentelemetry": {"endpoint": ""}})
        attributes = backend._provider._sdk_config.resource.attributes
        assert attributes["deployment.environment.name"] == "staging"
