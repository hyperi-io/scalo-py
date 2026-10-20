# Project:   scalo
# File:      tests/unit/test_rules/test_import.py
# Purpose:   scalo.rules without the expression extra names the extra
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Importing scalo.rules with no cel package says which extra to install."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["scalo.rules", "scalo.rules._compiler", "scalo.rules._ruleset"])
def test_a_missing_cel_package_raises_the_named_import_error(module, tmp_path):
    program = f"import sys\nsys.modules['cel'] = None\nimport {module}\n"
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode != 0
    last_line = result.stderr.strip().splitlines()[-1]
    assert last_line.startswith("ImportError: CEL expression support requires the 'expression' extra"), last_line
