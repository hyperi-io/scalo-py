#  Project:   scalo
#  File:      tests/unit/test_cli_settings_adoption.py
#  Purpose:   Code that reads the module-level settings sees a ServiceApp's prefix and --config file
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""The version check, span export, the expression profile and the Kafka health
thresholds read the module-level ``settings``. A ``ServiceApp`` loads its config
under its own ``env_prefix`` and ``--config`` file, so these run a live app and
read each of the four from inside ``run_service``.
"""

import pytest
import yaml

from scalo.cli import ServiceApp, VersionInfo
from scalo.config import ConfigReloader, adopt_config, get_config, settings
from scalo.expression import profile as expression_profile

PREFIX = "ADOPTPFX"


class _SettingsApp(ServiceApp):
    """Reads the four settings consumers while running."""

    name = "settings-adoption-app"
    env_prefix = PREFIX
    serve_observability = False

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.1.0")

    def run_service(self, config) -> None:
        from scalo.kafka.health import _get_health_config
        from scalo.otel_tracing import config_from_cascade
        from scalo.version_check.checker import VersionCheckConfig

        self.seen = {
            "settings_is_config": config is settings,
            "allow_regex": expression_profile.cascade_profile().allow_regex,
            "sample_ratio": config_from_cascade().sample_ratio,
            "api_url": VersionCheckConfig().api_url,
            "lag_threshold": _get_health_config()["lag_threshold"],
        }


DEFAULTS = {"allow_regex": False, "sample_ratio": 0.05, "api_url": None, "lag_threshold": 10000}


@pytest.fixture(autouse=True)
def _fresh_expression_latch():
    """The profile is kept for the life of the process once read, so clear it around each test."""
    expression_profile._LATCH.profile = None
    yield
    expression_profile._LATCH.profile = None


def _run(argv: list[str]) -> dict:
    app = _SettingsApp()
    with pytest.raises(SystemExit) as exc:
        app.cli(argv)
    assert exc.value.code in (0, None), f"service exited {exc.value.code}"
    return app.seen


def test_nothing_set_reads_the_defaults():
    seen = _run(["run"])

    assert {key: seen[key] for key in DEFAULTS} == DEFAULTS
    assert seen["settings_is_config"]


def test_a_config_file_reaches_all_four(tmp_path):
    path = tmp_path / "app.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "expression": {"allow_regex": True},
                "otel_tracing": {"sample_ratio": 0.5},
                "version_check": {"api_url": "https://from-file.invalid/check"},
                "kafka": {"health": {"lag_threshold": 777}},
            }
        ),
        encoding="utf-8",
        newline="\n",
    )

    seen = _run(["run", "--config", str(path)])

    assert seen["allow_regex"] is True
    assert seen["sample_ratio"] == 0.5
    assert seen["api_url"] == "https://from-file.invalid/check"
    assert seen["lag_threshold"] == 777


def test_the_apps_env_prefix_reaches_all_four(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}_EXPRESSION__ALLOW_REGEX", "true")
    monkeypatch.setenv(f"{PREFIX}_OTEL_TRACING__SAMPLE_RATIO", "0.25")
    monkeypatch.setenv(f"{PREFIX}_VERSION_CHECK__API_URL", "https://from-env.invalid/check")
    monkeypatch.setenv(f"{PREFIX}_KAFKA__HEALTH__LAG_THRESHOLD", "555")

    seen = _run(["run"])

    assert seen["allow_regex"] is True
    assert seen["sample_ratio"] == 0.25
    assert seen["api_url"] == "https://from-env.invalid/check"
    assert seen["lag_threshold"] == 555


def test_bare_env_keys_no_longer_reach_an_app_with_a_prefix(monkeypatch):
    monkeypatch.setenv("EXPRESSION__ALLOW_REGEX", "true")
    monkeypatch.setenv("OTEL_TRACING__SAMPLE_RATIO", "0.25")
    monkeypatch.setenv("VERSION_CHECK__API_URL", "https://bare.invalid/check")
    monkeypatch.setenv("KAFKA__HEALTH__LAG_THRESHOLD", "555")

    seen = _run(["run"])

    assert {key: seen[key] for key in DEFAULTS} == DEFAULTS


def test_adopt_config_keeps_the_identity_of_settings():
    before = settings
    adopted = adopt_config(get_config(env_prefix=PREFIX, load_dotenv=False))

    assert adopted is before


def test_a_reload_keeps_the_adopted_prefix(monkeypatch):
    adopt_config(get_config(env_prefix=PREFIX, load_dotenv=False))
    assert settings.get("kafka.health.lag_threshold") is None
    monkeypatch.setenv(f"{PREFIX}_KAFKA__HEALTH__LAG_THRESHOLD", "321")
    monkeypatch.setenv("KAFKA__HEALTH__LAG_THRESHOLD", "999")

    assert ConfigReloader().reload_now()

    assert settings.get("kafka.health.lag_threshold") == 321
