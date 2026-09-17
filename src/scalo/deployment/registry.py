# Project:   scalo
# File:      deployment/registry.py
# Purpose:   Config-cascade-driven container registry resolution
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Container registry resolution -- mirrors scalo-rs's
``scalo::deployment::registry``.

The publish-target registry (where the built image is pushed) and the base
image (the ``FROM`` line) are org-wide decisions, not per-app. This module
reads them from the Dynaconf cascade so they live in YAML config rather than
being hardcoded in each app's contract source.

Cascade keys::

    deployment:
      image_registry: localhost:5000        # default: localhost:5000
      base_image: python:3.14-slim          # default: python:3.14-slim
      argocd:
        repo_url: https://github.com/your-org/<app>  # default: derived
"""

from __future__ import annotations

DEFAULT_IMAGE_REGISTRY = "localhost:5000"
"""Neutral default registry. Parameterise per app via the
``deployment.image_registry`` cascade key (e.g., ``ghcr.io/your-org``)."""

DEFAULT_PYTHON_VERSION = "3.14"
"""Default Python version driving both the runtime base and builder images.

The single source for the version -- ``DeploymentContract.python_version``
defaults to it, and both image helpers below format it in, so a bump cannot
leave one path on an older tag than the other.
"""


DEFAULT_DISTRO_CODENAME = "trixie"
"""Base-image distro suite (Debian 13) that ``python:*-slim`` resolves to.

Stated explicitly and kept beside the image defaults it belongs to, because
package selection must never sniff the codename out of the base-image string
-- ``debian:13-slim``, ``debian:stable-slim`` and any digest-pinned reference
all defeat substring matching.
"""


def default_base_image(python_version: str = DEFAULT_PYTHON_VERSION) -> str:
    """Default runtime base image for Python apps.

    ``python:*-slim`` is Debian 13 (trixie) underneath, which is the
    estate-wide base OS. Override per-environment via the
    ``deployment.base_image`` cascade key.
    """
    return f"python:{python_version}-slim"


def default_builder_image(python_version: str = DEFAULT_PYTHON_VERSION) -> str:
    """Default Astral uv builder image.

    Deliberately held on ``-bookworm-slim`` (Debian 12) while the runtime is
    ``-slim`` (Debian 13). The rule is ``glibc(runtime) >= glibc(build)``: a
    binary built against older glibc runs on newer, not the reverse. Keeping
    the builder explicitly one release behind means the safe direction holds
    even if Astral repoints its tags -- if these ever invert, the failure is
    ``version 'GLIBC_x.yz' not found`` at container exec, in the target
    environment rather than at build time.
    """
    return f"ghcr.io/astral-sh/uv:python{python_version}-bookworm-slim"


DEFAULT_BASE_IMAGE = default_base_image()
"""Default runtime base image (see :func:`default_base_image`)."""

DEFAULT_BUILDER_IMAGE = default_builder_image()
"""Default uv builder image (see :func:`default_builder_image`)."""


def _from_settings(key: str) -> str | None:
    """Look up a dotted key in the active Dynaconf settings, if available."""
    try:
        from scalo.config import settings
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
    ``https://github.com/your-org/{app_name}`` -- matches the org convention.
    """
    return _from_settings("deployment.argocd.repo_url") or f"https://github.com/your-org/{app_name}"


__all__ = [
    "DEFAULT_BASE_IMAGE",
    "DEFAULT_BUILDER_IMAGE",
    "DEFAULT_DISTRO_CODENAME",
    "DEFAULT_IMAGE_REGISTRY",
    "DEFAULT_PYTHON_VERSION",
    "argocd_repo_url_from_cascade",
    "base_image_from_cascade",
    "default_base_image",
    "default_builder_image",
    "image_registry_from_cascade",
]
