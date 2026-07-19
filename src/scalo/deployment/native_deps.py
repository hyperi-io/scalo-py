# Project:   scalo
# File:      deployment/native_deps.py
# Purpose:   Runtime native dependency declarations for container images
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Runtime native dependency contracts -- mirrors rustlib's
``hyperi_rustlib::deployment::native_deps``.

For Python apps, the equivalent of rustlib's ``for_rustlib_features`` is
``for_pylib_extras`` -- pass the list of pylib optional extras the app uses,
get back the runtime APT packages and any custom repos needed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .registry import DEFAULT_DISTRO_CODENAME


def libgit2_runtime_package(codename: str) -> str:
    """Runtime libgit2 package name for a Debian/Ubuntu suite.

    Trixie ships ``libgit2-1.9``; older suites ship ``libgit2-1.7``. There is
    no virtual provider to paper over the difference -- soname-versioned
    packages do not alias, because different ABI versions are genuinely
    different libraries. Verified by building on ``debian:trixie-slim``.
    """
    return "libgit2-1.9" if codename == "trixie" else "libgit2-1.7"


class AptRepoContract(BaseModel):
    """A custom APT repository (e.g., Confluent for librdkafka)."""

    model_config = ConfigDict(extra="forbid")

    key_url: str
    """GPG key URL for the repo."""

    keyring: str
    """Local keyring file path (e.g., ``/usr/share/keyrings/confluent-clients.gpg``)."""

    url: str
    """Repository base URL (e.g., ``https://packages.confluent.io/clients/deb``)."""

    codename: str = ""
    """Distribution codename (e.g., ``noble``, ``bookworm``).

    If empty, derived from the base image at generation time.
    """

    packages: list[str] = Field(default_factory=list)
    """APT packages to install from this specific repo."""


class NativeDepsContract(BaseModel):
    """Runtime native dependencies for a container image.

    Populate via ``NativeDepsContract.for_pylib_extras`` from the list of
    ``pyproject.toml`` extras the app uses, or via ``for_rustlib_features``
    for polyglot apps that re-bind a Rust core.
    """

    model_config = ConfigDict(extra="forbid")

    apt_repos: list[AptRepoContract] = Field(default_factory=list)
    """Custom APT repositories to add before installing packages."""

    apt_packages: list[str] = Field(default_factory=list)
    """APT packages to install from default repos."""

    distro_codename: str = DEFAULT_DISTRO_CODENAME
    """Base-image distro suite the package names were selected for.

    Stated explicitly rather than sniffed from the base-image string, and
    recorded in the emitted contract so CI can audit which suite an image
    targets. Drives soname-versioned package names (e.g. libgit2).
    """

    def is_empty(self) -> bool:
        """True if there are no native deps to install."""
        return not self.apt_repos and not self.apt_packages

    @classmethod
    def for_pylib_extras(
        cls,
        extras: list[str],
        base_image: str,
        *,
        distro_codename: str = DEFAULT_DISTRO_CODENAME,
    ) -> NativeDepsContract:
        """Build runtime native deps from a list of scalo optional extras.

        Pass the same extra strings used in ``pyproject.toml`` (e.g.
        ``"kafka"``, ``"secrets-azure"``). Maps to the system packages that the
        wheel's transitive C extensions need at runtime.

        ``distro_codename`` names the base-image suite the packages are
        selected for; ``base_image`` only picks the Confluent APT suite (see
        :func:`_confluent_suite_codename`).
        """
        codename = _confluent_suite_codename(base_image)
        apt_repos: list[AptRepoContract] = []
        packages: list[str] = []
        seen: set[str] = set()

        def add(pkg: str) -> None:
            if pkg not in seen:
                seen.add(pkg)
                packages.append(pkg)

        # Kafka (confluent-kafka wheel dynamically links librdkafka)
        if "kafka" in extras:
            apt_repos.append(_confluent_repo(codename))
            add("libssl3")
            add("zlib1g")

        # OpenTelemetry / HTTP both need TLS
        if "opentelemetry" in extras or "http" in extras:
            add("libssl3")
            add("zlib1g")

        # Cloud secrets backends -- boto3/azure/gcp wheels need TLS
        if any(e.startswith("secrets") for e in extras):
            add("libssl3")
            add("zlib1g")

        return cls(apt_repos=apt_repos, apt_packages=packages, distro_codename=distro_codename)

    @classmethod
    def for_rustlib_features(
        cls,
        features: list[str],
        base_image: str,
        *,
        distro_codename: str = DEFAULT_DISTRO_CODENAME,
    ) -> NativeDepsContract:
        """Build runtime native deps from a list of hyperi-rustlib feature flags.

        Mirrors rustlib's ``NativeDepsContract::for_rustlib_features`` for
        polyglot apps that re-bind Rust cores. Feature strings match Cargo
        feature names exactly.

        ``distro_codename`` selects soname-versioned package names (libgit2);
        ``base_image`` only picks the Confluent APT suite.
        """
        codename = _confluent_suite_codename(base_image)
        apt_repos: list[AptRepoContract] = []
        packages: list[str] = []
        seen: set[str] = set()

        def add(pkg: str) -> None:
            if pkg not in seen:
                seen.add(pkg)
                packages.append(pkg)

        needs_kafka = any(f == "transport-kafka" or f.startswith("dlq-kafka") for f in features)
        if needs_kafka:
            apt_repos.append(_confluent_repo(codename))
            add("libssl3")
            add("zlib1g")

        if any(f in ("spool", "tiered-sink") for f in features):
            add("libzstd1")

        needs_ssl = any(
            f == "http"
            or f.startswith("secrets")
            or f.startswith("transport")
            or f == "config-postgres"
            or f.startswith("otel")
            for f in features
        )
        if needs_ssl:
            add("libssl3")
            add("zlib1g")

        if "directory-config-git" in features:
            add(libgit2_runtime_package(distro_codename))

        return cls(apt_repos=apt_repos, apt_packages=packages, distro_codename=distro_codename)


def _confluent_repo(codename: str) -> AptRepoContract:
    """Confluent APT repository for librdkafka."""
    return AptRepoContract(
        key_url="https://packages.confluent.io/clients/deb/archive.key",
        keyring="/usr/share/keyrings/confluent-clients.gpg",
        url="https://packages.confluent.io/clients/deb",
        codename=codename,
        packages=["librdkafka1"],
    )


def _confluent_suite_codename(base_image: str) -> str:
    """Pick a Confluent-published APT suite for the librdkafka repo.

    Deliberately NOT the distro codename -- Confluent publishes its own set of
    suites, so the repo tracks a suite Confluent actually ships rather than
    whatever the base image happens to be. Both ``bookworm`` and ``noble``
    are verified (by build) to install cleanly on a trixie base, which is why
    the trixie move did not need a change here. Use
    :data:`DEFAULT_DISTRO_CODENAME` for distro-versioned package names.
    """
    if "bookworm" in base_image:
        return "bookworm"
    if "jammy" in base_image:
        return "jammy"
    if "focal" in base_image:
        return "focal"
    return "noble"


__all__ = [
    "DEFAULT_DISTRO_CODENAME",
    "AptRepoContract",
    "NativeDepsContract",
    "libgit2_runtime_package",
]
