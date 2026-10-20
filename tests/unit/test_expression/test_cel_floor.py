# Project:   scalo
# File:      tests/unit/test_expression/test_cel_floor.py
# Purpose:   The expression extra's floor is the CEL release scalo needs
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""common-expression-language 0.10.0 is the first release that imports in a clean install.

It is also built on cel-rust 0.14.5, the crate floor scalo-rs compiles against, so both
implementations parse and evaluate with the same parser. 0.6.0 to 0.9.0 fail ``import cel``
without typing_extensions installed.
"""

import importlib.metadata
import re
import tomllib
from pathlib import Path

FLOOR = (0, 10, 0)
PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_the_expression_extra_floor_is_the_release_scalo_needs():
    extras = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    requirement = next(r for r in extras["expression"] if r.startswith("common-expression-language"))
    found = re.fullmatch(r"common-expression-language>=([0-9.]+)", requirement)
    assert found, requirement
    assert _version(found.group(1)) >= FLOOR, requirement


def test_the_installed_release_meets_the_floor():
    assert _version(importlib.metadata.version("common-expression-language")) >= FLOOR
