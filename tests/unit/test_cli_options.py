#  Project:   scalo
#  File:      tests/unit/test_cli_options.py
#  Purpose:   enum_option refuses a default outside its enum
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""Option helpers in ``scalo.cli.options``."""

from enum import StrEnum

import pytest

from scalo.cli.options import HAS_TYPER, enum_option

pytestmark = pytest.mark.skipif(not HAS_TYPER, reason="needs the cli extra")


class Environment(StrEnum):
    DEV = "dev"
    PROD = "prod"


class Colour(StrEnum):
    RED = "red"


def test_a_default_from_the_enum_builds_the_option() -> None:
    option = enum_option(Environment, Environment.DEV, "--env")
    assert option.default is Environment.DEV


def test_no_default_builds_the_option() -> None:
    option = enum_option(Environment, None, "--env")
    assert option.default is None


def test_a_default_from_another_enum_is_refused() -> None:
    with pytest.raises(TypeError, match="not a member of Environment"):
        enum_option(Environment, Colour.RED, "--env")


def test_a_bare_string_default_is_refused() -> None:
    with pytest.raises(TypeError, match="not a member of Environment"):
        enum_option(Environment, "staging", "--env")
