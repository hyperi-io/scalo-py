# Project:   scalo
# File:      tests/unit/deployment/test_container_standard.py
# Purpose:   Container-standard conformance for the generated artefacts
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Conformance tests for the HyperI container standard (scalo-py#4).

Covers the defects that shipped to every consumer of the generator: a
package name that does not exist in the target suite, a builder stage that
defeated its own layer cache, an unpinnable builder image, and the default
base image spelled in more than one place.
"""

from __future__ import annotations

import json

import pytest

from .support import py_contract

try:
    from scalo.deployment import (
        CONFLUENT_KEY_FINGERPRINT,
        DEFAULT_BASE_IMAGE,
        DEFAULT_BUILDER_IMAGE,
        DEFAULT_DISTRO_CODENAME,
        DEFAULT_PYTHON_VERSION,
        DEPLOYMENT_AVAILABLE,
        DeploymentContract,
        NativeDepsContract,
        default_base_image,
        default_builder_image,
        generate_builder_stage,
        generate_dockerignore,
        generate_runtime_stage,
        libgit2_runtime_package,
        validate_base_image,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False

pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="scalo.deployment requires the [deployment] extra",
)


# Packages that do NOT exist in a given suite. Soname-versioned libraries are
# the case where Debian's `Provides:` aliasing does not save you, so a wrong
# name here is an outright build failure (`Unable to locate package`).
ABSENT_FROM_SUITE = {
    "trixie": {"libgit2-1.7"},
    "bookworm": {"libgit2-1.9"},
}


class TestLibgit2SuiteResolution:
    """libgit2-1.7 does not exist in Debian trixie."""

    def test_trixie_gets_1_9(self):
        assert libgit2_runtime_package("trixie") == "libgit2-1.9"

    def test_older_suites_get_1_7(self):
        assert libgit2_runtime_package("bookworm") == "libgit2-1.7"

    def test_default_codename_is_trixie(self):
        # python:*-slim is trixie underneath; the default must follow it.
        assert DEFAULT_DISTRO_CODENAME == "trixie"

    def test_git_feature_emits_trixie_package_by_default(self):
        deps = NativeDepsContract.for_scalo_features(["directory-config-git"], DEFAULT_BASE_IMAGE)
        assert "libgit2-1.9" in deps.apt_packages
        assert "libgit2-1.7" not in deps.apt_packages

    def test_explicit_codename_overrides(self):
        deps = NativeDepsContract.for_scalo_features(
            ["directory-config-git"],
            "python:3.12-slim",
            distro_codename="bookworm",
        )
        assert "libgit2-1.7" in deps.apt_packages
        assert deps.distro_codename == "bookworm"

    def test_codename_is_not_sniffed_from_base_image(self):
        # The regression this guards: deriving the suite by substring-matching
        # the base image breaks on debian:13-slim / stable-slim / digest pins.
        for base in ("debian:13-slim", "debian:stable-slim", "python:3.12-slim@sha256:abc"):
            deps = NativeDepsContract.for_scalo_features(["directory-config-git"], base)
            assert "libgit2-1.9" in deps.apt_packages, base


class TestNoPackageAbsentFromTargetSuite:
    """No emitted apt package may be absent from the target suite."""

    @pytest.mark.parametrize("codename", sorted(ABSENT_FROM_SUITE))
    def test_scalo_rs_features_emit_nothing_absent_from_suite(self, codename: str):
        features = [
            "directory-config-git",
            "transport-kafka",
            "spool",
            "tiered-sink",
            "http",
            "secrets-vault",
            "config-postgres",
            "otel",
        ]
        deps = NativeDepsContract.for_scalo_features(features, DEFAULT_BASE_IMAGE, distro_codename=codename)
        emitted = set(deps.apt_packages)
        for repo in deps.apt_repos:
            emitted.update(repo.packages)
        assert not (emitted & ABSENT_FROM_SUITE[codename]), (
            f"emitted a package absent from {codename}: {emitted & ABSENT_FROM_SUITE[codename]}"
        )

    @pytest.mark.parametrize("codename", sorted(ABSENT_FROM_SUITE))
    def test_scalo_py_extras_emit_nothing_absent_from_suite(self, codename: str):
        deps = NativeDepsContract.for_scalo_extras(
            ["kafka", "opentelemetry", "http", "secrets-vault"],
            DEFAULT_BASE_IMAGE,
            distro_codename=codename,
        )
        emitted = set(deps.apt_packages)
        for repo in deps.apt_repos:
            emitted.update(repo.packages)
        assert not (emitted & ABSENT_FROM_SUITE[codename])


class TestBuilderStageLayerCache:
    """The builder stage must not defeat its own layer cache."""

    def test_project_source_is_copied_after_the_dependency_sync(self):
        text = generate_builder_stage(py_contract())
        first_sync = text.index("uv sync --frozen --no-dev --no-install-project")
        copy_src = text.index("COPY src/ src/")
        assert first_sync < copy_src, (
            "COPY src/ must come AFTER the dependency-only sync, or any source "
            "edit invalidates the whole dependency layer"
        )

    def test_two_phase_sync(self):
        text = generate_builder_stage(py_contract())
        # Phase 1 installs deps without the project; phase 2 installs the project.
        assert "uv sync --frozen --no-dev --no-install-project" in text
        assert text.rstrip().endswith("RUN uv sync --frozen --no-dev")

    def test_manifests_copied_before_first_sync(self):
        text = generate_builder_stage(py_contract())
        assert text.index("COPY pyproject.toml uv.lock ./") < text.index("uv sync")


class TestBuilderStageUvPosture:
    """Never source-build a DEPENDENCY; bytecode at build time."""

    def test_no_build_covers_the_dependency_phase(self):
        text = generate_builder_stage(py_contract())
        assert "RUN UV_NO_BUILD=1 uv sync --frozen --no-dev --no-install-project" in text

    def test_no_build_is_not_stage_wide(self):
        # Regression guard. As a stage-wide `ENV UV_NO_BUILD=1` this also
        # blocks building THE PROJECT, which is a local source tree with no
        # wheel, so phase 2 died with "marked as --no-build but has no binary
        # distribution" and every generated Dockerfile failed to build.
        text = generate_builder_stage(py_contract())
        assert "ENV UV_NO_BUILD" not in text

    def test_project_phase_has_no_build_restriction(self):
        text = generate_builder_stage(py_contract())
        project_phase = text.split("COPY src/ src/", 1)[1]
        assert "UV_NO_BUILD" not in project_phase

    def test_compile_bytecode_is_set(self):
        assert "ENV UV_COMPILE_BYTECODE=1" in generate_builder_stage(py_contract())

    def test_uv_env_precedes_the_sync(self):
        text = generate_builder_stage(py_contract())
        assert text.index("UV_COMPILE_BYTECODE") < text.index("uv sync")


class TestBuilderImageContractField:
    """The builder image is overridable and pinned deliberately."""

    def test_default_builder_image_matches_python_version(self):
        c = py_contract()
        assert c.effective_builder_image() == default_builder_image(c.python_version)

    def test_explicit_builder_image_wins(self):
        c = py_contract().model_copy(update={"builder_image": "internal/uv:pinned"})
        assert c.effective_builder_image() == "internal/uv:pinned"
        assert "FROM internal/uv:pinned AS builder" in generate_builder_stage(c)

    def test_builder_trails_runtime_by_one_debian_release(self):
        # glibc(runtime) >= glibc(build): a binary built against older glibc
        # runs on newer, never the reverse. Holding the builder on bookworm
        # while the runtime is trixie keeps the safe direction.
        c = py_contract()
        assert "bookworm" in c.effective_builder_image()
        assert "slim" in c.effective_base_image()


class TestSingleSourcedImageDefaults:
    """The default base and builder image literals are single-sourced."""

    def test_contract_default_matches_registry_default(self):
        c = DeploymentContract(
            app_name="x",
            metrics_port=9090,
            env_prefix="X",
            metric_prefix="x",
            config_mount_path="/etc/x.yaml",
            image_registry="registry.example.com",
        )
        assert c.effective_base_image() == DEFAULT_BASE_IMAGE
        assert c.effective_builder_image() == DEFAULT_BUILDER_IMAGE

    def test_python_version_bump_moves_both_images_together(self):
        c = DeploymentContract(
            app_name="x",
            metrics_port=9090,
            env_prefix="X",
            metric_prefix="x",
            config_mount_path="/etc/x.yaml",
            image_registry="registry.example.com",
            python_version="3.13",
        )
        assert c.effective_base_image() == "python:3.13-slim"
        assert "python3.13" in c.effective_builder_image()

    def test_default_python_version_is_single_sourced(self):
        assert default_base_image(DEFAULT_PYTHON_VERSION) == DEFAULT_BASE_IMAGE
        assert default_builder_image(DEFAULT_PYTHON_VERSION) == DEFAULT_BUILDER_IMAGE


class TestHealthcheckIsContractGated:
    """K8s ignores HEALTHCHECK, so a cluster-only image can drop it."""

    def test_emitted_by_default(self):
        assert "HEALTHCHECK" in generate_runtime_stage(py_contract())

    def test_suppressed_when_disabled(self):
        c = py_contract().model_copy(update={"emit_healthcheck": False})
        text = generate_runtime_stage(c)
        assert "HEALTHCHECK" not in text
        # The entrypoint must still be intact after removing the block.
        assert 'ENTRYPOINT ["dfe-api"]' in text

    def test_curl_stays_either_way(self):
        # curl earns its place as a debug utility independently of HEALTHCHECK.
        c = py_contract().model_copy(update={"emit_healthcheck": False})
        assert "curl" in generate_runtime_stage(c)


class TestDockerignore:
    """The whole context transfers to the daemon on every build."""

    def test_excludes_the_heavy_and_the_secret(self):
        text = generate_dockerignore(py_contract())
        for entry in (".git", ".venv", "__pycache__", ".env", "*.key", "dist"):
            assert entry in text, entry

    def test_keeps_the_env_sample(self):
        assert "!.env.sample" in generate_dockerignore(py_contract())

    def test_deterministic(self):
        assert generate_dockerignore(py_contract()) == generate_dockerignore(py_contract())


class TestAptRepoKeyIsPinned:
    """The generated build must not re-establish trust in an APT key every build.

    Without a pin the key is downloaded fresh and whatever comes back is
    trusted: a compromised mirror serves its own key, ``signed-by`` validates
    the attacker's repo, and their ``librdkafka1`` goes into the image.
    """

    @staticmethod
    def _kafka_runtime_stage() -> str:
        contract = py_contract().model_copy(
            update={"native_deps": NativeDepsContract.for_scalo_extras(["kafka"], base_image=DEFAULT_BASE_IMAGE)}
        )
        return generate_runtime_stage(contract)

    def test_the_confluent_repo_carries_a_fingerprint(self):
        deps = NativeDepsContract.for_scalo_extras(["kafka"], base_image=DEFAULT_BASE_IMAGE)
        assert deps.apt_repos, "the kafka extra must add the Confluent repo"
        for repo in deps.apt_repos:
            assert repo.key_fingerprint, f"{repo.url} has no pinned key fingerprint"
            assert repo.key_fingerprint == repo.key_fingerprint.upper()
            assert " " not in repo.key_fingerprint, "gpg --with-colons emits the fingerprint unspaced"

    def test_the_fingerprint_is_asserted_in_the_build(self):
        stage = self._kafka_runtime_stage()
        assert "gpg --show-keys --with-colons --with-fingerprint" in stage
        assert f"^fpr:::::::::{CONFLUENT_KEY_FINGERPRINT}:" in stage

    def test_the_check_runs_before_the_key_is_trusted(self):
        stage = self._kafka_runtime_stage()
        check = stage.index("--with-fingerprint")
        dearmor = stage.index("gpg --dearmor")
        assert check < dearmor, "the key was dearmoured into the keyring before it was verified"

    def test_the_key_is_not_piped_into_gpg(self):
        """`sh` has no pipefail, so a failed fetch would leave an empty keyring."""
        stage = self._kafka_runtime_stage()
        assert "| gpg" not in stage
        assert "-o /tmp/repo-key.asc" in stage

    def test_the_downloaded_key_does_not_stay_in_the_layer(self):
        stage = self._kafka_runtime_stage()
        assert "rm -f /tmp/repo-key.asc" in stage
        assert "rm -f /tmp/repo-key.info" in stage

    def test_the_manifest_records_the_pin(self):
        """CI reads the manifest, so the pin has to survive the round trip."""
        from scalo.deployment import generate_container_manifest

        contract = py_contract().model_copy(
            update={"native_deps": NativeDepsContract.for_scalo_extras(["kafka"], base_image=DEFAULT_BASE_IMAGE)}
        )
        manifest = json.loads(generate_container_manifest(contract))
        repos = manifest["runtime_packages"]["apt_repos"]
        assert repos, "the manifest lost the APT repo"
        assert repos[0]["key_fingerprint"] == CONFLUENT_KEY_FINGERPRINT


class TestAlpineGuard:
    """musl/Alpine bases are flagged; Debian is the supported base."""

    def test_clean_on_the_default_debian_base(self):
        assert validate_base_image(py_contract()) == []

    def test_flags_alpine_runtime(self):
        c = py_contract().model_copy(update={"base_image": "python:3.12-alpine"})
        issues = validate_base_image(c)
        assert len(issues) == 1
        assert issues[0].field == "base_image"

    def test_flags_musl_builder(self):
        c = py_contract().model_copy(update={"builder_image": "some/uv:musl"})
        issues = validate_base_image(c)
        assert len(issues) == 1
        assert issues[0].field == "builder_image"
