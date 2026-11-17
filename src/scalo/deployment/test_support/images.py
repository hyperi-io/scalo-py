#  Project:   scalo
#  File:      src/scalo/deployment/test_support/images.py
#  Purpose:   Pull Docker Hub test images through the GHCR mirror
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Docker Hub test images, pulled through the mirror.

Hosted CI runners pull Docker Hub anonymously and hit its rate limit, so a test
image goes through a mirror that serves the same tag and digest. A pinned
reference stays valid, and Renovate keeps tracking the upstream name.
"""

import os

DEFAULT_IMAGE_MIRROR = "ghcr.io/hyperi-io/mirror"
"""Last-resort mirror, used when neither the cascade nor the env names one."""

_KEY = "deployment.test_image_mirror"
_ENV = "DEPLOYMENT__TEST_IMAGE_MIRROR"
_DOCKER_HUB_HOSTS = ("docker.io/", "index.docker.io/", "registry-1.docker.io/")


def image_mirror() -> str:
    """Return the registry path Docker Hub test images are pulled through.

    Reads ``DEPLOYMENT__TEST_IMAGE_MIRROR``, then ``deployment.test_image_mirror``
    from the cascade, then ``DEFAULT_IMAGE_MIRROR``. The env var is read live
    because the cascade snapshots ENV when it loads, so a test that sets it later
    would get the old value. An empty value at either layer means Docker Hub itself.
    """
    if _ENV in os.environ:
        return os.environ[_ENV]
    try:
        from scalo.config import settings

        value = settings.get(_KEY)
    except Exception:
        value = None
    return DEFAULT_IMAGE_MIRROR if value is None else str(value)


def mirrored(mirror: str, reference: str) -> str:
    """Return ``reference`` under ``mirror`` when it names Docker Hub.

    An official image (``alpine:3.24``) gains ``library/``, a namespaced one
    keeps its namespace, and a reference naming another registry comes back
    unchanged. An empty ``mirror`` means Docker Hub itself.
    """
    for host in _DOCKER_HUB_HOSTS:
        if reference.startswith(host):
            reference = reference.removeprefix(host)
            break
    mirror = mirror.rstrip("/")
    first, sep, _ = reference.partition("/")
    other_registry = bool(sep) and ("." in first or ":" in first or first == "localhost")
    if not mirror or other_registry:
        return reference
    return f"{mirror}/{reference}" if sep else f"{mirror}/library/{reference}"


def mirror_image(reference: str) -> str:
    """Return ``reference`` pulled through :func:`image_mirror` when it names Docker Hub."""
    return mirrored(image_mirror(), reference)


__all__ = ["DEFAULT_IMAGE_MIRROR", "image_mirror", "mirror_image", "mirrored"]
