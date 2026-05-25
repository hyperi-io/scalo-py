# Project:   hyperi-pylib
# File:      deployment/contract_identity.py
# Purpose:   Contract Identity Annotation Scheme v1
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Contract Identity Annotation Scheme v1.

Stamps every deployment artefact (Dockerfile, Helm Chart.yaml, ArgoCD
Application) with three uniform, greppable keys so the same logical
contract output is traceable across surfaces and across language tiers
(rustlib / pylib / hyperi-ci).

Keys (all under the ``io.hyperi.contract`` prefix):

- ``io.hyperi.contract.version`` -- schema version, literal ``v1``.
- ``io.hyperi.contract.source-commit`` -- 40-char lowercase hex git SHA
  of the consumer app's repo HEAD.
- ``io.hyperi.contract.image-ref`` -- intended pull reference, either
  ``<registry>/<repo>:<tag>`` (pre-push) or ``<registry>/<repo>@sha256:<digest>``
  (post-push, immutable).

Mirrors ``hyperi_rustlib::deployment::contract_identity`` once that
module lands. Both implementations consume a shared golden fixture for
byte-equivalent output verification.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

from hyperi_pylib.deployment.errors import DeploymentError


KEY_PREFIX = "io.hyperi.contract"
VERSION = "v1"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class IdentityError(DeploymentError, ValueError):
    """Validation failure for a :class:`ContractIdentity` field.

    Subclasses both :class:`DeploymentError` (for callers using the
    deployment-specific catch) and :class:`ValueError` (so generic
    validation handlers still trigger).
    """


@dataclass(frozen=True, slots=True)
class ContractIdentity:
    """Three-field identity stamped onto every deployment artefact.

    Construct directly with both fields, or use :meth:`detect` to
    auto-resolve ``source_commit`` from the CI env or a local git repo.
    """

    source_commit: str
    image_ref: str

    def __post_init__(self) -> None:
        _validate_source_commit(self.source_commit)
        _validate_image_ref(self.image_ref)

    @classmethod
    def detect(cls, image_ref: str) -> ContractIdentity:
        """Build an identity by auto-resolving ``source_commit``.

        Resolution order:

        1. ``GITHUB_SHA`` env var (GitHub Actions).
        2. ``CI_COMMIT_SHA`` env var (GitLab).
        3. ``git rev-parse HEAD`` in the current working directory.

        Raises :class:`IdentityError` if none yield a 40-char hex SHA or
        if ``image_ref`` is invalid.
        """
        sha = os.environ.get("GITHUB_SHA") or os.environ.get("CI_COMMIT_SHA")
        if not sha:
            sha = _git_head_sha()
        if not sha or not _SHA_RE.fullmatch(sha):
            raise IdentityError(
                "source_commit: auto-detect failed (GITHUB_SHA, "
                "CI_COMMIT_SHA, and `git rev-parse HEAD` all yielded "
                "no 40-char hex SHA)"
            )
        return cls(source_commit=sha, image_ref=image_ref)

    def as_dockerfile_labels(self) -> str:
        """Three ``LABEL`` lines, canonical order, no trailing newline."""
        return (
            f'LABEL {KEY_PREFIX}.version="{VERSION}"\n'
            f'LABEL {KEY_PREFIX}.source-commit="{self.source_commit}"\n'
            f'LABEL {KEY_PREFIX}.image-ref="{self.image_ref}"'
        )

    def as_yaml_annotations(self, indent: int = 0) -> str:
        """Three YAML key/value lines, canonical order, indented.

        Values are always double-quoted so YAML parsers don't coerce
        ``v1`` to a partial-version literal and don't misread refs
        containing ``@sha256:``.
        """
        pad = " " * indent
        return (
            f'{pad}{KEY_PREFIX}.version: "{VERSION}"\n'
            f'{pad}{KEY_PREFIX}.source-commit: "{self.source_commit}"\n'
            f'{pad}{KEY_PREFIX}.image-ref: "{self.image_ref}"'
        )


def _validate_source_commit(value: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise IdentityError(
            f"source_commit: must match {_SHA_RE.pattern} "
            f"(40-char lowercase hex, no sha256: prefix, no whitespace); "
            f"got {value!r}"
        )


def _validate_image_ref(value: str) -> None:
    if value != value.strip() or not value:
        raise IdentityError(
            f"image_ref: must be non-empty with no leading/trailing "
            f"whitespace; got {value!r}"
        )
    if "/" not in value:
        raise IdentityError(
            f"image_ref: must include an explicit registry host "
            f"(no implicit docker.io); got {value!r}"
        )
    host = value.split("/", 1)[0]
    if not ("." in host or ":" in host or host == "localhost"):
        raise IdentityError(
            f"image_ref: registry host {host!r} must contain a dot, "
            f"a port colon, or be the literal 'localhost'; got {value!r}"
        )


def _git_head_sha() -> str | None:
    """Return ``git rev-parse HEAD`` output or ``None`` on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


__all__ = [
    "KEY_PREFIX",
    "VERSION",
    "ContractIdentity",
    "IdentityError",
]
