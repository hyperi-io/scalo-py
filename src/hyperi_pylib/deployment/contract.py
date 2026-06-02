# Project:   hyperi-pylib
# File:      deployment/contract.py
# Purpose:   Deployment contract Pydantic models
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Deployment contract Pydantic models for Python apps.

pylib is the Tier-2 producer of the HyperI deployment contract (rustlib is
Tier 1 for Rust services). Apps build a ``DeploymentContract`` from their
``Config`` defaults; generation functions create Python-native deployment
artefacts (uv/venv runtime-stage Dockerfile, Helm chart, Compose fragment,
ArgoCD Application) and validation functions check existing artefacts against
the contract.

The serialised JSON (``deployment-contract.json`` / ``container-manifest.json``)
stays schema-compatible with rustlib's so CI tooling reads either uniformly;
the *generation* is Python-specific (uv venv, console-script entrypoint,
``python:*-slim`` base) -- it does not produce Rust artefacts.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .keda import KedaContract
from .native_deps import NativeDepsContract


class ImageProfile(StrEnum):
    """Container image profile -- controls what goes into the generated Dockerfile.

    Both profiles use the same linking strategy (dynamic). The difference is
    optimisation level, debug tooling, and image metadata.

    Image tagging convention:

    | Profile | Tag | Example |
    |---------|-----|---------|
    | ``production`` | ``:<version>``, ``:latest`` | ``dfe-loader:1.15.0`` |
    | ``development`` | ``:<version>-dev``, ``:latest-dev`` | ``dfe-loader:1.15.0-dev`` |
    """

    PRODUCTION = "production"
    """Minimal production image -- stripped binary, no debug tools."""

    DEVELOPMENT = "development"
    """Development image -- includes diagnostic tools (bash, strace, tcpdump,
    procps, dnsutils, net-tools). Same binary, same linking."""


# ---- Defaults (module-level so they appear in JSON Schema docs) -------------

DEFAULT_VENDOR = "HYPERI PTY LIMITED"
DEFAULT_LICENSE = "BUSL-1.1"
DEFAULT_SCHEMA_VERSION = 2
MAX_SUPPORTED_SCHEMA_VERSION = 2


class OciLabels(BaseModel):
    """OCI image labels for the container.

    Static labels are set from the contract. Dynamic labels (source, revision,
    version, created) are injected by CI at build time via ``--build-arg``.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    """Image title (defaults to app_name when empty)."""

    description: str = ""
    """Image description."""

    vendor: str = DEFAULT_VENDOR
    """Image vendor."""

    licenses: str = DEFAULT_LICENSE
    """License identifier."""


class HealthContract(BaseModel):
    """Health probe endpoint paths."""

    model_config = ConfigDict(extra="forbid")

    liveness_path: str = "/healthz"
    readiness_path: str = "/readyz"
    metrics_path: str = "/metrics"


class PortContract(BaseModel):
    """Additional container port beyond the metrics port."""

    model_config = ConfigDict(extra="forbid")

    name: str
    """Port name (e.g., ``http``)."""

    port: int = Field(ge=1, le=65535)
    """Port number (e.g., 8080)."""

    protocol: str = "TCP"
    """Protocol (default: ``TCP``)."""


class SecretEnvContract(BaseModel):
    """A single environment variable sourced from a K8s Secret."""

    model_config = ConfigDict(extra="forbid")

    env_var: str
    """Full env var name (e.g., ``DFE_LOADER__KAFKA__PASSWORD``)."""

    key_name: str
    """Key name in values.yaml secretKeys and default values (e.g., ``password``)."""

    secret_key: str
    """Default K8s secret key name (e.g., ``kafka-password``)."""


class SecretGroupContract(BaseModel):
    """A group of secrets from the same K8s Secret (e.g., ``kafka``, ``clickhouse``)."""

    model_config = ConfigDict(extra="forbid")

    group_name: str
    """Group name. Used in values.yaml section name and helper template names."""

    env_vars: list[SecretEnvContract]
    """Environment variables injected from this secret group."""


class DeploymentContract(BaseModel):
    """Deployment-facing contract points derived from the app config cascade.

    Apps build this from their ``Config.default()``. Validation functions
    compare Helm charts and Dockerfiles against these values. Generation
    functions create deployment artefacts (Dockerfile, Helm chart, Compose
    fragment) from scratch.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = DEFAULT_SCHEMA_VERSION
    """Contract schema version. CI checks this and fails if unsupported."""

    app_name: str
    """Application name (e.g., ``dfe-loader``) -- matched against ``Chart.yaml`` ``name``."""

    binary_name: str = ""
    """Binary name (e.g., ``dfe-loader``). Defaults to app_name when empty."""

    description: str = ""
    """One-line description for ``Chart.yaml``."""

    metrics_port: int = Field(ge=1, le=65535)
    """Metrics/health listen port (e.g., 9090)."""

    health: HealthContract = Field(default_factory=HealthContract)
    """Health probe endpoint paths."""

    env_prefix: str
    """Environment variable prefix (e.g., ``DFE_LOADER``).

    Used with ``__`` nesting for the Dynaconf config cascade.
    """

    metric_prefix: str
    """Prometheus metric namespace/prefix (e.g., ``loader``)."""

    config_mount_path: str
    """Config file mount path (e.g., ``/etc/dfe/loader.yaml``)."""

    image_registry: str = "ghcr.io/hyperi-io"
    """Container registry base (e.g., ``ghcr.io/hyperi-io``)."""

    extra_ports: list[PortContract] = Field(default_factory=list)
    """Additional ports beyond metrics (e.g., HTTP data port for receiver)."""

    entrypoint_args: list[str] = Field(default_factory=list)
    """Default ENTRYPOINT args (e.g., ``["--config", "/etc/dfe/loader.yaml"]``)."""

    secrets: list[SecretGroupContract] = Field(default_factory=list)
    """Secret groups injected from K8s Secrets."""

    default_config: Any | None = None
    """App-specific config YAML for ``values.yaml`` (any JSON-serialisable shape)."""

    depends_on: list[str] = Field(default_factory=list)
    """Docker Compose service dependencies (e.g., ``["kafka", "clickhouse"]``)."""

    keda: KedaContract | None = None
    """KEDA autoscaling contract (None if KEDA not used)."""

    base_image: str = ""
    """Base container image for the runtime stage.

    Leave empty (the default) to use the language-appropriate
    ``python:{python_version}-slim``. Set explicitly to override. Read it via
    :meth:`effective_base_image`.
    """

    python_version: str = "3.12"
    """Python version for the runtime/base image (e.g. ``"3.12"``).

    Drives the default base image (``python:{python_version}-slim``) and the
    uv builder image when ``base_image`` is left empty.
    """

    native_deps: NativeDepsContract = Field(default_factory=NativeDepsContract)
    """Runtime native dependencies for the container image.

    Use ``NativeDepsContract.for_pylib_extras`` to auto-populate from pylib
    optional-dependency names; the Dockerfile generator emits the correct
    APT repo setup and package installation commands.
    """

    image_profile: ImageProfile = ImageProfile.PRODUCTION
    """Image profile -- production (minimal) or development (debug tools)."""

    oci_labels: OciLabels = Field(default_factory=OciLabels)
    """OCI image labels (static -- dynamic labels injected by CI at build time)."""

    # ---- Convenience accessors (mirror rustlib's impl block) ---------------

    def binary(self) -> str:
        """Effective binary name -- falls back to app_name when binary_name empty."""
        return self.binary_name if self.binary_name else self.app_name

    def effective_base_image(self) -> str:
        """Runtime base image -- explicit ``base_image`` or ``python:{python_version}-slim``."""
        return self.base_image if self.base_image else f"python:{self.python_version}-slim"

    def config_filename(self) -> str:
        """Config file name from the mount path (e.g., ``loader.yaml``)."""
        if "/" not in self.config_mount_path:
            return "config.yaml"
        return self.config_mount_path.rsplit("/", 1)[-1]

    def config_dir(self) -> str:
        """Config mount directory (e.g., ``/etc/dfe``)."""
        if "/" not in self.config_mount_path:
            return "/etc"
        head = self.config_mount_path.rsplit("/", 1)[0]
        return head if head else "/"

    def to_json(self) -> str:
        """Serialise to indent=2 JSON for ``--emit-contract`` CLI support."""
        return self.model_dump_json(indent=2, by_alias=False, exclude_none=False)

    def with_dev_profile(self) -> DeploymentContract:
        """Return a clone with ``ImageProfile.DEVELOPMENT`` set."""
        return self.model_copy(update={"image_profile": ImageProfile.DEVELOPMENT}, deep=True)

    @classmethod
    def from_json(cls, raw: str) -> DeploymentContract:
        """Parse a contract from a JSON string."""
        return cls.model_validate(json.loads(raw))


__all__ = [
    "DEFAULT_LICENSE",
    "DEFAULT_SCHEMA_VERSION",
    "DEFAULT_VENDOR",
    "MAX_SUPPORTED_SCHEMA_VERSION",
    "DeploymentContract",
    "HealthContract",
    "ImageProfile",
    "OciLabels",
    "PortContract",
    "SecretEnvContract",
    "SecretGroupContract",
]
