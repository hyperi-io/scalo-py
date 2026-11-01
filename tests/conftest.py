"""Pytest configuration and fixtures for scalo tests."""

import os
from pathlib import Path

import pytest

# The run's one ClickHouse, Kafka and OpenBao, shared by every xdist worker: tests/TESTING.md.
pytest_plugins = ["scalo.deployment.test_support.pytest_plugin"]


@pytest.fixture(autouse=True)
def _reset_scalo_env_prefix():
    """Isolate the process-global env-var and metric prefixes between tests.

    The single scalo env prefix (set via ServiceApp/set_env_prefix or the bare
    ENV_PREFIX var) and the metric prefix (set_metric_prefix / METRIC_PREFIX)
    are process-global. A CLI/app test that sets either would otherwise leak
    into later tests, making bare control-var reads or bare metric names miss.
    """
    import scalo._env_compat as _ec

    _ec._prefix_override = None
    _ec._metric_prefix_override = None
    os.environ.pop("ENV_PREFIX", None)
    os.environ.pop("METRIC_PREFIX", None)
    yield
    _ec._prefix_override = None
    _ec._metric_prefix_override = None


@pytest.fixture(scope="session", autouse=True)
def _drop_logger_sinks_at_session_end():
    """Remove every loguru sink once the session ends.

    A sink a test left on a since-closed stream would otherwise report each
    record logged at interpreter exit, OpenTelemetry's shutdown warnings
    among them, as a loguru handler error.
    """
    yield
    from loguru import logger

    logger.remove()


# Enable DEBUG logging for all tests
os.environ["LOG_LEVEL"] = "DEBUG"

# On a GitHub runner scalo's logger turns ERROR and WARNING records into ::error::
# and ::warning:: workflow commands, so a test that logs one on purpose shows up as a
# build annotation. Tests that exercise that mode set GITHUB_ACTIONS themselves.
os.environ.pop("GITHUB_ACTIONS", None)

# OTLP push is ON by default, so the suite has to switch it off explicitly or
# every backend built in a test dials a collector that is not there. A blank
# OTEL_EXPORTER_OTLP_ENDPOINT is the documented off switch, and it beats config
# -- which is the point: a test asserting that config CAN set the endpoint has to
# clear this first (see the config_endpoint_wins fixture in
# tests/unit/test_metrics_dual_export.py), or it asserts nothing.
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "")

# Load .env file for test credentials (Artifactory, database, etc.)
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Strip quotes from value
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value


@pytest.fixture(scope="session")
def kafka_config(shared_kafka) -> dict:
    """librdkafka settings for the run's Kafka, with scalo's admin defaults."""
    from scalo.kafka.config import ADMIN_DEFAULTS, merge_config

    return merge_config(dict(shared_kafka.client_config), ADMIN_DEFAULTS, verify_ssl=False)


@pytest.fixture(scope="session")
def openbao_endpoint(shared_openbao) -> tuple[str, str]:
    """The run's OpenBao address and root token."""
    return shared_openbao.address, shared_openbao.token
