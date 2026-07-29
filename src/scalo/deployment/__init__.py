# Project:   scalo
# File:      deployment/__init__.py
# Purpose:   Public API for the deployment-contract subsystem
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Deployment contract and artefact generation for Python apps.

scalo-py is the Tier-2 producer of the HyperI deployment contract (scalo-rs is
Tier 1 for Rust). The serialised JSON stays schema-compatible across both, but
artefact *generation* here is Python-native (uv venv runtime stage,
console-script entrypoint, ``python:*-slim`` base) -- it does not emit Rust
artefacts.

This subsystem is opt-in via the ``[deployment]`` extra; importing
``scalo.deployment`` without ``pydantic>=2.13`` raises a clear
``ProviderNotAvailableError`` so apps that don't use container artefact
generation aren't forced to install Pydantic.

Install with::

    pip install "scalo[deployment]"

or in ``pyproject.toml``::

    [project.optional-dependencies]
    dev = ["scalo[deployment]>=2.28.0"]
"""

from __future__ import annotations

# Contract Identity v1 has no pydantic dependency -- always available
# whenever the deployment package can be imported. Keep this import
# outside the pydantic-gated block so consumers can stamp identities
# even before installing the ``deployment`` extra.
from .contract_identity import (
    KEY_PREFIX,
    VERSION,
    ContractIdentity,
    IdentityError,
)

try:
    import pydantic

    DEPLOYMENT_AVAILABLE = True
except ImportError:
    DEPLOYMENT_AVAILABLE = False


if not DEPLOYMENT_AVAILABLE:
    # Defer the error until something is actually used so a bare
    # `from scalo import deployment` doesn't break import graphs.
    def _missing(*_args: object, **_kwargs: object) -> None:
        from scalo.secrets.exceptions import ProviderNotAvailableError

        raise ProviderNotAvailableError(
            "deployment",
            "pydantic",
            "pip install 'scalo[deployment]'",
        )

    DeploymentContract = _missing  # type: ignore[assignment]
    Capability = _missing  # type: ignore[assignment]
    FieldSpec = _missing  # type: ignore[assignment]
    FieldType = _missing  # type: ignore[assignment]
    config_schema_json = _missing  # type: ignore[assignment]
    emit_config_artifacts = _missing  # type: ignore[assignment]
    check_config_artifact_drift = _missing  # type: ignore[assignment]
    assert_no_config_artifact_drift = _missing  # type: ignore[assignment]
    HealthContract = _missing  # type: ignore[assignment]
    ImageProfile = _missing  # type: ignore[assignment]
    OciLabels = _missing  # type: ignore[assignment]
    PortContract = _missing  # type: ignore[assignment]
    SecretEnvContract = _missing  # type: ignore[assignment]
    SecretGroupContract = _missing  # type: ignore[assignment]
    KedaConfig = _missing  # type: ignore[assignment]
    KedaContract = _missing  # type: ignore[assignment]
    AptRepoContract = _missing  # type: ignore[assignment]
    NativeDepsContract = _missing  # type: ignore[assignment]
    ArgocdConfig = _missing  # type: ignore[assignment]
    AppProjectContract = _missing  # type: ignore[assignment]
    AppProjectDestination = _missing  # type: ignore[assignment]
    generate_argocd_app_project = _missing  # type: ignore[assignment]
    WAVE_OPERATORS: int = -20
    WAVE_CRDS: int = -10
    WAVE_TOPICS: int = -5
    WAVE_APPS: int = 0
    WAVE_POST: int = 10
    ContractMismatch = _missing  # type: ignore[assignment]
    DeploymentError = _missing  # type: ignore[assignment]
    generate_builder_stage = _missing  # type: ignore[assignment]
    generate_dockerfile = _missing  # type: ignore[assignment]
    generate_runtime_stage = _missing  # type: ignore[assignment]
    generate_container_manifest = _missing  # type: ignore[assignment]
    generate_compose_fragment = _missing  # type: ignore[assignment]
    generate_chart = _missing  # type: ignore[assignment]
    generate_argocd_application = _missing  # type: ignore[assignment]
    validate_base_image = _missing  # type: ignore[assignment]
    validate_dockerfile = _missing  # type: ignore[assignment]
    validate_helm_values = _missing  # type: ignore[assignment]
    generate_dockerignore = _missing  # type: ignore[assignment]
    image_registry_from_cascade = _missing  # type: ignore[assignment]
    base_image_from_cascade = _missing  # type: ignore[assignment]
    argocd_repo_url_from_cascade = _missing  # type: ignore[assignment]
    # Image defaults are plain strings with no pydantic dependency, so they
    # come from the one source even on the degraded-import path -- never
    # re-spelled here, where they would silently drift from the contract.
    libgit2_runtime_package = _missing  # type: ignore[assignment]
    from .registry import (
        DEFAULT_BASE_IMAGE,
        DEFAULT_BUILDER_IMAGE,
        DEFAULT_DISTRO_CODENAME,
        DEFAULT_IMAGE_REGISTRY,
        DEFAULT_PYTHON_VERSION,
        default_base_image,
        default_builder_image,
    )
else:
    from .app_project import (
        AppProjectContract,
        AppProjectDestination,
        generate_argocd_app_project,
    )
    from .capability import Capability, FieldSpec, FieldType
    from .contract import (
        DEFAULT_LICENSE,
        DEFAULT_SCHEMA_VERSION,
        DEFAULT_VENDOR,
        MAX_SUPPORTED_SCHEMA_VERSION,
        DeploymentContract,
        HealthContract,
        ImageProfile,
        OciLabels,
        PortContract,
        SecretEnvContract,
        SecretGroupContract,
    )
    from .emit import (
        assert_no_config_artifact_drift,
        check_config_artifact_drift,
        config_schema_json,
        emit_config_artifacts,
    )
    from .errors import (
        ContractMismatch,
        CreateDirError,
        DeploymentError,
        NotFoundError,
        ParseYamlError,
        ReadFileError,
        WriteFileError,
    )
    from .generate import (
        ArgocdConfig,
        generate_argocd_application,
        generate_builder_stage,
        generate_chart,
        generate_compose_fragment,
        generate_container_manifest,
        generate_dockerfile,
        generate_dockerignore,
        generate_runtime_stage,
    )
    from .keda import KedaConfig, KedaContract
    from .native_deps import (
        AptRepoContract,
        NativeDepsContract,
        libgit2_runtime_package,
    )
    from .registry import (
        DEFAULT_BASE_IMAGE,
        DEFAULT_BUILDER_IMAGE,
        DEFAULT_DISTRO_CODENAME,
        DEFAULT_IMAGE_REGISTRY,
        DEFAULT_PYTHON_VERSION,
        argocd_repo_url_from_cascade,
        base_image_from_cascade,
        default_base_image,
        default_builder_image,
        image_registry_from_cascade,
    )
    from .validate import validate_base_image, validate_dockerfile, validate_helm_values
    from .waves import (
        WAVE_APPS,
        WAVE_CRDS,
        WAVE_OPERATORS,
        WAVE_POST,
        WAVE_TOPICS,
    )


__all__ = [
    "DEFAULT_BASE_IMAGE",
    "DEFAULT_BUILDER_IMAGE",
    "DEFAULT_DISTRO_CODENAME",
    "DEFAULT_IMAGE_REGISTRY",
    "DEFAULT_PYTHON_VERSION",
    "DEPLOYMENT_AVAILABLE",
    "KEY_PREFIX",
    "VERSION",
    "WAVE_APPS",
    "WAVE_CRDS",
    "WAVE_OPERATORS",
    "WAVE_POST",
    "WAVE_TOPICS",
    "AppProjectContract",
    "AppProjectDestination",
    "AptRepoContract",
    "ArgocdConfig",
    "Capability",
    "ContractIdentity",
    "ContractMismatch",
    "DeploymentContract",
    "DeploymentError",
    "FieldSpec",
    "FieldType",
    "HealthContract",
    "IdentityError",
    "ImageProfile",
    "KedaConfig",
    "KedaContract",
    "NativeDepsContract",
    "OciLabels",
    "PortContract",
    "SecretEnvContract",
    "SecretGroupContract",
    "argocd_repo_url_from_cascade",
    "assert_no_config_artifact_drift",
    "base_image_from_cascade",
    "check_config_artifact_drift",
    "config_schema_json",
    "default_base_image",
    "default_builder_image",
    "emit_config_artifacts",
    "generate_argocd_app_project",
    "generate_argocd_application",
    "generate_builder_stage",
    "generate_chart",
    "generate_compose_fragment",
    "generate_container_manifest",
    "generate_dockerfile",
    "generate_dockerignore",
    "generate_runtime_stage",
    "image_registry_from_cascade",
    "libgit2_runtime_package",
    "validate_base_image",
    "validate_dockerfile",
    "validate_helm_values",
]
