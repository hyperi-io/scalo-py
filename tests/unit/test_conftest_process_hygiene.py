#  Project:   scalo
#  File:      tests/unit/test_conftest_process_hygiene.py
#  Purpose:   Prove a test session leaves processes it did not start alone
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A test session must never kill a process it did not start.

The suite runs on shared hosts. A session-wide sweep that kills by command-line
pattern reaches every process on the host whose command line matches, whoever
owns it. This runs a nested pytest session against the real ``tests/conftest.py``
while a decoy is alive whose command line carries every pattern such a sweep
used, then asserts the decoy survived.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve().relative_to(REPO_ROOT)

# One command line that matches the TEST_*, minikube, kubectl and helm kill-by-name patterns.
DECOY_ARGV_MARKER = (
    "TEST_HELM TEST_K8S TEST_DOCKER TEST_MINIKUBE minikube ssh docker login kubectl helm-scalo helm install scalo"
)


def test_nested_session_target():
    """Give the nested session one passing test to run."""


def test_session_leaves_a_same_named_process_it_did_not_start(tmp_path):
    decoy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", DECOY_ARGV_MARKER])
    try:
        nested = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"{THIS_FILE.as_posix()}::test_nested_session_target",
                "-p",
                "no:cacheprovider",
                "-o",
                "log_cli=false",
                f"--log-file={tmp_path / 'nested.log'}",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        assert nested.returncode == 0, nested.stdout + nested.stderr
        assert decoy.poll() is None, f"the test session killed a process it did not start (exit {decoy.returncode})"
    finally:
        decoy.kill()
        decoy.wait(timeout=10)
