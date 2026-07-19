#  Project:   scalo
#  File:      tests/unit/test_health_observability.py
#  Purpose:   Tests for the dedicated observability listener
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the observability port (scalo-py#5).

The defect these guard: ServiceApp advertised --metrics-addr / METRICS_ADDR
and logged the address, but nothing ever bound it, so Prometheus scrapes and
kubelet probes aimed at that port got connection-refused.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from scalo.health import (
    HealthManager,
    ObservabilityServer,
    parse_addr,
    serve_observability,
)

LOCAL = "127.0.0.1:0"


def _get(port: int, path: str) -> tuple[int, dict | bytes, str]:
    """GET a path, returning (status, parsed-or-raw body, content type)."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        resp = urllib.request.urlopen(url, timeout=5)  # noqa: S310 -- fixed http:// loopback
        status, raw, ctype = resp.status, resp.read(), resp.headers["Content-Type"]
    except urllib.error.HTTPError as exc:
        status, raw, ctype = exc.code, exc.read(), exc.headers["Content-Type"]
    if ctype and ctype.startswith("application/json"):
        return status, json.loads(raw), ctype
    return status, raw, ctype


@pytest.fixture
def server():
    """A started observability server on an ephemeral port."""
    health = HealthManager()
    srv = serve_observability(health, None, LOCAL)
    yield srv, health, srv.bound_address[1]
    srv.stop()


class TestParseAddr:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.0.0.0:9090", ("0.0.0.0", 9090)),
            ("127.0.0.1:8080", ("127.0.0.1", 8080)),
            (":9090", ("0.0.0.0", 9090)),
            ("0.0.0.0:0", ("0.0.0.0", 0)),
            ("localhost", ("localhost", 9090)),
            ("[::]:9090", ("::", 9090)),
            ("[::1]:8080", ("::1", 8080)),
            ("", ("0.0.0.0", 9090)),
        ],
    )
    def test_parses(self, raw: str, expected: tuple[str, int]):
        assert parse_addr(raw) == expected

    def test_rejects_non_numeric_port(self):
        with pytest.raises(ValueError, match="invalid port"):
            parse_addr("0.0.0.0:http")

    def test_rejects_malformed_ipv6(self):
        with pytest.raises(ValueError, match="malformed IPv6"):
            parse_addr("[::9090")


class TestProbeSemantics:
    def test_liveness_alive_before_ready(self, server):
        _, _, port = server
        status, body, ctype = _get(port, "/healthz")
        assert status == 200
        assert body["status"] == "alive"
        assert ctype.startswith("application/json")

    def test_readiness_503_until_set_ready(self, server):
        _, health, port = server
        assert _get(port, "/readyz")[0] == 503
        health.set_ready()
        status, body, _ = _get(port, "/readyz")
        assert status == 200
        assert body["status"] == "ready"

    def test_startup_503_until_set_started(self, server):
        _, health, port = server
        assert _get(port, "/health/startup")[0] == 503
        health.set_started()
        assert _get(port, "/health/startup")[0] == 200

    def test_failing_ready_check_keeps_503(self, server):
        _, health, port = server
        health.set_ready()
        health.register_ready_check("db", lambda: False)
        status, body, _ = _get(port, "/readyz")
        assert status == 503
        assert body["checks"]["db"] is False

    def test_raising_check_is_treated_as_failure(self, server):
        _, health, port = server
        health.set_ready()

        def boom() -> bool:
            raise RuntimeError("db down")

        health.register_ready_check("db", boom)
        assert _get(port, "/readyz")[0] == 503

    def test_hung_check_times_out_rather_than_pinning_the_handler(self, server):
        # The probe must answer within the per-check budget. Serving these
        # off the SYNC response path would not enforce the timeout at all,
        # and a hung check would hold the handler thread indefinitely while
        # the kubelet kept retrying.
        _, health, port = server
        health.set_ready()
        health.register_ready_check("hung", lambda: time.sleep(30) or True, per_check_timeout=0.5)

        started = time.monotonic()
        status, body, _ = _get(port, "/readyz")
        elapsed = time.monotonic() - started

        assert status == 503
        assert body["checks"]["hung"] is False
        assert elapsed < 10, f"probe took {elapsed:.1f}s -- timeout not enforced"

    def test_server_still_answers_after_a_hung_check(self, server):
        _, health, port = server
        health.register_ready_check("hung", lambda: time.sleep(30) or True, per_check_timeout=0.5)
        _get(port, "/readyz")
        # Liveness is unaffected by a stuck readiness check.
        assert _get(port, "/healthz")[0] == 200


class TestCanonicalPathsAndAliases:
    @pytest.mark.parametrize("path", ["/healthz", "/health/live"])
    def test_liveness_paths(self, server, path: str):
        _, _, port = server
        assert _get(port, path)[0] == 200

    @pytest.mark.parametrize("path", ["/readyz", "/health/ready"])
    def test_readiness_paths(self, server, path: str):
        _, health, port = server
        health.set_ready()
        assert _get(port, path)[0] == 200

    def test_trailing_slash_and_query_tolerated(self, server):
        _, _, port = server
        assert _get(port, "/healthz/")[0] == 200
        assert _get(port, "/healthz?verbose=1")[0] == 200

    def test_unknown_path_404s(self, server):
        _, _, port = server
        assert _get(port, "/nope")[0] == 404


class TestMetricsEndpoint:
    def test_404_when_no_metrics_manager(self, server):
        _, _, port = server
        assert _get(port, "/metrics")[0] == 404

    def test_serves_prometheus_text(self):
        metrics = pytest.importorskip("scalo.metrics")
        mgr = metrics.create_metrics("obs_test", backend="prometheus")
        mgr.counter("obs_widgets_total", "test counter").inc()
        srv = serve_observability(HealthManager(), mgr, LOCAL)
        try:
            status, raw, ctype = _get(srv.bound_address[1], "/metrics")
            assert status == 200
            assert "text/plain" in ctype
            assert b"obs_widgets_total" in raw
        finally:
            srv.stop()


class TestLifecycle:
    def test_start_is_idempotent(self):
        srv = ObservabilityServer(HealthManager(), None, LOCAL)
        try:
            srv.start()
            first = srv.bound_address
            srv.start()
            assert srv.bound_address == first
        finally:
            srv.stop()

    def test_stop_is_idempotent(self):
        srv = serve_observability(HealthManager(), None, LOCAL)
        srv.stop()
        srv.stop()
        assert not srv.is_running
        assert srv.bound_address is None

    def test_context_manager_releases_port(self):
        with ObservabilityServer(HealthManager(), None, LOCAL) as srv:
            port = srv.bound_address[1]
            assert _get(port, "/healthz")[0] == 200
        assert not srv.is_running
        # Port is free again -- rebinding it explicitly must succeed.
        again = ObservabilityServer(HealthManager(), None, f"127.0.0.1:{port}")
        again.start()
        again.stop()

    def test_bind_failure_raises_rather_than_going_quiet(self):
        # A service that cannot open its observability port must say so.
        # Swallowing this is precisely the defect scalo-py#5 is about.
        first = serve_observability(HealthManager(), None, LOCAL)
        port = first.bound_address[1]
        try:
            with pytest.raises(OSError):
                serve_observability(HealthManager(), None, f"127.0.0.1:{port}")
        finally:
            first.stop()
