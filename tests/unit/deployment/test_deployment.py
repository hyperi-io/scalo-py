# Project:   scalo
# File:      tests/unit/deployment/test_deployment.py
# Purpose:   Snapshot tests for the deployment-contract subsystem
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Snapshot tests for deployment artefact generators.

Cross-language byte parity with scalo-rs will be wired in v2.29.0 once
``scalo-rs/tests/parity/fixtures/`` lands. For now we verify shape
and key fragments -- enough to catch regressions while the contract is
being shaped.
"""

import json

import pytest

try:
    from scalo.deployment import (
        DEPLOYMENT_AVAILABLE,
        DeploymentContract,
        HealthContract,
        ImageProfile,
        KedaConfig,
        KedaContract,
        NativeDepsContract,
        OciLabels,
        PortContract,
        SecretEnvContract,
        SecretGroupContract,
        generate_compose_fragment,
        generate_container_manifest,
        generate_dockerfile,
        generate_runtime_stage,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False

from .support import deps_with_repo

# Every C library these link is in the wheel or the static binary, so none installs a package.
STATICALLY_LINKED_EXTRAS = ["kafka", "opentelemetry", "http", "secrets-aws", "secrets-vault", "expression", "metrics"]
STATICALLY_LINKED_FEATURES = ["transport-kafka", "dlq-kafka", "spool", "tiered-sink", "http", "secrets", "otel"]


pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="scalo.deployment requires the [deployment] extra (pydantic)",
)


# -----------------------------------------------------------------------------
# Test contract -- mirrors scalo-rs's tests::test_contract() in shape
# -----------------------------------------------------------------------------


def _full_contract() -> DeploymentContract:
    return DeploymentContract(
        app_name="dfe-loader",
        binary_name="dfe-loader",
        description="High-performance Kafka to ClickHouse data loader",
        metrics_port=9090,
        health=HealthContract(),
        env_prefix="DFE_LOADER",
        metric_prefix="loader",
        config_mount_path="/etc/dfe/loader.yaml",
        image_registry="ghcr.io/hyperi-io",
        extra_ports=[],
        entrypoint_args=["--config", "/etc/dfe/loader.yaml"],
        secrets=[
            SecretGroupContract(
                group_name="kafka",
                env_vars=[
                    SecretEnvContract(
                        env_var="DFE_LOADER__KAFKA__USERNAME",
                        key_name="username",
                        secret_key="kafka-username",
                    ),
                    SecretEnvContract(
                        env_var="DFE_LOADER__KAFKA__PASSWORD",
                        key_name="password",
                        secret_key="kafka-password",
                    ),
                ],
            ),
            SecretGroupContract(
                group_name="clickhouse",
                env_vars=[
                    SecretEnvContract(
                        env_var="DFE_LOADER__CLICKHOUSE__PASSWORD",
                        key_name="password",
                        secret_key="clickhouse-password",
                    ),
                ],
            ),
        ],
        depends_on=["kafka", "clickhouse"],
        keda=KedaContract(),
        native_deps=NativeDepsContract(),
        image_profile=ImageProfile.PRODUCTION,
        oci_labels=OciLabels(),
        schema_version=2,
    )


# -----------------------------------------------------------------------------
# Contract round-trips
# -----------------------------------------------------------------------------


class TestContractRoundtrips:
    def test_to_json_and_back(self):
        original = _full_contract()
        text = original.to_json()
        rebuilt = DeploymentContract.from_json(text)
        assert rebuilt.app_name == "dfe-loader"
        assert rebuilt.metrics_port == 9090
        assert len(rebuilt.secrets) == 2
        assert rebuilt.keda is not None
        assert rebuilt.keda.kafka_lag_threshold == 1000

    def test_binary_falls_back_to_app_name(self):
        c = _full_contract().model_copy(update={"binary_name": ""})
        assert c.binary() == "dfe-loader"

    def test_config_filename_and_dir(self):
        c = _full_contract()
        assert c.config_filename() == "loader.yaml"
        assert c.config_dir() == "/etc/dfe"

    def test_with_dev_profile_is_clone(self):
        c = _full_contract()
        dev = c.with_dev_profile()
        assert dev.image_profile == ImageProfile.DEVELOPMENT
        assert c.image_profile == ImageProfile.PRODUCTION
        assert dev.app_name == c.app_name


# -----------------------------------------------------------------------------
# Python runtime contract (issue #22)
# -----------------------------------------------------------------------------


class TestPythonRuntimeContract:
    def _minimal(self) -> DeploymentContract:
        return DeploymentContract(
            app_name="a",
            metrics_port=8000,
            env_prefix="A",
            metric_prefix="a",
            config_mount_path="/etc/a.yaml",
            image_registry="registry.example.com",
        )

    def test_default_python_version(self):
        assert self._minimal().python_version == "3.14"

    def test_base_image_defaults_to_python_slim(self):
        c = self._minimal()
        assert c.base_image == ""
        assert c.effective_base_image() == "python:3.14-slim"

    def test_python_version_drives_base_image(self):
        c = self._minimal().model_copy(update={"python_version": "3.13"})
        assert c.effective_base_image() == "python:3.13-slim"

    def test_explicit_base_image_wins(self):
        c = self._minimal().model_copy(update={"base_image": "python:3.12-bookworm"})
        assert c.effective_base_image() == "python:3.12-bookworm"


# -----------------------------------------------------------------------------
# Dockerfile
# -----------------------------------------------------------------------------


class TestGenerateDockerfile:
    def test_basic_shape(self):
        df = generate_dockerfile(_full_contract())
        # Python multi-stage: uv builder + venv runtime.
        assert "FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder" in df
        assert "uv sync --frozen --no-dev" in df
        assert "FROM python:3.14-slim AS runtime" in df
        assert "COPY --from=builder /app /app" in df
        assert 'ENV PATH="/app/.venv/bin:$PATH"' in df
        # No Rust cargo layout.
        assert "/usr/local/bin/dfe-loader" not in df
        assert "/app/target/release" not in df
        assert "userdel" not in df
        assert "EXPOSE 9090" in df
        assert "localhost:9090/livez" in df
        assert 'ENTRYPOINT ["dfe-loader"]' in df
        assert 'CMD ["--config", "/etc/dfe/loader.yaml"]' in df

    def test_with_native_deps_emits_the_repo_and_packages(self):
        c = _full_contract()
        c.native_deps = deps_with_repo("ubuntu:24.04")
        df = generate_dockerfile(c)
        # Substring check on the generated Dockerfile, not a host allow-list.
        assert "https://apt.vendor.example/deb" in df
        assert "signed-by=/usr/share/keyrings/vendor.gpg" in df
        assert "vendor-runtime" in df
        assert "libgit2-1.9" in df
        assert "gnupg" in df

    def test_statically_linked_extras_and_features_install_nothing(self):
        c = _full_contract()
        for deps in (
            NativeDepsContract.for_scalo_extras(STATICALLY_LINKED_EXTRAS, "ubuntu:24.04"),
            NativeDepsContract.for_scalo_features(STATICALLY_LINKED_FEATURES, "ubuntu:24.04"),
        ):
            c.native_deps = deps
            for image in (generate_dockerfile(c), generate_runtime_stage(c)):
                for absent in ("librdkafka", "libssl", "zlib1g", "libzstd", "confluent", "signed-by", "gnupg"):
                    assert absent not in image, absent
                # The linked-in OpenSSL reads the CA store ca-certificates installs.
                assert " ca-certificates" in image

    @pytest.mark.parametrize(
        ("codename", "line"),
        [
            pytest.param("", "deb bookworm main", id="no-codename-takes-the-release"),
            pytest.param("noble", "deb noble main", id="a-codename-is-kept"),
        ],
    )
    def test_a_repo_codename(self, codename, line):
        c = _full_contract()
        c.base_image = "debian:bookworm-slim"
        c.native_deps = deps_with_repo("debian:bookworm-slim", distro_codename="bookworm")
        c.native_deps.apt_repos[0].codename = codename
        assert f"https://apt.vendor.example/{line}" in generate_dockerfile(c)

    def test_production_profile(self):
        df = generate_dockerfile(_full_contract())
        assert "Purpose:   production container image" in df
        assert 'LABEL io.scalo.profile="production"' in df
        assert "strace" not in df
        assert "tcpdump" not in df

    def test_development_profile(self):
        df = generate_dockerfile(_full_contract().with_dev_profile())
        assert "Purpose:   development container image" in df
        assert 'LABEL io.scalo.profile="development"' in df
        assert "strace" in df
        assert "tcpdump" in df
        assert "procps" in df
        assert "bash" in df
        assert "jq" in df

    def test_dev_with_native_deps_includes_both(self):
        c = _full_contract()
        c.native_deps = deps_with_repo("ubuntu:24.04")
        df = generate_dockerfile(c.with_dev_profile())
        assert "strace" in df
        assert "vendor-runtime" in df
        assert 'LABEL io.scalo.profile="development"' in df

    def test_extra_ports_in_expose(self):
        c = _full_contract()
        c.extra_ports = [PortContract(name="http", port=8080)]
        df = generate_dockerfile(c)
        assert "EXPOSE 9090 8080" in df


# The header lines every generated Dockerfile starts with, before the licence and copyright.
HEADER_TOP = "# Project:   dfe-loader\n# File:      Dockerfile\n# Purpose:   production container image\n#\n"


def _with_labels(**labels: str) -> DeploymentContract:
    return _full_contract().model_copy(update={"oci_labels": OciLabels(**labels)})


class TestDockerfileHeader:
    def test_omits_an_unset_licence_and_copyright(self):
        # No line, not an empty one, and no second "#".
        df = generate_dockerfile(_full_contract())
        assert df.startswith(f"{HEADER_TOP}# AUTOGENERATED -- do not edit by hand.\n"), df
        assert "# License" not in df
        assert "# Copyright" not in df

    def test_writes_a_set_licence_and_copyright_as_before(self):
        df = generate_dockerfile(_with_labels(licenses="BUSL-1.1", copyright="(c) 2026 Acme Corp"))
        assert df.startswith(
            f"{HEADER_TOP}# License:   BUSL-1.1\n# Copyright: (c) 2026 Acme Corp\n#\n"
            "# AUTOGENERATED -- do not edit by hand.\n"
        ), df

    def test_writes_only_the_line_that_is_set(self):
        df = generate_dockerfile(_with_labels(licenses="MIT"))
        assert df.startswith(f"{HEADER_TOP}# License:   MIT\n#\n# AUTOGENERATED"), df
        df = generate_dockerfile(_with_labels(copyright="(c) 2026 Acme Corp"))
        assert df.startswith(f"{HEADER_TOP}# Copyright: (c) 2026 Acme Corp\n#\n# AUTOGENERATED"), df


class TestOciLabels:
    def test_default_to_no_vendor_licence_or_copyright(self):
        labels = OciLabels()
        assert labels.vendor == ""
        assert labels.licenses == ""
        assert labels.copyright == ""
        assert labels.label_namespace == "io.scalo"

    def test_labels_without_a_namespace_load_under_the_default(self):
        labels = OciLabels.model_validate(
            {"vendor": "Example Ltd", "licenses": "MIT", "copyright": "(c) 2026 Example Ltd"}
        )
        assert (labels.vendor, labels.licenses, labels.copyright) == ("Example Ltd", "MIT", "(c) 2026 Example Ltd")
        assert labels.label_namespace == "io.scalo"

    def test_an_unset_vendor_or_licence_writes_no_label(self):
        c = _full_contract()
        runtime = generate_runtime_stage(c)
        assert 'LABEL org.opencontainers.image.description=""\nLABEL io.scalo.profile="production"\n' in runtime, (
            runtime
        )
        labels = json.loads(generate_container_manifest(c))["labels"]
        for key in ("org.opencontainers.image.vendor", "org.opencontainers.image.licenses"):
            assert key not in runtime
            assert key not in labels

    def test_a_set_vendor_and_licence_are_written_in_place(self):
        c = _with_labels(title="event-loader", vendor="Example Ltd", licenses="MIT", label_namespace="com.example")
        runtime = generate_runtime_stage(c)
        assert (
            "# Static OCI labels (from contract)\n"
            'LABEL org.opencontainers.image.title="event-loader"\n'
            'LABEL org.opencontainers.image.description=""\n'
            'LABEL org.opencontainers.image.vendor="Example Ltd"\n'
            'LABEL org.opencontainers.image.licenses="MIT"\n'
            'LABEL com.example.profile="production"\n\n'
        ) in runtime, runtime
        labels = json.loads(generate_container_manifest(c))["labels"]
        assert list(labels) == [
            "com.example.profile",
            "com.example.app",
            "com.example.metrics_port",
            "org.opencontainers.image.title",
            "org.opencontainers.image.description",
            "org.opencontainers.image.vendor",
            "org.opencontainers.image.licenses",
        ]
        assert labels["org.opencontainers.image.vendor"] == "Example Ltd"
        assert labels["org.opencontainers.image.licenses"] == "MIT"


class TestGenerateBuilderStage:
    def test_uv_builder_snippet(self):
        from scalo.deployment import generate_builder_stage

        text = generate_builder_stage(_full_contract())
        assert "FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder" in text
        assert "COPY pyproject.toml uv.lock ./" in text
        assert "COPY src/ src/" in text
        assert "uv sync --frozen --no-dev" in text
        # No baked credentials -- apps inject via --build-arg.
        assert "ARTIFACTORY" not in text
        assert "TOKEN" not in text

    def test_builder_image_tracks_python_version(self):
        from scalo.deployment import generate_builder_stage

        c = _full_contract().model_copy(update={"python_version": "3.13"})
        assert "uv:python3.13-bookworm-slim AS builder" in generate_builder_stage(c)


# -----------------------------------------------------------------------------
# Runtime stage fragment
# -----------------------------------------------------------------------------


class TestGenerateRuntimeStage:
    def test_has_runtime_stage_marker(self):
        text = generate_runtime_stage(_full_contract())
        assert "FROM python:3.14-slim AS runtime" in text
        assert "COPY --from=builder /app /app" in text
        assert 'ENV PATH="/app/.venv/bin:$PATH"' in text
        assert "ARG OCI_SOURCE=" in text
        assert 'LABEL org.opencontainers.image.source="${OCI_SOURCE}"' in text
        # No Rust cargo layout, no ubuntu-user removal.
        assert "/app/target/release" not in text
        assert "userdel" not in text
        assert "useradd --create-home --uid 1000 appuser" in text


# -----------------------------------------------------------------------------
# Container manifest
# -----------------------------------------------------------------------------


class TestGenerateContainerManifest:
    def test_parses_as_json(self):
        text = generate_container_manifest(_full_contract())
        manifest = json.loads(text)
        assert manifest["app_name"] == "dfe-loader"
        assert manifest["binary_name"] == "dfe-loader"
        assert manifest["base_image"] == "python:3.14-slim"
        assert manifest["image_profile"] == "production"
        assert manifest["expose_ports"] == [9090]
        assert manifest["healthcheck"]["path"] == "/livez"
        assert manifest["healthcheck"]["port"] == 9090
        assert manifest["entrypoint"] == ["dfe-loader"]
        assert manifest["cmd"] == ["--config", "/etc/dfe/loader.yaml"]
        assert manifest["user"] == "appuser"

    def test_includes_native_deps_when_present(self):
        c = _full_contract()
        c.native_deps = deps_with_repo("ubuntu:24.04")
        manifest = json.loads(generate_container_manifest(c))
        assert len(manifest["runtime_packages"]["apt_repos"]) == 1
        assert manifest["runtime_packages"]["apt_repos"][0]["url"] == "https://apt.vendor.example/deb"
        assert manifest["runtime_packages"]["apt_packages"] == ["libgit2-1.9"]

    def test_oci_labels_default_to_app_name(self):
        manifest = json.loads(generate_container_manifest(_full_contract()))
        assert manifest["labels"]["org.opencontainers.image.title"] == "dfe-loader"
        assert manifest["labels"]["io.scalo.app"] == "dfe-loader"
        assert "org.opencontainers.image.vendor" not in manifest["labels"]


# -----------------------------------------------------------------------------
# Compose fragment
# -----------------------------------------------------------------------------


class TestGenerateComposeFragment:
    def test_basic_shape(self):
        text = generate_compose_fragment(_full_contract())
        assert "dfe-loader:" in text
        assert "ghcr.io/hyperi-io/dfe-loader" in text
        assert "kafka:" in text
        assert "clickhouse:" in text
        assert "condition: service_healthy" in text
        assert "loader.yaml:/etc/dfe/loader.yaml:ro" in text
        assert "/livez" in text

    def test_observability_port_exposed_not_published(self):
        # Publishing the observability port to the host partly undoes the
        # reason it is a separate port. It stays reachable inside the compose
        # network (and to the healthcheck) via `expose`.
        text = generate_compose_fragment(_full_contract())
        assert '- "9090"' in text
        assert '"9090:9090"' not in text

    def test_application_ports_are_still_published(self):
        # Only the observability port is withheld -- ports carrying user
        # traffic still need to be reachable from the host.
        contract = _full_contract().model_copy(update={"extra_ports": [PortContract(name="http", port=8080)]})
        text = generate_compose_fragment(contract)
        assert '"8080:8080"' in text
        assert '"9090:9090"' not in text

    def test_declares_resource_limits(self):
        # An unlimited service on a single box is how one container takes the
        # host down.
        text = generate_compose_fragment(_full_contract())
        assert "deploy:" in text
        assert "limits:" in text
        assert "reservations:" in text


# -----------------------------------------------------------------------------
# Cascade readers
# -----------------------------------------------------------------------------


class TestRegistryCascade:
    def test_no_registry_default_when_the_cascade_is_silent(self):
        from scalo.config import settings
        from scalo.deployment import (
            DEFAULT_BASE_IMAGE,
            base_image_from_cascade,
            image_registry_from_cascade,
        )

        settings.unset("DEPLOYMENT")
        assert image_registry_from_cascade() is None
        assert base_image_from_cascade() == DEFAULT_BASE_IMAGE

    def test_readers_return_what_the_cascade_names(self):
        from scalo.config import settings
        from scalo.deployment import base_image_from_cascade, image_registry_from_cascade

        settings.set("deployment.image_registry", "registry.example.com/team")
        settings.set("deployment.base_image", "python:3.14-slim-trixie")
        try:
            assert image_registry_from_cascade() == "registry.example.com/team"
            assert base_image_from_cascade() == "python:3.14-slim-trixie"
        finally:
            settings.unset("DEPLOYMENT")


# -----------------------------------------------------------------------------
# KedaContract.from_config
# -----------------------------------------------------------------------------


class TestKedaContract:
    def test_from_config_carries_the_thresholds_and_enabled(self):
        cfg = KedaConfig(kafka_lag_threshold=5000, cpu_threshold=90)
        contract = KedaContract.from_config(cfg)
        assert contract.kafka_lag_threshold == 5000
        assert contract.cpu_threshold == 90
        assert contract.enabled is True
        assert KedaContract.from_config(KedaConfig(enabled=False)).enabled is False

    def test_keda_contract_defaults_match_config_defaults(self):
        from_default = KedaContract.from_config(KedaConfig())
        bare = KedaContract()
        assert from_default.model_dump() == bare.model_dump()


# -----------------------------------------------------------------------------
# NativeDepsContract.for_scalo_extras
# -----------------------------------------------------------------------------


class TestNativeDepsForPylibExtras:
    @pytest.mark.parametrize("extras", [[], ["kafka"], STATICALLY_LINKED_EXTRAS], ids=["none", "kafka", "all"])
    def test_no_extra_installs_a_package(self, extras):
        deps = NativeDepsContract.for_scalo_extras(extras, "ubuntu:24.04")
        assert deps.is_empty()
        assert deps.distro_codename == "trixie"


class TestNativeDepsForRustlibFeatures:
    """Polyglot path -- when a Python app re-binds a Rust core via PyO3."""

    @pytest.mark.parametrize(
        ("features", "codename", "packages"),
        [
            pytest.param(STATICALLY_LINKED_FEATURES, "trixie", [], id="statically-linked"),
            pytest.param(["directory-config-git", "transport-kafka"], "trixie", ["libgit2-1.9"], id="libgit2-trixie"),
            pytest.param(["directory-config-git"], "bookworm", ["libgit2-1.7"], id="libgit2-bookworm"),
        ],
    )
    def test_only_libgit2_installs_a_package(self, features, codename, packages):
        deps = NativeDepsContract.for_scalo_features(features, "ubuntu:24.04", distro_codename=codename)
        assert deps.apt_packages == packages
        assert deps.apt_repos == []


# -----------------------------------------------------------------------------
# Robustness: YAML parses, generators are deterministic, contract validation
# -----------------------------------------------------------------------------


class TestGeneratedYamlParses:
    """The Compose fragment must round-trip through ``yaml.safe_load``.

    Catches structural regressions that substring-only checks miss (mismatched
    indents, unquoted special characters, missing colons).
    """

    def test_compose_fragment_is_valid_yaml(self):
        text = generate_compose_fragment(_full_contract())
        import yaml

        data = yaml.safe_load(text)
        assert isinstance(data, dict)
        assert "services" in data
        assert "dfe-loader" in data["services"]


class TestGeneratorDeterminism:
    """Calling a generator twice with the same contract MUST return identical output."""

    def test_dockerfile_deterministic(self):
        c = _full_contract()
        c.native_deps = deps_with_repo("ubuntu:24.04")
        assert generate_dockerfile(c) == generate_dockerfile(c)

    def test_runtime_stage_deterministic(self):
        c = _full_contract()
        assert generate_runtime_stage(c) == generate_runtime_stage(c)

    def test_container_manifest_deterministic(self):
        c = _full_contract()
        assert generate_container_manifest(c) == generate_container_manifest(c)

    def test_compose_fragment_deterministic(self):
        c = _full_contract()
        assert generate_compose_fragment(c) == generate_compose_fragment(c)


class TestContractValidation:
    """Pydantic guards -- make sure invalid contracts are caught at construction."""

    def test_metrics_port_zero_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="metrics_port"):
            DeploymentContract(
                app_name="x",
                metrics_port=0,  # invalid: ge=1
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
                image_registry="registry.example.com",
            )

    def test_metrics_port_above_65535_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="metrics_port"):
            DeploymentContract(
                app_name="x",
                metrics_port=70000,  # invalid: le=65535
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
                image_registry="registry.example.com",
            )

    def test_extra_fields_rejected_on_contract(self):
        """``extra="forbid"`` -- typos in field names must fail loudly."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="wrong_field_name"):
            DeploymentContract(
                app_name="x",
                metrics_port=9090,
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
                image_registry="registry.example.com",
                wrong_field_name="boom",  # ty: ignore[unknown-argument]  # the unknown field is the point of the test
            )

    def test_registry_is_required(self):
        """No default registry: a contract that names none is refused at construction."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="image_registry"):
            DeploymentContract(  # ty: ignore[missing-argument]  # the missing registry is the point of the test
                app_name="x",
                metrics_port=9090,
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
            )

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_registry_is_refused(self, blank):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="deployment.image_registry"):
            DeploymentContract(
                app_name="x",
                metrics_port=9090,
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
                image_registry=blank,
            )

    def test_contract_json_without_a_registry_is_refused(self):
        from pydantic import ValidationError

        raw = json.loads(_full_contract().to_json())
        raw.pop("image_registry")
        with pytest.raises(ValidationError, match="image_registry"):
            DeploymentContract.from_json(json.dumps(raw))

    def test_extra_fields_rejected_on_keda_contract(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            KedaContract(unknown=1)  # ty: ignore[unknown-argument]  # the unknown field is the point of the test

    def test_extra_fields_rejected_on_health_contract(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HealthContract(unknown="path")  # ty: ignore[unknown-argument]  # the unknown field is the point of the test

    def test_minimal_required_fields_only(self):
        """Construction with only required fields must succeed and use defaults everywhere else."""
        c = DeploymentContract(
            app_name="minimal",
            metrics_port=8080,
            env_prefix="MIN",
            metric_prefix="min",
            config_mount_path="/etc/min.yaml",
            image_registry="registry.example.com",
        )
        # Defaults applied
        assert c.schema_version == 4
        # base_image defaults empty; resolved to python:{python_version}-slim.
        assert c.base_image == ""
        assert c.effective_base_image() == "python:3.14-slim"
        assert c.image_profile == ImageProfile.PRODUCTION
        assert c.health.liveness_path == "/livez"
        assert c.keda is None
        assert c.binary() == "minimal"  # falls back to app_name

    def test_keda_min_replicas_negative_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            KedaContract(min_replicas=-1)

    def test_port_contract_invalid_port_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PortContract(name="http", port=99999)


class TestMinimalContractGenerators:
    """Generators must work on a contract with only required fields populated."""

    def _minimal(self) -> DeploymentContract:
        return DeploymentContract(
            app_name="minimal-app",
            metrics_port=8080,
            env_prefix="MA",
            metric_prefix="ma",
            config_mount_path="/etc/ma.yaml",
            image_registry="registry.example.com",
        )

    def test_dockerfile_works_on_minimal(self):
        df = generate_dockerfile(self._minimal())
        assert "FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder" in df
        assert "FROM python:3.14-slim AS runtime" in df
        assert "COPY --from=builder /app /app" in df
        assert "EXPOSE 8080" in df
        # No CMD line when entrypoint_args is empty
        assert "\nCMD [" not in df

    def test_compose_works_on_minimal(self):
        text = generate_compose_fragment(self._minimal())
        # No depends_on section when depends_on is empty
        assert "depends_on:" not in text
        # No command line when entrypoint_args is empty
        assert "command:" not in text

    def test_compose_names_the_contract_registry(self):
        assert "image: registry.example.com/minimal-app:" in generate_compose_fragment(self._minimal())

    def test_container_manifest_works_on_minimal(self):
        text = generate_container_manifest(self._minimal())
        manifest = json.loads(text)
        assert manifest["app_name"] == "minimal-app"
        assert manifest["binary_name"] == "minimal-app"  # binary() fallback
        assert manifest["expose_ports"] == [8080]
        assert manifest["cmd"] == []
        assert manifest["runtime_packages"]["apt_repos"] == []
        assert manifest["runtime_packages"]["apt_packages"] == []
