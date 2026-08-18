#  Project:   scalo
#  File:      tests/unit/test_otel_tracing.py
#  Purpose:   Span-export config resolution and composition
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""OTLP span export.

The contract is shared with scalo-rs ``otel_tracing``: on by default, aimed at a
local collector, parent-based sampling under 1.0, a bounded queue so an
unreachable collector costs spans and never memory, and a bounded flush on exit
so it cannot eat a termination grace period.
"""

from __future__ import annotations

import importlib.util

import pytest

from scalo import otel_tracing
from scalo.otel_tracing import OtelTracingConfig, config_from_cascade, resolve


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch):
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_SERVICE_NAME",
        "OTEL_TRACES_SAMPLER_ARG",
        "APP_ENV",
        "ENVIRONMENT",
        "ENV",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_leaked_provider():
    """Any provider a test installs must not outlive it."""
    yield
    otel_tracing.shutdown()


def _otel_available() -> bool:
    return importlib.util.find_spec("opentelemetry") is not None


class TestDefaults:
    def test_export_is_on_and_aimed_at_a_local_collector(self):
        config = OtelTracingConfig()
        assert config.enabled
        assert config.endpoint == "http://localhost:4317"
        assert config.protocol == "grpc"
        assert config.is_active()

    def test_service_name_has_no_default(self):
        """A package-name default would report every service in the fleet as scalo."""
        assert OtelTracingConfig().service_name == ""

    def test_sampling_is_well_under_everything(self):
        ratio = OtelTracingConfig().sample_ratio
        assert 0 < ratio < 1.0, "exporting every span costs more than the traces are worth"

    def test_the_queue_is_bounded(self):
        config = OtelTracingConfig()
        assert config.batch_max_queue_size > 0, "an unbounded queue lets a dead collector grow memory"
        assert config.batch_max_export_batch_size <= config.batch_max_queue_size

    def test_shutdown_flush_stays_inside_a_termination_grace_period(self):
        assert 0 < otel_tracing.SHUTDOWN_TIMEOUT_MILLIS <= 5_000


class TestSwitchingItOff:
    def test_master_switch(self):
        assert not OtelTracingConfig(enabled=False).is_active()

    def test_blank_endpoint(self):
        assert not OtelTracingConfig(endpoint="").is_active()

    def test_whitespace_endpoint(self):
        assert not OtelTracingConfig(endpoint="   ").is_active()

    def test_blank_endpoint_from_env(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        assert not OtelTracingConfig().is_active()


class TestEnvOutranksConfig:
    def test_endpoint(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://from-env:4317")
        assert resolve(OtelTracingConfig(endpoint="http://from-config:4317")).endpoint == "http://from-env:4317"

    def test_protocol(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
        assert resolve(OtelTracingConfig()).protocol == "http"

    def test_service_name(self, monkeypatch):
        monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
        assert resolve(OtelTracingConfig(service_name="from-config")).service_name == "from-env"

    def test_sampler_arg(self, monkeypatch):
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "1.0")
        assert resolve(OtelTracingConfig()).sample_ratio == 1.0

    def test_a_non_numeric_sampler_arg_does_not_take_the_process_down(self, monkeypatch):
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "all-of-them")
        assert resolve(OtelTracingConfig()).sample_ratio == OtelTracingConfig().sample_ratio


class TestFromCascade:
    def test_absent_section_yields_the_defaults(self):
        class _Empty:
            def get(self, key, default=None):
                return default

        assert config_from_cascade(_Empty()) == OtelTracingConfig()

    def test_unreadable_settings_yield_the_defaults(self):
        class _Exploding:
            def get(self, *args, **kwargs):
                raise RuntimeError("settings unavailable")

        assert config_from_cascade(_Exploding()) == OtelTracingConfig()

    def test_section_values_are_read(self):
        class _Settings:
            def get(self, key, default=None):
                if key == "otel_tracing":
                    return {
                        "enabled": "false",
                        "endpoint": "http://collector:4318",
                        "protocol": "http",
                        "sample_ratio": "0.5",
                        "batch_max_queue_size": "128",
                    }
                return default

        config = config_from_cascade(_Settings())
        assert config.enabled is False, "a string 'false' from an env-backed cascade must read as off"
        assert config.endpoint == "http://collector:4318"
        assert config.protocol == "http"
        assert config.sample_ratio == 0.5
        assert config.batch_max_queue_size == 128

    def test_http_protocol_picks_up_the_http_default_port(self):
        class _Settings:
            def get(self, key, default=None):
                return {"protocol": "http"} if key == "otel_tracing" else default

        assert config_from_cascade(_Settings()).endpoint == "http://localhost:4318"


@pytest.mark.skipif(not _otel_available(), reason="opentelemetry not installed")
class TestComposition:
    def test_disabled_installs_nothing(self):
        assert otel_tracing.setup_tracing(OtelTracingConfig(enabled=False)) is False

    def test_setup_installs_a_provider_and_is_idempotent(self):
        config = OtelTracingConfig(service_name="unit-test")
        assert otel_tracing.setup_tracing(config) is True
        assert otel_tracing.setup_tracing(config) is True, "a second call must not build a second provider"

    def test_the_sampler_is_parent_based(self):
        """An upstream sampling decision must be honoured, or traces come apart."""
        from opentelemetry.sdk.trace.sampling import ParentBased

        otel_tracing.setup_tracing(OtelTracingConfig(service_name="sampler-test"))
        assert isinstance(otel_tracing._PROVIDER.sampler, ParentBased)

    def test_the_service_name_reaches_the_resource(self):
        otel_tracing.setup_tracing(OtelTracingConfig(), service_name="named-service")
        attributes = otel_tracing._PROVIDER.resource.attributes
        assert attributes["service.name"] == "named-service"

    def test_deployment_environment_is_tagged(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "staging")
        otel_tracing.setup_tracing(OtelTracingConfig(service_name="env-test"))
        attributes = otel_tracing._PROVIDER.resource.attributes
        assert attributes["deployment.environment.name"] == "staging"

    def test_a_broken_endpoint_degrades_rather_than_raising(self):
        """Telemetry that cannot start must never stop a service starting."""
        result = otel_tracing.setup_tracing(OtelTracingConfig(endpoint="not a url", protocol="grpc"))
        assert isinstance(result, bool), "setup_tracing must report an outcome, never propagate the failure"

    def test_a_missing_extra_is_quiet(self, monkeypatch):
        """A base install made a choice; it should not be warned at on every setup."""
        levels = []

        class _Recorder:
            def debug(self, message):
                levels.append(("debug", message))

            def warning(self, message):
                levels.append(("warning", message))

            def info(self, message):
                levels.append(("info", message))

        def _no_sdk(_resolved):
            raise ImportError("No module named 'opentelemetry'")

        monkeypatch.setattr(otel_tracing, "logger", _Recorder())
        monkeypatch.setattr(otel_tracing, "_build_provider", _no_sdk)

        assert otel_tracing.setup_tracing(OtelTracingConfig(service_name="no-sdk")) is False
        assert [level for level, _ in levels] == ["debug"], levels

    def test_the_caller_s_config_object_is_not_mutated(self):
        config = OtelTracingConfig(service_name="from-config")
        otel_tracing.setup_tracing(config, service_name="from-caller")
        assert config.service_name == "from-config", "setup_tracing wrote back into the caller's object"

    def test_shutdown_is_safe_to_call_twice(self):
        otel_tracing.setup_tracing(OtelTracingConfig(service_name="shutdown-test"))
        otel_tracing.shutdown()
        otel_tracing.shutdown()


@pytest.mark.skipif(not _otel_available(), reason="opentelemetry not installed")
class TestLoggerComposesItIn:
    """An app that calls logger.setup() and nothing else gets tracing."""

    def test_setup_wires_span_export(self, monkeypatch):
        calls = []
        monkeypatch.setattr(otel_tracing, "setup_tracing", lambda **kw: calls.append(kw) or True)

        from scalo.logger import setup

        setup(service_name="wired-service")
        assert calls == [{"service_name": "wired-service"}]

    def test_it_can_be_switched_off_for_a_caller_that_must_not_start_a_thread(self, monkeypatch):
        calls = []
        monkeypatch.setattr(otel_tracing, "setup_tracing", lambda **kw: calls.append(kw) or True)

        from scalo.logger import setup

        setup(otel_tracing=False)
        assert calls == []

    def test_a_failure_there_does_not_break_logging(self, monkeypatch):
        def _explode(**kwargs):
            raise RuntimeError("collector on fire")

        monkeypatch.setattr(otel_tracing, "setup_tracing", _explode)

        from scalo.logger import logger, setup

        assert setup() is logger, "logging must survive a telemetry failure"
