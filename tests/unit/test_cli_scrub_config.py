#  Project:   scalo
#  File:      tests/unit/test_cli_scrub_config.py
#  Purpose:   logging.scrub.* from the loaded config reaches a ServiceApp's logger
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""A ``logging.scrub`` section in the app's config scrubs the app's log lines.

Run against a live ``ServiceApp`` with a fake stderr, because the section sits
in a ``--config`` file or the app's env prefix, and neither is visible to the
process-wide settings that ``setup()`` falls back on.
"""

import pytest
import yaml
from common.fake_secrets import github_classic_pat
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.cli import ServiceApp, VersionInfo

GITHUB_TOKEN = github_classic_pat()
EMAIL = "someone@example.com"
LINE = f"push with {GITHUB_TOKEN} for {EMAIL}"


class _ScrubConfigApp(ServiceApp):
    """Logs one line holding a secret and an email, then exits."""

    name = "scrub-config-app"
    env_prefix = "SCRUBCFG"
    serve_observability = False

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.1.0")

    def run_service(self, config) -> None:
        from scalo.logger import logger as scalo_logger

        scalo_logger.info(LINE)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # The app's env prefix applies to the control variable, so the bare name is not read.
    monkeypatch.setenv("SCRUBCFG_LOG_ENQUEUE", "0")
    with preserved_stdlib_logging():
        yield
        logger.remove()


def _run_capturing_stderr(monkeypatch, argv: list[str]) -> str:
    stream = StreamDouble(tty=False)
    monkeypatch.setattr("sys.stderr", stream)
    with pytest.raises(SystemExit) as exc:
        _ScrubConfigApp().cli(argv)
    assert exc.value.code in (0, None), f"service exited {exc.value.code}"
    return stream.getvalue()


def _config_file(tmp_path, scrub: dict) -> str:
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"logging": {"scrub": scrub}}), encoding="utf-8", newline="\n")
    return str(path)


def test_without_a_scrub_section_both_the_secret_and_the_email_are_scrubbed(monkeypatch):
    output = _run_capturing_stderr(monkeypatch, ["run"])

    assert GITHUB_TOKEN not in output
    assert EMAIL not in output


def test_a_config_file_rule_turns_one_layer_off_and_leaves_the_others(monkeypatch, tmp_path):
    path = _config_file(tmp_path, {"pii": {"enabled": False}})

    output = _run_capturing_stderr(monkeypatch, ["run", "--config", path])

    assert EMAIL in output, "logging.scrub.pii.enabled: false did not reach the logger"
    assert GITHUB_TOKEN not in output


def test_a_config_file_can_turn_the_scrubber_off(monkeypatch, tmp_path):
    path = _config_file(tmp_path, {"enabled": False})

    output = _run_capturing_stderr(monkeypatch, ["run", "--config", path])

    assert GITHUB_TOKEN in output, output
    assert EMAIL in output


@pytest.mark.parametrize("bare", [False, 0, [], ""])
def test_a_malformed_scrub_section_stops_startup_even_when_it_is_falsy(monkeypatch, tmp_path, bare):
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"logging": {"scrub": bare}}), encoding="utf-8", newline="\n")

    stream = StreamDouble(tty=False)
    monkeypatch.setattr("sys.stderr", stream)
    with pytest.raises(SystemExit) as exc:
        _ScrubConfigApp().cli(["run", "--config", str(path)])

    assert exc.value.code == 1


def test_the_apps_env_prefix_reaches_the_scrubber(monkeypatch):
    monkeypatch.setenv("SCRUBCFG_LOGGING__SCRUB__PII__ENABLED", "false")

    output = _run_capturing_stderr(monkeypatch, ["run"])

    assert EMAIL in output, "SCRUBCFG_LOGGING__SCRUB__PII__ENABLED did not reach the logger"
    assert GITHUB_TOKEN not in output
