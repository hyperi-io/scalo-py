# Project:   scalo
# File:      deployment/native_deps.py
# Purpose:   Runtime native dependency declarations for container images
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Runtime native dependency contracts -- mirrors scalo-rs's ``scalo::deployment::native_deps``.

For Python apps, the equivalent of scalo-rs's ``for_scalo_features`` is
``for_scalo_extras`` -- pass the list of scalo-py optional extras the app uses,
get back the runtime APT packages and any custom repos needed.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .registry import DEFAULT_DISTRO_CODENAME


class BaseDistro(StrEnum):
    """A distro release scalo resolves runtime package names for (scalo-rs ``BaseDistro``)."""

    TRIXIE = "trixie"
    BOOKWORM = "bookworm"
    NOBLE = "noble"
    JAMMY = "jammy"
    FOCAL = "focal"


def _known_distro(codename: str) -> BaseDistro | None:
    """The release ``codename`` names, or None for one scalo has no package names for."""
    try:
        return BaseDistro(codename)
    except ValueError:
        return None


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

    key_fingerprint: str = ""
    """Expected OpenPGP fingerprint of ``key_url``, uppercase hex, no spaces.

    Asserted before the key is dearmoured into the keyring. Without it the build
    downloads the key fresh every time and trusts whatever comes back: a
    compromised mirror or an intercepted TLS session serves its own key,
    ``signed-by`` then validates the attacker's repo, and their package goes into
    the image. Pinning converts an every-build trust-on-first-use into a one-time
    one; it does not establish that the key was legitimate to begin with.

    Empty skips the check, for a repo whose fingerprint has not been derived.
    """

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

    Populate via ``NativeDepsContract.for_scalo_extras`` from the list of
    ``pyproject.toml`` extras the app uses, or via ``for_scalo_features``
    for polyglot apps that re-bind a Rust core.
    """

    model_config = ConfigDict(extra="forbid")

    apt_repos: list[AptRepoContract] = Field(default_factory=list)
    """Custom APT repositories to add before installing packages."""

    apt_packages: list[str] = Field(default_factory=list)
    """APT packages to install from default repos."""

    distro: BaseDistro | None = Field(default=None, exclude_if=lambda value: value is None)
    """The release the package names were resolved for, as scalo-rs records it.

    None, and left out of the emitted contract, when the contract does not say.
    """

    unresolved_base_image: str | None = Field(default=None, exclude_if=lambda value: value is None)
    """The base image whose release could not be derived, so the default was assumed.

    Left out of the emitted contract when unset.
    """

    contradicted_base_image: str | None = Field(default=None, exclude_if=lambda value: value is None)
    """The base image that names a different release from the one config stated.

    Left out of the emitted contract when unset.
    """

    distro_codename: str = DEFAULT_DISTRO_CODENAME
    """Base-image distro suite the package names were selected for.

    Stated explicitly rather than sniffed from the base-image string, and
    recorded in the emitted contract so CI can audit which suite an image
    targets. Drives soname-versioned package names (e.g. libgit2). A contract
    that names ``distro`` but not this takes it from ``distro``.
    """

    @model_validator(mode="before")
    @classmethod
    def _codename_follows_distro(cls, data: Any) -> Any:
        """Read ``distro_codename`` from ``distro`` when only ``distro`` is given, as scalo-rs writes it."""
        if isinstance(data, dict) and data.get("distro") is not None and "distro_codename" not in data:
            return {**data, "distro_codename": data["distro"]}
        return data

    def is_empty(self) -> bool:
        """True if there are no native deps to install."""
        return not self.apt_repos and not self.apt_packages

    @classmethod
    def for_scalo_extras(
        cls,
        extras: list[str],
        base_image: str,
        *,
        distro_codename: str = DEFAULT_DISTRO_CODENAME,
    ) -> Self:
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

        return cls(
            apt_repos=apt_repos,
            apt_packages=packages,
            distro=_known_distro(distro_codename),
            distro_codename=distro_codename,
        )

    @classmethod
    def for_scalo_features(
        cls,
        features: list[str],
        base_image: str,
        *,
        distro_codename: str = DEFAULT_DISTRO_CODENAME,
    ) -> Self:
        """Build runtime native deps from a list of scalo-rs feature flags.

        Mirrors scalo-rs's ``NativeDepsContract::for_scalo_features`` for
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

        return cls(
            apt_repos=apt_repos,
            apt_packages=packages,
            distro=_known_distro(distro_codename),
            distro_codename=distro_codename,
        )


# OpenPGP v4 fingerprint of the Confluent clients signing key, shared with
# scalo-rs. If Confluent rotates the key the build fails loudly at the gpg
# step -- re-derive and update it, never remove the check.
CONFLUENT_KEY_FINGERPRINT = "CBBB821E8FAF364F79835C438B1DA6120C2BF624"


def _confluent_repo(codename: str) -> AptRepoContract:
    """Confluent APT repository for librdkafka."""
    return AptRepoContract(
        key_url="https://packages.confluent.io/clients/deb/archive.key",
        key_fingerprint=CONFLUENT_KEY_FINGERPRINT,
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
    "CONFLUENT_KEY_FINGERPRINT",
    "DEFAULT_DISTRO_CODENAME",
    "AptRepoContract",
    "BaseDistro",
    "NativeDepsContract",
    "libgit2_runtime_package",
]
