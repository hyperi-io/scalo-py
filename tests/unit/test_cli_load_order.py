#  Project:   scalo
#  File:      tests/unit/test_cli_load_order.py
#  Purpose:   Config loads before the logger, so the cascade can configure it
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""ServiceApp lifecycle ordering.

The logger's level, format and span exporter all come from the config cascade,
so building the logger before loading config leaves every one of them reachable
only from a flag or an env var. These assert the order against a RUNNING app
rather than by reading the source, because the wiring looked right while the
cascade had no effect.

Mirrors scalo-rs ``tests/logger_cascade_level.rs``.
"""

from __future__ import annotations

import pytest
import yaml

from scalo.cli import ServiceApp, VersionInfo


class _OrderApp(ServiceApp):
    """Records the lifecycle order and the level the logger ended up with."""

    name = "load-order-app"
    env_prefix = "LOAD_ORDER"
    serve_observability = False

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.1.0")

    def run_service(self, config) -> None:
        self.seen_config = config
        self.console_levels = _console_sink_levels()


def _console_sink_levels() -> list[int]:
    """The minimum level of every sink loguru currently has installed."""
    from scalo.logger import logger

    return [handler.levelno for handler in logger._core.handlers.values()]


def _run(app: ServiceApp, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        app.cli(argv)
    assert exc.value.code in (0, None), f"service exited {exc.value.code}"


@pytest.fixture
def settings_file(tmp_path):
    def _write(payload: dict) -> str:
        path = tmp_path / "settings.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8", newline="\n")
        return str(path)

    return _write


@pytest.fixture(autouse=True)
def _clear_log_env(monkeypatch):
    """The CLI exports LOG_LEVEL, and conftest sets it -- start from neither."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)


class TestConfigReachesTheLogger:
    def test_config_file_sets_the_log_level(self, settings_file):
        """The whole point of the ordering: settings.yaml can set the level."""
        path = settings_file({"logging": {"level": "ERROR"}})
        app = _OrderApp()
        _run(app, ["run", "--config", path])

        assert app.console_levels, "no sink was installed at all"
        assert min(app.console_levels) == 40, f"expected ERROR (40), got {app.console_levels}"

    def test_the_flag_still_beats_the_config_file(self, settings_file):
        path = settings_file({"logging": {"level": "ERROR"}})
        app = _OrderApp()
        _run(app, ["run", "--config", path, "--log-level", "warning"])

        assert min(app.console_levels) == 30, f"expected WARNING (30), got {app.console_levels}"

    def test_verbose_beats_the_config_file(self, settings_file):
        path = settings_file({"logging": {"level": "ERROR"}})
        app = _OrderApp()
        _run(app, ["run", "--config", path, "--verbose"])

        assert min(app.console_levels) == 10, f"expected DEBUG (10), got {app.console_levels}"

    def test_log_level_env_beats_the_config_file(self, settings_file, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
        path = settings_file({"logging": {"level": "ERROR"}})
        app = _OrderApp()
        _run(app, ["run", "--config", path])

        assert min(app.console_levels) == 50, f"expected CRITICAL (50), got {app.console_levels}"

    def test_nothing_configured_lands_on_info(self):
        app = _OrderApp()
        _run(app, ["run"])

        assert min(app.console_levels) == 20, f"expected INFO (20), got {app.console_levels}"


class TestConfigCheckReportsTheCascade:
    """config-check PRINTS the resolved level, so it must resolve it, not guess."""

    def test_the_printed_level_comes_from_the_config_file(self, settings_file, capsys):
        path = settings_file({"logging": {"level": "ERROR", "format": "json"}})
        app = _OrderApp()
        with pytest.raises(SystemExit) as exc:
            app.cli(["config-check", "--config", path])
        assert exc.value.code in (0, None)

        summary = capsys.readouterr().err
        assert "log_level        ERROR" in summary, summary
        assert "log_format       json" in summary, summary

    def test_the_printed_level_honours_the_flag(self, settings_file, capsys):
        path = settings_file({"logging": {"level": "ERROR"}})
        app = _OrderApp()
        with pytest.raises(SystemExit) as exc:
            app.cli(["config-check", "--config", path, "--log-level", "debug"])
        assert exc.value.code in (0, None)

        assert "log_level        DEBUG" in capsys.readouterr().err
