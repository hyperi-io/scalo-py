#  Project:   scalo
#  File:      tests/unit/test_logger_default_sink.py
#  Purpose:   loguru's import-time sink never prints a traceback's local variables once scalo is imported
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""What an app logs before scalo's ``setup()`` runs goes to loguru's own stderr sink.

loguru builds that sink with ``diagnose`` on, which prints every local variable of
a logged traceback, so scalo's unhandled-exception log would carry request headers
and secrets. Each case runs in a fresh interpreter, because the sink is global.
"""

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

_SECRET = "local-secret-9d2e"

# loguru colours its own sink under CI, and a colour code inside a value would hide it from a substring check.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_UNHANDLED = f"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scalo.api import install_problem_handlers

app = FastAPI()
install_problem_handlers(app)


@app.get("/boom")
def boom():
    token = "{_SECRET}"
    raise RuntimeError("boom " + str(len(token)))


TestClient(app, raise_server_exceptions=False).get("/boom")
"""


def _run(directory: Path, code: str, **env: str) -> subprocess.CompletedProcess[str]:
    # A script file, not -c: loguru annotates locals only on frames whose source it can read.
    script = directory / "script.py"
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("LOGURU_") and not key.endswith(("AUTO_LOGGER_CONFIG", "NO_LOGGER_CONFIG"))
    }
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        env={**clean, **env},
    )
    result.stderr = _ANSI.sub("", result.stderr)
    return result


class TestDefaultSink:
    def test_an_unhandled_exception_logs_without_the_frames_locals(self, tmp_path):
        result = _run(tmp_path, _UNHANDLED)

        assert result.returncode == 0, result.stderr
        assert "Unhandled exception" in result.stderr
        assert "RuntimeError: boom 17" in result.stderr
        assert _SECRET not in result.stderr

    def test_an_explicit_loguru_diagnose_is_left_alone(self, tmp_path):
        result = _run(tmp_path, _UNHANDLED, LOGURU_DIAGNOSE="1")

        assert result.returncode == 0, result.stderr
        assert _SECRET in result.stderr

    def test_an_app_that_removed_the_sink_gets_none_back(self, tmp_path):
        result = _run(
            tmp_path,
            """
            from loguru import logger
            logger.remove()
            import scalo.logger
            logger.error("nothing should print this")
            """,
        )

        assert result.returncode == 0, result.stderr
        assert "nothing should print this" not in result.stderr
