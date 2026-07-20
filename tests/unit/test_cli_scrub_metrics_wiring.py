#  Project:   scalo
#  File:      tests/unit/test_cli_scrub_metrics_wiring.py
#  Purpose:   ServiceApp wires scrub metrics into the logger
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""ServiceApp auto-wires the scrub layers to its metrics manager.

The parity manifest publishes six log_scrub_* metric names and states both
implementations must honour every key. Nothing emitted them: the runtime
path forced ScrubMetrics.noop(), and there was no way to hand a manager to
logger.setup() in the first place.

Asserted against a RUNNING service, because the wiring looked correct while
producing nothing.
"""

from __future__ import annotations

import pytest

from scalo.cli import ServiceApp, VersionInfo

SECRET_LINE = "token ghp_abcdefghijklmnopqrstuvwxyz0123456789 for a@b.com"


class _ScrubApp(ServiceApp):
    """Logs a line containing a secret + PII while running."""

    name = "scrub-wiring-app"
    env_prefix = "SCRUB_WIRING"
    serve_observability = False  # no port needed for this test

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.1.0")

    def run_service(self, config) -> None:
        from scalo.logger import logger

        logger.info(SECRET_LINE)
        self.scraped = self._metrics.get_metrics().decode("utf-8")


def _run(app: ServiceApp) -> None:
    with pytest.raises(SystemExit) as exc:
        app.cli(["run"])
    assert exc.value.code in (0, None), f"service exited {exc.value.code}"


class TestServiceAppEmitsScrubMetrics:
    def test_scrub_matches_are_emitted(self):
        app = _ScrubApp()
        _run(app)
        assert "log_scrub_matches_total" in app.scraped

    def test_redactions_are_emitted(self):
        app = _ScrubApp()
        _run(app)
        assert "log_scrub_redactions_total" in app.scraped

    def test_the_secret_itself_never_reaches_the_metrics(self):
        # Metric labels carry the TYPE, never the matched value.
        app = _ScrubApp()
        _run(app)
        assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in app.scraped
        assert "a@b.com" not in app.scraped


class TestInitLoggerSignature:
    def test_accepts_metrics(self):
        import inspect

        from scalo.cli.app import CommonArgs

        assert "metrics" in inspect.signature(CommonArgs.init_logger).parameters

    def test_default_still_works_without_metrics(self):
        from scalo.cli.app import CommonArgs

        # Must not raise -- the pre-metrics call on the startup path.
        CommonArgs().init_logger()
