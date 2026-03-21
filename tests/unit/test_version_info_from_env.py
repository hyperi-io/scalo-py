# Project:   hyperi-pylib
# File:      tests/unit/test_version_info_from_env.py
# Purpose:   Tests for VersionInfo.from_env() classmethod
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for VersionInfo.from_env() auto-detection classmethod."""

import platform
import sys

import pytest

from hyperi_pylib.cli.version_info import VersionInfo


def test_from_env_with_git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """GIT_COMMIT env var is used as commit hash."""
    monkeypatch.setenv("GIT_COMMIT", "deadbeef")
    monkeypatch.delenv("BUILD_COMMIT", raising=False)

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.commit == "deadbeef"


def test_from_env_build_commit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUILD_COMMIT is used when GIT_COMMIT is absent."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setenv("BUILD_COMMIT", "cafebabe")

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.commit == "cafebabe"


def test_from_env_git_commit_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """GIT_COMMIT takes precedence over BUILD_COMMIT when both are set."""
    monkeypatch.setenv("GIT_COMMIT", "primary123")
    monkeypatch.setenv("BUILD_COMMIT", "fallback456")

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.commit == "primary123"


def test_from_env_with_build_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUILD_DATE env var is used as build date."""
    monkeypatch.setenv("BUILD_DATE", "2026-03-21")
    monkeypatch.delenv("BUILD_TIME", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_COMMIT", raising=False)

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.build_date == "2026-03-21"


def test_from_env_build_time_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUILD_TIME is used when BUILD_DATE is absent."""
    monkeypatch.delenv("BUILD_DATE", raising=False)
    monkeypatch.setenv("BUILD_TIME", "2026-03-21T10:00:00Z")
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_COMMIT", raising=False)

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.build_date == "2026-03-21T10:00:00Z"


def test_from_env_no_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Commit and build_date are None when no env vars are set."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_DATE", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.commit is None
    assert info.build_date is None


def test_from_env_auto_detects_python_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """python_version is populated from the running interpreter."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_DATE", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)

    info = VersionInfo.from_env("my-service", "1.2.3")

    expected = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    assert info.python_version == expected


def test_from_env_auto_detects_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """platform field is populated from the running system."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_DATE", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)

    info = VersionInfo.from_env("my-service", "1.2.3")

    assert info.platform == platform.platform()


def test_from_env_preserves_name_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """name and version are passed through unchanged."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_DATE", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)

    info = VersionInfo.from_env("dfe-loader", "9.8.7")

    assert info.name == "dfe-loader"
    assert info.version == "9.8.7"
