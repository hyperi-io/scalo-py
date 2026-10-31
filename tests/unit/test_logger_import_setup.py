#  Project:   scalo
#  File:      tests/unit/test_logger_import_setup.py
#  Purpose:   Importing scalo.logger installs scalo's sinks only when AUTO_LOGGER_CONFIG asks
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""What ``import scalo.logger`` does to the host's logging, as logging.md states it.

Each case runs in a fresh interpreter. ``LOG_FORMAT=json`` tells the two sinks apart:
scalo's writes a JSON line, and loguru's own default ignores the variable.
"""

import json
import os
import subprocess
import sys

import pytest

_MARKER = "import-setup-marker"

_SCRIPT = f"""
import scalo.logger
from loguru import logger

logger.info("{_MARKER}")
logger.complete()
"""

_CONTROL_SUFFIXES = ("AUTO_LOGGER_CONFIG", "NO_LOGGER_CONFIG", "LOG_FORMAT", "LOG_LEVEL", "ENV_PREFIX")


def _logged_line(tmp_path, **env: str) -> str:
    clean = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("LOGURU_") and not key.endswith(_CONTROL_SUFFIXES)
    }
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        env={**clean, "LOG_FORMAT": "json", "LOG_ENQUEUE": "0", **env},
    )
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stderr.splitlines() if _MARKER in line]
    assert len(lines) == 1, result.stderr
    return lines[0]


def _from_scalos_sink(line: str) -> bool:
    try:
        return json.loads(line).get("message") == _MARKER
    except ValueError:
        return False


@pytest.mark.parametrize(
    ("env", "scalo_sink"),
    [
        ({}, False),
        ({"AUTO_LOGGER_CONFIG": "1"}, True),
        ({"AUTO_LOGGER_CONFIG": "1", "NO_LOGGER_CONFIG": "1"}, False),
    ],
    ids=["plain-import", "auto-logger-config", "no-logger-config-vetoes"],
)
def test_import_installs_scalos_sink_only_when_asked(tmp_path, env, scalo_sink):
    assert _from_scalos_sink(_logged_line(tmp_path, **env)) is scalo_sink
