# Project:   hyperi-pylib
# File:      deployment/registry.py
# Purpose:   Config-cascade-driven container registry resolution
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Container registry resolution -- mirrors rustlib's
``hyperi_rustlib::deployment::registry``.

The publish-target registry (where the built image is pushed) and the base
image (the ``FROM`` line) are org-wide decisions, not per-app. This module
reads them from the Dynaconf cascade so they live in YAML config rather than
being hardcoded in each app's contract source.

Cascade keys::

    deployment:
      image_registry: ghcr.io/hyperi-io        # default: ghcr.io/hyperi-io
      base_image: ubuntu:24.04                 # default: ubuntu:24.04
      argocd:
        repo_url: https://github.com/hyperi-io/<app>  # default: derived
"""

from __future__ import annotations

DEFAULT_IMAGE_REGISTRY = "ghcr.io/hyperi-io"
"""Default publish-target registry for HyperI org."""

DEFAULT_BASE_IMAGE = "python:3.12-slim"
"""Default runtime base image for Python apps.

Pulled from Docker Hub. Override per-environment by setting
``deployment.base_image`` in the YAML cascade.
"""


def _from_settings(key: str) -> str | None:
    """Look up a dotted key in the active Dynaconf settings, if available."""
    try:
        from hyperi_pylib.config import settings
    except Exception:
        return None
    try:
        value = settings.get(key)
    except Exception:
        return None
    if value is None:
        return None
    text = str(value)
    return text if text else None


def image_registry_from_cascade() -> str:
    """Read the publish-target image registry from the config cascade.

    Reads ``deployment.image_registry`` from the Dynaconf cascade. Falls back
    to ``DEFAULT_IMAGE_REGISTRY`` when not set or when config isn't loaded.
    """
    return _from_settings("deployment.image_registry") or DEFAULT_IMAGE_REGISTRY


def base_image_from_cascade() -> str:
    """Read the runtime base image from the config cascade.

    Reads ``deployment.base_image``. Falls back to ``DEFAULT_BASE_IMAGE``.
    """
    return _from_settings("deployment.base_image") or DEFAULT_BASE_IMAGE


def argocd_repo_url_from_cascade(app_name: str) -> str:
    """Read the git repo URL for ArgoCD generation from the config cascade.

    Reads ``deployment.argocd.repo_url``. Falls back to
    ``https://github.com/hyperi-io/{app_name}`` -- matches the org convention.
    """
    return _from_settings("deployment.argocd.repo_url") or f"https://github.com/hyperi-io/{app_name}"


__all__ = [
    "DEFAULT_BASE_IMAGE",
    "DEFAULT_IMAGE_REGISTRY",
    "argocd_repo_url_from_cascade",
    "base_image_from_cascade",
    "image_registry_from_cascade",
]
