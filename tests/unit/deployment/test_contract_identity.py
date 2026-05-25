# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_contract_identity.py
# Purpose:   Unit tests for the Contract Identity v1 annotation scheme
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for ``hyperi_pylib.deployment.contract_identity``.

Covers validators, the auto-detect classmethod, and the two serialisers
(``as_dockerfile_labels``, ``as_yaml_annotations``). These tests define
byte-equivalent output that the cross-language parity test will verify
against the shared golden fixture once rustlib lands its implementation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hyperi_pylib.deployment.contract_identity import (
    KEY_PREFIX,
    VERSION,
    ContractIdentity,
    IdentityError,
)
from hyperi_pylib.deployment.errors import DeploymentError


VALID_SHA = "0123456789abcdef0123456789abcdef01234567"
VALID_REF = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"


# ---- Constants ------------------------------------------------------------


def test_key_prefix_is_io_hyperi_contract() -> None:
    assert KEY_PREFIX == "io.hyperi.contract"


def test_version_is_literal_v1() -> None:
    assert VERSION == "v1"


# ---- source_commit validators ---------------------------------------------


def test_valid_source_commit_accepted() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    assert ident.source_commit == VALID_SHA


def test_source_commit_rejects_39_chars() -> None:
    with pytest.raises(IdentityError, match="source_commit"):
        ContractIdentity(source_commit=VALID_SHA[:-1], image_ref=VALID_REF)


def test_source_commit_rejects_41_chars() -> None:
    with pytest.raises(IdentityError, match="source_commit"):
        ContractIdentity(source_commit=VALID_SHA + "0", image_ref=VALID_REF)


def test_source_commit_rejects_uppercase_hex() -> None:
    with pytest.raises(IdentityError, match="source_commit"):
        ContractIdentity(source_commit=VALID_SHA.upper(), image_ref=VALID_REF)


def test_source_commit_rejects_sha256_prefix() -> None:
    with pytest.raises(IdentityError, match="source_commit"):
        ContractIdentity(source_commit=f"sha256:{VALID_SHA}", image_ref=VALID_REF)


def test_source_commit_rejects_whitespace() -> None:
    with pytest.raises(IdentityError, match="source_commit"):
        ContractIdentity(source_commit=f" {VALID_SHA}", image_ref=VALID_REF)


def test_source_commit_rejects_non_hex_chars() -> None:
    bad = "g" + VALID_SHA[1:]
    with pytest.raises(IdentityError, match="source_commit"):
        ContractIdentity(source_commit=bad, image_ref=VALID_REF)


# ---- image_ref validators -------------------------------------------------


def test_image_ref_rejects_empty() -> None:
    with pytest.raises(IdentityError, match="image_ref"):
        ContractIdentity(source_commit=VALID_SHA, image_ref="")


def test_image_ref_rejects_whitespace_only() -> None:
    with pytest.raises(IdentityError, match="image_ref"):
        ContractIdentity(source_commit=VALID_SHA, image_ref="   ")


def test_image_ref_rejects_leading_trailing_whitespace() -> None:
    with pytest.raises(IdentityError, match="image_ref"):
        ContractIdentity(source_commit=VALID_SHA, image_ref=f" {VALID_REF}")


def test_image_ref_rejects_bare_path_no_slash() -> None:
    with pytest.raises(IdentityError, match="image_ref"):
        ContractIdentity(source_commit=VALID_SHA, image_ref="nginx:1.25")


def test_image_ref_rejects_implicit_docker_hub() -> None:
    with pytest.raises(IdentityError, match="image_ref"):
        ContractIdentity(source_commit=VALID_SHA, image_ref="library/nginx")


def test_image_ref_accepts_ghcr() -> None:
    ContractIdentity(source_commit=VALID_SHA, image_ref="ghcr.io/hyperi-io/x:v1")


def test_image_ref_accepts_localhost() -> None:
    ContractIdentity(source_commit=VALID_SHA, image_ref="localhost/x:dev")


def test_image_ref_accepts_localhost_with_port() -> None:
    ContractIdentity(source_commit=VALID_SHA, image_ref="localhost:5000/x:dev")


def test_image_ref_accepts_digest_form() -> None:
    digest_ref = "ghcr.io/hyperi-io/x@sha256:" + "a" * 64
    ContractIdentity(source_commit=VALID_SHA, image_ref=digest_ref)


# ---- Exception type -------------------------------------------------------


def test_identity_error_subclasses_deployment_error() -> None:
    assert issubclass(IdentityError, DeploymentError)


def test_identity_error_subclasses_value_error() -> None:
    assert issubclass(IdentityError, ValueError)


# ---- Frozen dataclass -----------------------------------------------------


def test_identity_is_immutable() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    with pytest.raises((AttributeError, Exception)):
        ident.source_commit = "x" * 40  # type: ignore[misc]


# ---- as_dockerfile_labels -------------------------------------------------


def test_as_dockerfile_labels_format() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    out = ident.as_dockerfile_labels()
    expected = (
        f'LABEL io.hyperi.contract.version="v1"\n'
        f'LABEL io.hyperi.contract.source-commit="{VALID_SHA}"\n'
        f'LABEL io.hyperi.contract.image-ref="{VALID_REF}"'
    )
    assert out == expected


def test_as_dockerfile_labels_no_trailing_newline() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    assert not ident.as_dockerfile_labels().endswith("\n")


def test_as_dockerfile_labels_grep_prefix() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    out = ident.as_dockerfile_labels()
    assert out.count("io.hyperi.contract.") == 3


# ---- as_yaml_annotations --------------------------------------------------


def test_as_yaml_annotations_indent_0() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    out = ident.as_yaml_annotations(indent=0)
    expected = (
        f'io.hyperi.contract.version: "v1"\n'
        f'io.hyperi.contract.source-commit: "{VALID_SHA}"\n'
        f'io.hyperi.contract.image-ref: "{VALID_REF}"'
    )
    assert out == expected


def test_as_yaml_annotations_indent_4() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    out = ident.as_yaml_annotations(indent=4)
    expected = (
        f'    io.hyperi.contract.version: "v1"\n'
        f'    io.hyperi.contract.source-commit: "{VALID_SHA}"\n'
        f'    io.hyperi.contract.image-ref: "{VALID_REF}"'
    )
    assert out == expected


def test_as_yaml_annotations_no_trailing_newline() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    assert not ident.as_yaml_annotations().endswith("\n")


def test_as_yaml_annotations_values_double_quoted() -> None:
    ident = ContractIdentity(source_commit=VALID_SHA, image_ref=VALID_REF)
    out = ident.as_yaml_annotations()
    # v1 must be quoted so YAML doesn't parse it as a partial-version literal
    assert '"v1"' in out
    # SHA must be quoted
    assert f'"{VALID_SHA}"' in out


# ---- detect classmethod ---------------------------------------------------


def test_detect_uses_github_sha_env_first() -> None:
    env = {"GITHUB_SHA": VALID_SHA, "CI_COMMIT_SHA": "f" * 40}
    with patch.dict(os.environ, env, clear=False):
        ident = ContractIdentity.detect(image_ref=VALID_REF)
    assert ident.source_commit == VALID_SHA


def test_detect_falls_back_to_ci_commit_sha() -> None:
    env = {"CI_COMMIT_SHA": VALID_SHA}
    with patch.dict(os.environ, env, clear=False):
        # Make sure GITHUB_SHA is absent
        os.environ.pop("GITHUB_SHA", None)
        ident = ContractIdentity.detect(image_ref=VALID_REF)
    assert ident.source_commit == VALID_SHA


def test_detect_falls_back_to_git_rev_parse(tmp_path: Path) -> None:
    # Run inside a tempdir that's a fresh git repo with one commit
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=str(tmp_path),
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    subprocess.run(
        ["git", "-c", "user.email=t@e.t", "-c", "user.name=t", "commit",
         "--allow-empty", "-m", "init", "--quiet"],
        cwd=str(tmp_path),
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    env_no_sha = {k: v for k, v in os.environ.items()
                  if k not in ("GITHUB_SHA", "CI_COMMIT_SHA")}
    with patch.dict(os.environ, env_no_sha, clear=True):
        prev_cwd = Path.cwd()
        try:
            os.chdir(str(tmp_path))
            ident = ContractIdentity.detect(image_ref=VALID_REF)
        finally:
            os.chdir(str(prev_cwd))
    # 40-char lowercase hex SHA
    assert len(ident.source_commit) == 40
    assert all(c in "0123456789abcdef" for c in ident.source_commit)


def test_detect_raises_when_no_sha_available(tmp_path: Path) -> None:
    env_no_sha = {k: v for k, v in os.environ.items()
                  if k not in ("GITHUB_SHA", "CI_COMMIT_SHA")}
    # Use a tempdir that's NOT a git repo so rev-parse fails
    with patch.dict(os.environ, env_no_sha, clear=True):
        prev_cwd = Path.cwd()
        try:
            os.chdir(str(tmp_path))
            with pytest.raises(IdentityError, match="source_commit"):
                ContractIdentity.detect(image_ref=VALID_REF)
        finally:
            os.chdir(str(prev_cwd))


def test_detect_rejects_invalid_image_ref() -> None:
    env = {"GITHUB_SHA": VALID_SHA}
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(IdentityError, match="image_ref"):
            ContractIdentity.detect(image_ref="nginx:1.25")
