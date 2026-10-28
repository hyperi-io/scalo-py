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

import importlib.util
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scalo import otel_tracing
from scalo.otel_tracing import OtelTracingConfig, config_from_cascade, resolve


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch):
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
        "OTEL_TRACES_EXPORTER",
        "OTEL_SDK_DISABLED",
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


def _fastapi_available() -> bool:
    return _otel_available() and importlib.util.find_spec("fastapi") is not None


def _transport(exporter: Any) -> str:
    """The OTLP transport an exporter speaks, from ``opentelemetry.exporter.otlp.proto.<transport>``."""
    return type(exporter).__module__.split(".")[4]


def _span_exporters(provider: Any) -> list[Any]:
    """Every span exporter on a provider, unwrapped from scalo's backoff gate."""
    processors = provider._active_span_processor._span_processors
    exporters = [processor.span_exporter for processor in processors]
    return [getattr(exporter, "_inner", exporter) for exporter in exporters]


class _Collector:
    """A real OTLP gRPC trace receiver on loopback, so exports cross the wire.

    With ``stall`` set, every Export call blocks until :meth:`stop`, standing in
    for a collector that accepts the connection and never answers.
    """

    def __init__(self, *, stall: bool = False) -> None:
        from concurrent import futures

        import grpc
        from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

        self.received: list[str] = []
        self.called = threading.Event()
        self._release = threading.Event()
        if not stall:
            self._release.set()
        collector = self

        class _Receiver(trace_service_pb2_grpc.TraceServiceServicer):
            def Export(self, request, context):  # noqa: N802 - name fixed by the generated servicer
                collector.called.set()
                collector._release.wait(30)
                for resource_spans in request.resource_spans:
                    for scope_spans in resource_spans.scope_spans:
                        collector.received.extend(span.name for span in scope_spans.spans)
                return trace_service_pb2.ExportTraceServiceResponse()

        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(_Receiver(), self._server)
        port = self._server.add_insecure_port("127.0.0.1:0")
        self.endpoint = f"http://127.0.0.1:{port}"
        self._server.start()

    def stop(self) -> None:
        self._release.set()
        self._server.stop(grace=None)


@pytest.fixture
def collector() -> Iterator[_Collector]:
    receiver = _Collector()
    yield receiver
    receiver.stop()


@pytest.fixture
def stalled_collector() -> Iterator[_Collector]:
    receiver = _Collector(stall=True)
    yield receiver
    receiver.stop()


def _exit_flush_config(endpoint: str) -> OtelTracingConfig:
    """Every span sampled, and a schedule so long that only the exit flush can export."""
    return OtelTracingConfig(
        endpoint=endpoint, service_name="exit-test", sample_ratio=1.0, batch_scheduled_delay_millis=600_000
    )


# Run in a child interpreter, so the flush happens on a real exit through atexit.
_EXITING_CHILD = """
import sys

from scalo import otel_tracing
from scalo.otel_tracing import OtelTracingConfig

config = OtelTracingConfig(
    endpoint=sys.argv[1], service_name="exit-test", sample_ratio=1.0, batch_scheduled_delay_millis=600_000
)
if not otel_tracing.setup_tracing(config):
    sys.exit("span export did not start")
with otel_tracing.tracer("exit-test").start_as_current_span("at-exit"):
    pass
print("span ended", flush=True)
"""


def _start_exiting_child(endpoint: str, cwd: Path) -> subprocess.Popen[str]:
    # An empty cwd, so the child's config cascade cannot load a stray .env.
    return subprocess.Popen(
        [sys.executable, "-c", _EXITING_CHILD, endpoint],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


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


class TestPerSignalEnv:
    """OTEL_EXPORTER_OTLP_TRACES_* outranks the generic form, which outranks config."""

    @pytest.mark.parametrize(
        ("env", "config", "endpoint", "protocol", "verbatim"),
        [
            # Per-signal alone takes effect, and is used as given.
            ({"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://t:4318/custom"}, {}, "http://t:4318/custom", "grpc", True),
            ({"OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf"}, {}, "http://localhost:4318", "http", False),
            # Per-signal beats generic.
            (
                {
                    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4317",
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://traces:4317",
                },
                {},
                "http://traces:4317",
                "grpc",
                True,
            ),
            (
                {"OTEL_EXPORTER_OTLP_PROTOCOL": "grpc", "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http"},
                {},
                "http://localhost:4318",
                "http",
                False,
            ),
            # Generic beats config, and is a base URL.
            (
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic:4317"},
                {"endpoint": "http://cfg:4317"},
                "http://generic:4317",
                "grpc",
                False,
            ),
            # The default port follows the resolved protocol, config-only included.
            ({"OTEL_EXPORTER_OTLP_PROTOCOL": "http"}, {}, "http://localhost:4318", "http", False),
            ({}, {"protocol": "http", "endpoint": "http://localhost:4318"}, "http://localhost:4318", "http", False),
            # An endpoint config named explicitly is not replaced by a default.
            (
                {"OTEL_EXPORTER_OTLP_PROTOCOL": "http"},
                {"endpoint": "http://cfg:9999"},
                "http://cfg:9999",
                "http",
                False,
            ),
            # An unrecognised per-signal protocol falls back rather than failing.
            ({"OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "carrier-pigeon"}, {}, "http://localhost:4317", "grpc", False),
            # A blank per-signal endpoint is the off switch for this signal.
            (
                {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": " ", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://g:4317"},
                {},
                "",
                "grpc",
                True,
            ),
        ],
    )
    def test_resolution(self, monkeypatch, env, config, endpoint, protocol, verbatim):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        resolved = resolve(OtelTracingConfig(**config))
        assert (resolved.endpoint, resolved.protocol, resolved.endpoint_verbatim) == (endpoint, protocol, verbatim)

    @pytest.mark.skipif(not _otel_available(), reason="opentelemetry not installed")
    def test_a_per_signal_http_endpoint_is_not_given_the_traces_path_twice(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://collector:4318/ingest")
        exporter = otel_tracing._build_span_exporter(resolve(OtelTracingConfig()))
        try:
            assert exporter._endpoint == "http://collector:4318/ingest"
        finally:
            exporter.shutdown()


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
class TestTheExitFlush:
    """Spans still buffered at exit reach the collector, and a stalled collector cannot hold exit open."""

    BOUND_SECONDS = otel_tracing.SHUTDOWN_TIMEOUT_MILLIS / 1000

    def test_buffered_spans_are_exported_by_shutdown(self, collector):
        assert otel_tracing.setup_tracing(_exit_flush_config(collector.endpoint)) is True
        with otel_tracing._PROVIDER.get_tracer("exit-test").start_as_current_span("buffered"):
            pass
        otel_tracing.shutdown()
        assert collector.received == ["buffered"]

    def test_a_stalled_collector_cannot_hold_shutdown_past_the_bound(self, stalled_collector):
        assert otel_tracing.setup_tracing(_exit_flush_config(stalled_collector.endpoint)) is True
        with otel_tracing._PROVIDER.get_tracer("exit-test").start_as_current_span("stalled"):
            pass

        started = time.monotonic()
        otel_tracing.shutdown()
        elapsed = time.monotonic() - started

        assert stalled_collector.called.is_set(), "shutdown never tried to flush"
        assert self.BOUND_SECONDS - 0.2 <= elapsed < self.BOUND_SECONDS + 1.0, elapsed

    def test_buffered_spans_reach_the_collector_when_the_process_exits(self, collector, tmp_path):
        child = _start_exiting_child(collector.endpoint, tmp_path)
        out, err = child.communicate(timeout=60)
        assert child.returncode == 0, err
        assert out.strip() == "span ended"
        assert collector.received == ["at-exit"], err

    def test_a_stalled_collector_cannot_hold_process_exit_past_the_bound(self, stalled_collector, tmp_path):
        child = _start_exiting_child(stalled_collector.endpoint, tmp_path)
        try:
            assert child.stdout is not None
            assert child.stdout.readline().strip() == "span ended"
            started = time.monotonic()
            _, err = child.communicate(timeout=60)
            elapsed = time.monotonic() - started
        finally:
            child.kill()

        assert child.returncode == 0, err
        assert stalled_collector.called.is_set(), f"the exit flush never reached the collector: {err}"
        assert self.BOUND_SECONDS - 0.2 <= elapsed < self.BOUND_SECONDS + 1.5, elapsed


@pytest.mark.skipif(not _otel_available(), reason="opentelemetry not installed")
class TestTheExporterMatchesTheProtocol:
    """The exporter built must speak the protocol scalo reports, or every export to the collector fails."""

    @pytest.mark.parametrize(
        ("env_protocol", "config_protocol", "expected"),
        [
            (None, "grpc", "grpc"),
            (None, "http", "http"),
            ("grpc", "http", "grpc"),
            ("http/protobuf", "grpc", "http"),
        ],
    )
    def test_the_span_exporter_speaks_the_resolved_protocol(self, monkeypatch, env_protocol, config_protocol, expected):
        if env_protocol is not None:
            monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", env_protocol)
        resolved = resolve(OtelTracingConfig(protocol=config_protocol))
        exporter = otel_tracing._build_span_exporter(resolved)
        try:
            assert resolved.protocol == expected
            assert _transport(exporter) == expected
        finally:
            exporter.shutdown()

    def test_grpc_dials_the_endpoint_as_given(self):
        exporter = otel_tracing._build_span_exporter(
            OtelTracingConfig(endpoint="http://collector:4317", protocol="grpc")
        )
        try:
            assert exporter._endpoint == "collector:4317"
        finally:
            exporter.shutdown()

    def test_http_posts_to_the_traces_path(self):
        exporter = otel_tracing._build_span_exporter(
            OtelTracingConfig(endpoint="http://collector:4318", protocol="http")
        )
        try:
            assert exporter._endpoint == "http://collector:4318/v1/traces"
        finally:
            exporter.shutdown()

    def test_setup_installs_only_a_grpc_exporter_when_just_the_endpoint_is_set(self, monkeypatch):
        """The deployment shape in scalo-py#79: the endpoint env var set, the protocol left at its default."""
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
        assert otel_tracing.setup_tracing(OtelTracingConfig(service_name="grpc-test")) is True
        assert [_transport(e) for e in _span_exporters(otel_tracing._PROVIDER)] == ["grpc"]

    def test_spans_reach_a_grpc_collector(self, collector):
        config = OtelTracingConfig(endpoint=collector.endpoint, service_name="wire-test", sample_ratio=1.0)
        assert otel_tracing.setup_tracing(config) is True
        with otel_tracing._PROVIDER.get_tracer("wire-test").start_as_current_span("over-grpc"):
            pass
        assert otel_tracing._PROVIDER.force_flush()
        assert collector.received == ["over-grpc"]

    @pytest.mark.parametrize("env_protocol", [None, "grpc", "http/protobuf"])
    def test_spans_and_metrics_agree_on_the_protocol(self, monkeypatch, env_protocol):
        from scalo.metrics.opentelemetry_backend import _create_otlp_exporter, resolve_otel_config

        if env_protocol is not None:
            monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", env_protocol)
        span_resolved = resolve(OtelTracingConfig())
        metric_resolved = resolve_otel_config({})
        assert span_resolved.protocol == metric_resolved.protocol

        span_exporter = otel_tracing._build_span_exporter(span_resolved)
        metric_exporter = _create_otlp_exporter(metric_resolved.protocol, metric_resolved.endpoint, 10_000, {})
        try:
            assert _transport(span_exporter) == _transport(metric_exporter) == span_resolved.protocol
        finally:
            span_exporter.shutdown()
            metric_exporter.shutdown()


@pytest.mark.skipif(not _fastapi_available(), reason="fastapi not installed")
class TestBesideFastApi:
    """fastapi 0.142+ adds http/protobuf exporters from ``OTEL_EXPORTER_OTLP_ENDPOINT`` unless told not to."""

    @staticmethod
    def _start(telemetry: dict[str, Any]) -> list[Any]:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # A zero ratio records no spans, so neither processor dials anything on shutdown.
        assert otel_tracing.setup_tracing(OtelTracingConfig(service_name="fastapi-test", sample_ratio=0.0)) is True
        provider = otel_tracing._PROVIDER
        # The OTel global tracer provider can be set once per process, so FastAPI is handed scalo's directly.
        app = FastAPI(telemetry={"tracer_provider": provider, "metrics": False, "logs": False, **telemetry})
        with TestClient(app):
            pass
        return _span_exporters(provider)

    def test_its_default_adds_an_http_exporter_beside_scalo_s_grpc_one(self, monkeypatch):
        """The cause of scalo-py#79: the collector's gRPC port resets every export from the HTTP one."""
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
        assert sorted(_transport(e) for e in self._start({})) == ["grpc", "http"]

    def test_the_documented_setting_leaves_only_scalo_s_grpc_exporter(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")
        assert [_transport(e) for e in self._start({"auto_configure": False})] == ["grpc"]


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
