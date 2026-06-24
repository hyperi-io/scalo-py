"""Tests for scalo._env_compat -- bare-by-default, app-configurable env prefix.

The library hard-codes no brand into env vars: names are bare by default and
gain a single app-supplied prefix (``DFE`` -> ``DFE_DEBUG``). There is no
legacy ``HYPERI_*`` fallback.
"""

from __future__ import annotations

import pytest

import scalo._env_compat as ec
from scalo._env_compat import control_flag, control_var, env_prefix, set_control_var, set_env_prefix


@pytest.fixture(autouse=True)
def _reset_prefix(monkeypatch):
    """Reset the programmatic prefix override and the bare ENV_PREFIX var."""
    monkeypatch.setattr(ec, "_prefix_override", None)
    monkeypatch.delenv("ENV_PREFIX", raising=False)
    yield
    monkeypatch.setattr(ec, "_prefix_override", None)


def test_bare_by_default(monkeypatch):
    monkeypatch.setenv("DEBUG", "1")
    assert env_prefix() == ""
    assert control_var("DEBUG") == "1"


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("METRICS_BACKEND", raising=False)
    assert control_var("METRICS_BACKEND") is None
    assert control_var("METRICS_BACKEND", default="otel") == "otel"


def test_app_prefix_via_set_env_prefix(monkeypatch):
    set_env_prefix("DFE")
    monkeypatch.setenv("DFE_DEBUG", "1")
    monkeypatch.setenv("DEBUG", "should-be-ignored")
    assert env_prefix() == "DFE"
    # Prefixed name wins; the bare name is NOT consulted once a prefix is set.
    assert control_var("DEBUG") == "1"


def test_app_prefix_via_bare_env_var(monkeypatch):
    monkeypatch.setenv("ENV_PREFIX", "DFE")
    monkeypatch.setenv("DFE_LOG_ENQUEUE", "0")
    assert env_prefix() == "DFE"
    assert control_var("LOG_ENQUEUE") == "0"


def test_trailing_underscore_stripped(monkeypatch):
    set_env_prefix("DFE_")
    monkeypatch.setenv("DFE_DEBUG", "1")
    assert control_var("DEBUG") == "1"


def test_legacy_hyperi_is_not_read(monkeypatch):
    # HYPERI_* is REMOVED -- no fallback, no deprecation.
    monkeypatch.setenv("HYPERI_DEBUG", "1")
    monkeypatch.setenv("HYPERI_LIB_DEBUG", "1")
    monkeypatch.delenv("DEBUG", raising=False)
    assert control_var("DEBUG") is None


def test_control_flag(monkeypatch):
    monkeypatch.setenv("AUTO_DETECT", "yes")
    assert control_flag("AUTO_DETECT") is True
    monkeypatch.setenv("AUTO_DETECT", "0")
    assert control_flag("AUTO_DETECT") is False
    monkeypatch.delenv("AUTO_DETECT", raising=False)
    assert control_flag("AUTO_DETECT", default=True) is True


def test_set_control_var_bare_and_prefixed(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    set_control_var("DEBUG", "1")
    assert control_var("DEBUG") == "1"

    set_env_prefix("DFE")
    set_control_var("DEBUG", "2")
    assert control_var("DEBUG") == "2"
