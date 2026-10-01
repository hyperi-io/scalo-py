#  Project:   scalo
#  File:      tests/common/log_capture.py
#  Purpose:   Stream double and environment isolation for tests that call logger setup()
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Helpers for tests that run the real ``setup()`` against a fake stderr.

``setup()`` reads the format and colour selectors from the environment,
switches to CI output under any CI marker, and rewires stdlib logging, so a
test that calls it clears the first two and puts the third back afterwards.
"""

import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager

# Environment variables that change what setup() writes.
LOGGER_ENV_VARS = (
    "LOG_FORMAT",
    "LOG_COLOR",
    "NO_COLOR",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "CI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "CIRCLECI",
    "TRAVIS",
)

# Stdlib loggers setup() strips of their own handlers.
SELF_HANDLING_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class StreamDouble(io.StringIO):
    """A stderr stand-in that answers ``isatty()`` as told."""

    def __init__(self, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@contextmanager
def preserved_stdlib_logging() -> Iterator[None]:
    """Restore the root and uvicorn loggers' handlers, level and propagation on exit."""
    root = logging.getLogger()
    saved_root = (list(root.handlers), root.level)
    saved = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).propagate)
        for name in SELF_HANDLING_LOGGERS
    }
    try:
        yield
    finally:
        root.handlers[:] = saved_root[0]
        root.setLevel(saved_root[1])
        for name, (handlers, propagate) in saved.items():
            logging.getLogger(name).handlers[:] = handlers
            logging.getLogger(name).propagate = propagate
