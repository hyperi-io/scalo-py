# Project:   hyperi-pylib
# File:      deployment/__init__.py
# Purpose:   Public API for the deployment-contract subsystem
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Deployment contract and artefact generation.

Mirrors ``hyperi_rustlib::deployment``: the same JSON contract input produces
matching Dockerfile / Helm chart / Compose fragment / ArgoCD Application
output across both implementations.

This subsystem is opt-in via the ``[deployment]`` extra; importing
``hyperi_pylib.deployment`` without ``pydantic>=2.13`` raises a clear
``ProviderNotAvailableError`` so apps that don't use container artefact
generation aren't forced to install Pydantic.

Install with::

    pip install "hyperi-pylib[deployment]"

or in ``pyproject.toml``::

    [project.optional-dependencies]
    dev = ["hyperi-pylib[deployment]>=2.28.0"]
"""

from __future__ import annotations

try:
    import pydantic

    DEPLOYMENT_AVAILABLE = True
except ImportError:
    DEPLOYMENT_AVAILABLE = False


if not DEPLOYMENT_AVAILABLE:
    # Defer the error until something is actually used so a bare
    # `from hyperi_pylib import deployment` doesn't break import graphs.
    def _missing(*_args: object, **_kwargs: object) -> None:
        from hyperi_pylib.secrets.exceptions import ProviderNotAvailableError

        raise ProviderNotAvailableError(
            "deployment",
            "pydantic",
            "pip install 'hyperi-pylib[deployment]'",
        )

    DeploymentContract = _missing  # type: ignore[assignment]
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
    generate_dockerfile = _missing  # type: ignore[assignment]
    generate_runtime_stage = _missing  # type: ignore[assignment]
    generate_container_manifest = _missing  # type: ignore[assignment]
    generate_compose_fragment = _missing  # type: ignore[assignment]
    generate_chart = _missing  # type: ignore[assignment]
    generate_argocd_application = _missing  # type: ignore[assignment]
    image_registry_from_cascade = _missing  # type: ignore[assignment]
    base_image_from_cascade = _missing  # type: ignore[assignment]
    argocd_repo_url_from_cascade = _missing  # type: ignore[assignment]
    DEFAULT_IMAGE_REGISTRY = "ghcr.io/hyperi-io"
    DEFAULT_BASE_IMAGE = "ubuntu:24.04"
else:
    from .app_project import (
        AppProjectContract,
        AppProjectDestination,
        generate_argocd_app_project,
    )
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
        generate_chart,
        generate_compose_fragment,
        generate_container_manifest,
        generate_dockerfile,
        generate_runtime_stage,
    )
    from .keda import KedaConfig, KedaContract
    from .native_deps import AptRepoContract, NativeDepsContract
    from .registry import (
        DEFAULT_BASE_IMAGE,
        DEFAULT_IMAGE_REGISTRY,
        argocd_repo_url_from_cascade,
        base_image_from_cascade,
        image_registry_from_cascade,
    )
    from .waves import (
        WAVE_APPS,
        WAVE_CRDS,
        WAVE_OPERATORS,
        WAVE_POST,
        WAVE_TOPICS,
    )


__all__ = [
    "DEFAULT_BASE_IMAGE",
    "DEFAULT_IMAGE_REGISTRY",
    "DEPLOYMENT_AVAILABLE",
    "WAVE_APPS",
    "WAVE_CRDS",
    "WAVE_OPERATORS",
    "WAVE_POST",
    "WAVE_TOPICS",
    "AppProjectContract",
    "AppProjectDestination",
    "AptRepoContract",
    "ArgocdConfig",
    "ContractMismatch",
    "DeploymentContract",
    "DeploymentError",
    "HealthContract",
    "ImageProfile",
    "KedaConfig",
    "KedaContract",
    "NativeDepsContract",
    "OciLabels",
    "PortContract",
    "SecretEnvContract",
    "SecretGroupContract",
    "argocd_repo_url_from_cascade",
    "base_image_from_cascade",
    "generate_argocd_app_project",
    "generate_argocd_application",
    "generate_chart",
    "generate_compose_fragment",
    "generate_container_manifest",
    "generate_dockerfile",
    "generate_runtime_stage",
    "image_registry_from_cascade",
]
