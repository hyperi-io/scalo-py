# Project:   scalo
# File:      deployment/contract.py
# Purpose:   Deployment contract Pydantic models
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Deployment contract Pydantic models for Python apps.

scalo-py is the Tier-2 producer of the scalo deployment contract (scalo-rs is
Tier 1 for Rust services). Apps build a ``DeploymentContract`` from their
``Config`` defaults; generation functions create Python-native deployment
artefacts (uv/venv runtime-stage Dockerfile, Helm chart, Compose fragment,
ArgoCD Application) and validation functions check existing artefacts against
the contract.

The serialised JSON (``deployment-contract.json`` / ``container-manifest.json``)
stays schema-compatible with scalo-rs's so CI tooling reads either uniformly;
the *generation* is Python-specific (uv venv, console-script entrypoint,
``python:*-slim`` base) -- it does not produce Rust artefacts.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .capability import Capability
from .contract_identity import DEFAULT_LABEL_NAMESPACE
from .keda import KedaContract
from .native_deps import NativeDepsContract
from .registry import DEFAULT_PYTHON_VERSION, default_base_image, default_builder_image


class ImageProfile(StrEnum):
    """Container image profile -- controls what goes into the generated Dockerfile.

    Both profiles use the same linking strategy (dynamic). The difference is
    optimisation level, debug tooling, and image metadata.

    Image tagging convention:

    | Profile | Tag | Example |
    |---------|-----|---------|
    | ``production`` | ``:<version>``, ``:latest`` | ``my-loader:1.15.0`` |
    | ``development`` | ``:<version>-dev``, ``:latest-dev`` | ``my-loader:1.15.0-dev`` |
    """

    PRODUCTION = "production"
    """Minimal production image -- stripped binary, no debug tools."""

    DEVELOPMENT = "development"
    """Development image -- includes diagnostic tools (bash, strace, tcpdump,
    procps, dnsutils, net-tools). Same binary, same linking."""


# ---- Defaults (module-level so they appear in JSON Schema docs) -------------

# v3: added config_schema + capabilities (scalo-py#3 / scalo-rs#6). Back-compat --
# old consumers ignore the new optional fields.
DEFAULT_SCHEMA_VERSION = 3
MAX_SUPPORTED_SCHEMA_VERSION = 3


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

    vendor: str = ""
    """Image vendor, the ``org.opencontainers.image.vendor`` label. Empty by
    default, and an empty vendor writes no label."""

    label_namespace: str = DEFAULT_LABEL_NAMESPACE
    """Reverse-DNS namespace of the keys scalo stamps itself:
    ``<namespace>.profile``, ``<namespace>.app`` and ``<namespace>.metrics_port``
    on the image, and the three ``<namespace>.contract.*`` identity keys on
    every artefact. Defaults to ``io.scalo``."""

    licenses: str = ""
    """The app's licence (SPDX). Drives both the
    ``org.opencontainers.image.licenses`` label and the generated Dockerfile's
    ``# License`` header line. Empty by default, and an empty licence writes
    neither."""

    copyright: str = ""
    """The app's copyright line for the generated Dockerfile's ``# Copyright``
    header line. Empty by default, and an empty copyright writes no line."""


class HealthContract(BaseModel):
    """Health probe endpoint paths.

    There is no startup path. A ``startupProbe`` targets ``liveness_path``:
    Kubernetes suspends liveness until the startup probe passes, so one path
    gives both a generous boot budget and a tight liveness period without the
    two drifting apart.
    """

    model_config = ConfigDict(extra="forbid")

    liveness_path: str = "/livez"
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
    """Full env var name (e.g., ``MYAPP__KAFKA__PASSWORD``)."""

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
    """Application name (e.g., ``my-loader``) -- matched against ``Chart.yaml`` ``name``."""

    binary_name: str = ""
    """Binary name (e.g., ``my-loader``). Defaults to app_name when empty."""

    description: str = ""
    """One-line description for ``Chart.yaml``."""

    metrics_port: int = Field(ge=1, le=65535)
    """Metrics/health listen port (e.g., 9090)."""

    health: HealthContract = Field(default_factory=HealthContract)
    """Health probe endpoint paths."""

    env_prefix: str
    """Environment variable prefix (e.g., ``MYAPP``).

    Used with ``__`` nesting for the Dynaconf config cascade.
    """

    metric_prefix: str
    """Prometheus metric namespace/prefix (e.g., ``loader``)."""

    config_mount_path: str
    """Config file mount path (e.g., ``/etc/myapp/config.yaml``)."""

    image_registry: str
    """Container registry base the image is pushed to and pulled from (e.g.,
    ``registry.example.com/team``). Required: there is no default, and a blank
    value is refused. Read it from the cascade with
    :func:`~scalo.deployment.image_registry_from_cascade`."""

    extra_ports: list[PortContract] = Field(default_factory=list)
    """Additional ports beyond metrics (e.g., HTTP data port for receiver)."""

    entrypoint_args: list[str] = Field(default_factory=list)
    """Default ENTRYPOINT args (e.g., ``["--config", "/etc/app/loader.yaml"]``)."""

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

    builder_image: str = ""
    """Builder-stage image (the uv image that produces ``/app/.venv``).

    Leave empty (the default) for the Astral uv image matching
    ``python_version``. Set explicitly to override -- mirrors ``base_image``.
    Read it via :meth:`effective_builder_image`.

    The default deliberately trails the runtime by one Debian release; see
    :func:`~scalo.deployment.registry.default_builder_image` for the
    ``glibc(runtime) >= glibc(build)`` rule that pins the direction.
    """

    python_version: str = DEFAULT_PYTHON_VERSION
    """Python version for the runtime/base image (e.g. ``"3.14"``).

    Drives the default base image (``python:{python_version}-slim``) and the
    uv builder image when ``base_image`` / ``builder_image`` are left empty.
    """

    native_deps: NativeDepsContract = Field(default_factory=NativeDepsContract)
    """Runtime native dependencies for the container image.

    Use ``NativeDepsContract.for_scalo_extras`` to auto-populate from scalo-py
    optional-dependency names; the Dockerfile generator emits the correct
    APT repo setup and package installation commands.
    """

    image_profile: ImageProfile = ImageProfile.PRODUCTION
    """Image profile -- production (minimal) or development (debug tools)."""

    emit_healthcheck: bool = True
    """Emit a ``HEALTHCHECK`` directive in the runtime stage.

    Kubernetes ignores ``HEALTHCHECK`` entirely -- it uses the probes from
    the pod spec -- so for a cluster-only image the directive is dead weight.
    It is still on by default because Compose DOES use it, and Compose is a
    supported target. Set False for images that only ever run in K8s.

    ``curl`` stays in the image either way: the standard keeps small debug
    utilities, and it earns its place on those merits.
    """

    oci_labels: OciLabels = Field(default_factory=OciLabels)
    """OCI image labels (static -- dynamic labels injected by CI at build time)."""

    config_schema: dict[str, Any] | None = None
    """Reflectable JSON Schema (draft 2020-12) of the app's full ``Config``,
    derived via pydantic ``model_json_schema`` (scalo-py#3). ``None`` when not
    provided. Secret fields carry the ``x-scalo-secret`` marker. Also written to
    ``config-schema.{json,yaml}`` by
    :func:`scalo.deployment.emit_config_artifacts`."""

    capabilities: list[Capability] = Field(default_factory=list)
    """Capability catalog -- the runtime-data surface a schema cannot derive
    (service names + their knobs). Hand-authored per app. Also written to
    ``capability-catalog.{json,yaml}``."""

    @field_validator("image_registry")
    @classmethod
    def _registry_is_set(cls, value: str) -> str:
        """Refuse a blank registry: an image named without one resolves to Docker Hub."""
        if not value.strip():
            raise ValueError(
                "no registry is set, so the chart, compose file and container manifest would "
                "name an image nothing pushed. Set `image_registry` in the contract, or "
                "`deployment.image_registry` in the config cascade"
            )
        return value

    # ---- Convenience accessors (mirror scalo-rs's impl block) ---------------

    def binary(self) -> str:
        """Effective binary name -- falls back to app_name when binary_name empty."""
        return self.binary_name if self.binary_name else self.app_name

    def effective_base_image(self) -> str:
        """Runtime base image -- explicit ``base_image`` or ``python:{python_version}-slim``."""
        return self.base_image if self.base_image else default_base_image(self.python_version)

    def effective_builder_image(self) -> str:
        """Builder image -- explicit ``builder_image`` or the matching uv image."""
        return self.builder_image if self.builder_image else default_builder_image(self.python_version)

    def config_filename(self) -> str:
        """Config file name from the mount path (e.g., ``loader.yaml``)."""
        if "/" not in self.config_mount_path:
            # A bare filename IS the filename. Returning a hardcoded
            # "config.yaml" here would rename the app's config behind its back.
            return self.config_mount_path or "config.yaml"
        return self.config_mount_path.rsplit("/", 1)[-1]

    def config_dir(self) -> str:
        """Config mount directory (e.g., ``/etc/app``)."""
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
    "DEFAULT_SCHEMA_VERSION",
    "MAX_SUPPORTED_SCHEMA_VERSION",
    "DeploymentContract",
    "HealthContract",
    "ImageProfile",
    "OciLabels",
    "PortContract",
    "SecretEnvContract",
    "SecretGroupContract",
]
