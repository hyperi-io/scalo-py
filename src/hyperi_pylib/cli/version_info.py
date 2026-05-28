# Project:   hyperi-pylib
# File:      cli/version_info.py
# Purpose:   Structured version metadata for DFE services
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Version information for DFE service CLIs.

Mirrors hyperi-rustlib's cli::version::VersionInfo with a builder pattern.
Populated at build time or from package metadata.
"""

import platform
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

__all__ = [
    "VersionInfo",
]


def _get_pylib_version() -> str:
    """Get hyperi-pylib version from package metadata."""
    try:
        return pkg_version("hyperi-pylib")
    except PackageNotFoundError:
        return "unknown"


@dataclass
class VersionInfo:
    """Service version information.

    Populated at build time or from package metadata. Provides both
    short and long format output matching rustlib's VersionInfo.

    Example::

        info = VersionInfo("dfe-loader", "1.9.7")
        info = info.with_commit("abc1234").with_build_date("2026-03-04")
        print(info)
    """

    name: str
    version: str
    commit: str | None = None
    build_date: str | None = None
    python_version: str | None = None
    platform: str | None = None
    pylib_version: str = field(default_factory=_get_pylib_version)

    @classmethod
    def from_env(cls, name: str, version: str) -> "VersionInfo":
        """Create VersionInfo with auto-detected metadata from environment.

        Checks env vars: GIT_COMMIT, BUILD_COMMIT for commit hash (GIT_COMMIT takes precedence).
        Checks env vars: BUILD_DATE, BUILD_TIME for build date (BUILD_DATE takes precedence).
        Auto-detects python_version and platform from the running interpreter and system.
        """
        import os

        commit = os.getenv("GIT_COMMIT") or os.getenv("BUILD_COMMIT")
        build_date = os.getenv("BUILD_DATE") or os.getenv("BUILD_TIME")
        return cls(
            name=name,
            version=version,
            commit=commit,
            build_date=build_date,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            platform=platform.platform(),
        )

    def with_commit(self, commit: str) -> "VersionInfo":
        """Set git commit SHA."""
        self.commit = commit
        return self

    def with_build_date(self, date: str) -> "VersionInfo":
        """Set build date."""
        self.build_date = date
        return self

    def with_python_version(self, version: str | None = None) -> "VersionInfo":
        """Set Python version (auto-detects if not provided)."""
        self.python_version = version or f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        return self

    def with_platform(self, plat: str | None = None) -> "VersionInfo":
        """Set platform/target (auto-detects if not provided)."""
        self.platform = plat or platform.platform()
        return self

    def short(self) -> str:
        """Short version string: 'name version (commit)'."""
        if self.commit:
            return f"{self.name} {self.version} ({self.commit})"
        return f"{self.name} {self.version}"

    def __str__(self) -> str:
        """Multi-line version output matching rustlib format."""
        lines = [f"{self.name} {self.version}"]
        if self.commit:
            lines.append(f"  commit:  {self.commit}")
        if self.build_date:
            lines.append(f"  built:   {self.build_date}")
        if self.python_version:
            lines.append(f"  python:  {self.python_version}")
        if self.platform:
            lines.append(f"  target:  {self.platform}")
        lines.append(f"  pylib:   {self.pylib_version}")
        return "\n".join(lines)
