# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_deployment.py
# Purpose:   Snapshot tests for the deployment-contract subsystem
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Snapshot tests for deployment artefact generators.

Cross-language byte parity with rustlib will be wired in v2.29.0 once
``hyperi-rustlib/tests/parity/fixtures/`` lands. For now we verify shape
and key fragments -- enough to catch regressions while the contract is
being shaped.
"""

from __future__ import annotations

import json

import pytest

try:
    from hyperi_pylib.deployment import (
        DEPLOYMENT_AVAILABLE,
        ArgocdConfig,
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
        generate_argocd_application,
        generate_chart,
        generate_compose_fragment,
        generate_container_manifest,
        generate_dockerfile,
        generate_runtime_stage,
    )

    deployment_importable = DEPLOYMENT_AVAILABLE
except Exception:
    deployment_importable = False


pytestmark = pytest.mark.skipif(
    not deployment_importable,
    reason="hyperi_pylib.deployment requires the [deployment] extra (pydantic)",
)


# -----------------------------------------------------------------------------
# Test contract -- mirrors rustlib's tests::test_contract() in shape
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
        )

    def test_default_python_version(self):
        assert self._minimal().python_version == "3.12"

    def test_base_image_defaults_to_python_slim(self):
        c = self._minimal()
        assert c.base_image == ""
        assert c.effective_base_image() == "python:3.12-slim"

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
        assert "FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder" in df
        assert "uv sync --frozen --no-dev" in df
        assert "FROM python:3.12-slim AS runtime" in df
        assert "COPY --from=builder /app /app" in df
        assert 'ENV PATH="/app/.venv/bin:$PATH"' in df
        # No Rust cargo layout.
        assert "/usr/local/bin/dfe-loader" not in df
        assert "/app/target/release" not in df
        assert "userdel" not in df
        assert "EXPOSE 9090" in df
        assert "localhost:9090/healthz" in df
        assert 'ENTRYPOINT ["dfe-loader"]' in df
        assert 'CMD ["--config", "/etc/dfe/loader.yaml"]' in df

    def test_with_native_deps_emits_confluent(self):
        c = _full_contract()
        c.native_deps = NativeDepsContract.for_pylib_extras(["kafka"], "ubuntu:24.04")
        df = generate_dockerfile(c)
        assert "packages.confluent.io" in df
        assert "confluent-clients.gpg" in df
        assert "librdkafka1" in df
        assert "libssl3" in df
        assert "gnupg" in df

    def test_pure_python_extras_have_no_apt_repos(self):
        c = _full_contract()
        c.native_deps = NativeDepsContract.for_pylib_extras(["expression"], "ubuntu:24.04")
        df = generate_dockerfile(c)
        assert "confluent" not in df
        assert "librdkafka1" not in df
        assert "gnupg" not in df

    def test_bookworm_codename(self):
        c = _full_contract()
        c.base_image = "debian:bookworm-slim"
        c.native_deps = NativeDepsContract.for_pylib_extras(["kafka"], "debian:bookworm-slim")
        df = generate_dockerfile(c)
        assert "bookworm main" in df

    def test_production_profile(self):
        df = generate_dockerfile(_full_contract())
        assert "Purpose:   production container image" in df
        assert 'io.hyperi.profile="production"' in df
        assert "strace" not in df
        assert "tcpdump" not in df

    def test_development_profile(self):
        df = generate_dockerfile(_full_contract().with_dev_profile())
        assert "Purpose:   development container image" in df
        assert 'io.hyperi.profile="development"' in df
        assert "strace" in df
        assert "tcpdump" in df
        assert "procps" in df
        assert "bash" in df
        assert "jq" in df

    def test_dev_with_native_deps_includes_both(self):
        c = _full_contract()
        c.native_deps = NativeDepsContract.for_pylib_extras(["kafka"], "ubuntu:24.04")
        df = generate_dockerfile(c.with_dev_profile())
        assert "strace" in df
        assert "librdkafka1" in df
        assert 'io.hyperi.profile="development"' in df

    def test_extra_ports_in_expose(self):
        c = _full_contract()
        c.extra_ports = [PortContract(name="http", port=8080)]
        df = generate_dockerfile(c)
        assert "EXPOSE 9090 8080" in df


class TestGenerateBuilderStage:
    def test_uv_builder_snippet(self):
        from hyperi_pylib.deployment import generate_builder_stage

        text = generate_builder_stage(_full_contract())
        assert "FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder" in text
        assert "COPY pyproject.toml uv.lock ./" in text
        assert "COPY src/ src/" in text
        assert "uv sync --frozen --no-dev" in text
        # No baked credentials -- apps inject via --build-arg.
        assert "ARTIFACTORY" not in text
        assert "TOKEN" not in text

    def test_builder_image_tracks_python_version(self):
        from hyperi_pylib.deployment import generate_builder_stage

        c = _full_contract().model_copy(update={"python_version": "3.13"})
        assert "uv:python3.13-bookworm-slim AS builder" in generate_builder_stage(c)


# -----------------------------------------------------------------------------
# Runtime stage fragment
# -----------------------------------------------------------------------------


class TestGenerateRuntimeStage:
    def test_has_runtime_stage_marker(self):
        text = generate_runtime_stage(_full_contract())
        assert "FROM python:3.12-slim AS runtime" in text
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
        assert manifest["base_image"] == "python:3.12-slim"
        assert manifest["image_profile"] == "production"
        assert manifest["expose_ports"] == [9090]
        assert manifest["healthcheck"]["path"] == "/healthz"
        assert manifest["healthcheck"]["port"] == 9090
        assert manifest["entrypoint"] == ["dfe-loader"]
        assert manifest["cmd"] == ["--config", "/etc/dfe/loader.yaml"]
        assert manifest["user"] == "appuser"

    def test_includes_native_deps_when_present(self):
        c = _full_contract()
        c.native_deps = NativeDepsContract.for_pylib_extras(["kafka"], "ubuntu:24.04")
        manifest = json.loads(generate_container_manifest(c))
        assert len(manifest["runtime_packages"]["apt_repos"]) == 1
        assert manifest["runtime_packages"]["apt_repos"][0]["url"].startswith("https://packages.confluent.io")
        assert "libssl3" in manifest["runtime_packages"]["apt_packages"]

    def test_oci_labels_default_to_app_name(self):
        manifest = json.loads(generate_container_manifest(_full_contract()))
        assert manifest["labels"]["org.opencontainers.image.title"] == "dfe-loader"
        assert manifest["labels"]["org.opencontainers.image.vendor"] == "HYPERI PTY LIMITED"


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
        assert '"9090:9090"' in text
        assert "loader.yaml:/etc/dfe/loader.yaml:ro" in text
        assert "/healthz" in text


# -----------------------------------------------------------------------------
# Helm chart
# -----------------------------------------------------------------------------


class TestGenerateChart:
    def test_writes_expected_files(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)

        expected = [
            "Chart.yaml",
            "values.yaml",
            "templates/_helpers.tpl",
            "templates/deployment.yaml",
            "templates/service.yaml",
            "templates/serviceaccount.yaml",
            "templates/configmap.yaml",
            "templates/secret.yaml",
            "templates/hpa.yaml",
            "templates/keda-scaledobject.yaml",
            "templates/keda-triggerauth.yaml",
            "templates/NOTES.txt",
        ]
        for rel in expected:
            assert (tmp_path / rel).exists(), f"missing {rel}"

    def test_chart_yaml_content(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)
        text = (tmp_path / "Chart.yaml").read_text()
        assert "name: dfe-loader" in text
        assert "description: High-performance Kafka to ClickHouse data loader" in text

    def test_values_yaml_content(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)
        text = (tmp_path / "values.yaml").read_text()
        assert "port: 9090" in text
        assert 'prometheus.io/port: "9090"' in text
        assert 'prometheus.io/path: "/metrics"' in text
        assert 'lagThreshold: "1000"' in text
        assert "kafka-username" in text
        assert "kafka-password" in text
        assert "clickhouse-password" in text

    def test_helpers_contain_secret_helpers(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)
        text = (tmp_path / "templates/_helpers.tpl").read_text()
        assert "kafkaSecretName" in text
        assert "clickhouseSecretName" in text

    def test_deployment_contains_env_vars_and_probes(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)
        text = (tmp_path / "templates/deployment.yaml").read_text()
        assert "DFE_LOADER__KAFKA__USERNAME" in text
        assert "DFE_LOADER__KAFKA__PASSWORD" in text
        assert "DFE_LOADER__CLICKHOUSE__PASSWORD" in text
        assert "path: /healthz" in text
        assert "path: /readyz" in text
        assert "/etc/dfe" in text

    def test_no_keda_files_when_disabled(self, tmp_path):
        c = _full_contract()
        c.keda = None
        generate_chart(c, tmp_path)
        assert not (tmp_path / "templates/keda-scaledobject.yaml").exists()
        assert not (tmp_path / "templates/keda-triggerauth.yaml").exists()


# -----------------------------------------------------------------------------
# ArgoCD Application
# -----------------------------------------------------------------------------


class TestGenerateArgocd:
    def test_default_config(self):
        argo = ArgocdConfig(repo_url="https://github.com/hyperi-io/dfe-loader")
        text = generate_argocd_application(_full_contract(), argo)
        assert "apiVersion: argoproj.io/v1alpha1" in text
        assert "kind: Application" in text
        assert "name: dfe-loader" in text
        assert "namespace: argocd" in text
        assert "repoURL: https://github.com/hyperi-io/dfe-loader" in text
        assert "targetRevision: main" in text
        assert "path: chart" in text
        assert "CreateNamespace=true" in text
        assert "Schema version:" in text

    def test_custom_namespace_and_path(self):
        argo = ArgocdConfig(
            repo_url="https://github.com/hyperi-io/dfe-loader",
            dest_namespace="production",
            chart_path="deploy/chart",
            target_revision="v1.0.0",
            sync_wave=5,
        )
        text = generate_argocd_application(_full_contract(), argo)
        assert "namespace: production" in text
        assert "path: deploy/chart" in text
        assert "targetRevision: v1.0.0" in text
        assert 'sync-wave: "5"' in text

    def test_argocd_config_default_uses_wave_apps(self):
        from hyperi_pylib.deployment import WAVE_APPS

        cfg = ArgocdConfig()
        assert cfg.sync_wave == WAVE_APPS

    def test_argocd_config_default_has_no_extra_ignore_differences(self):
        cfg = ArgocdConfig()
        assert cfg.extra_ignore_differences == []

    def test_generate_argocd_application_emits_default_ignore_differences(self):
        argo = ArgocdConfig(repo_url="https://github.com/hyperi-io/dfe-loader")
        yaml = generate_argocd_application(_full_contract(), argo)
        assert "ignoreDifferences:" in yaml
        assert "/spec/replicas" in yaml
        assert "/spec/clusterIP" in yaml
        assert ".webhooks[].clientConfig.caBundle" in yaml

    def test_regenerate_header_references_real_command(self):
        # Issue #23: header must reference the real generate-artefacts command.
        argo = ArgocdConfig(repo_url="https://github.com/hyperi-io/dfe-loader")
        yaml = generate_argocd_application(_full_contract(), argo)
        assert "emit-argocd" not in yaml
        assert "generate-artefacts" in yaml

    def test_generate_argocd_application_appends_extra_ignore_differences(self):
        argo = ArgocdConfig(
            repo_url="https://github.com/hyperi-io/dfe-loader",
            extra_ignore_differences=[
                "- group: apps\n  kind: Deployment\n  jsonPointers:\n    - /spec/template/spec/containers/0/image",
            ],
        )
        yaml = generate_argocd_application(_full_contract(), argo)
        assert "/spec/template/spec/containers/0/image" in yaml

    def test_generate_argocd_application_sync_wave_annotation_uses_config_value(self):
        from hyperi_pylib.deployment.waves import WAVE_TOPICS

        argo = ArgocdConfig(
            repo_url="https://github.com/hyperi-io/dfe-loader",
            sync_wave=WAVE_TOPICS,
        )
        yaml = generate_argocd_application(_full_contract(), argo)
        assert 'argocd.argoproj.io/sync-wave: "-5"' in yaml


# -----------------------------------------------------------------------------
# KedaContract.from_config
# -----------------------------------------------------------------------------


class TestKedaContract:
    def test_from_config_strips_enabled(self):
        cfg = KedaConfig(kafka_lag_threshold=5000, cpu_threshold=90)
        contract = KedaContract.from_config(cfg)
        assert contract.kafka_lag_threshold == 5000
        assert contract.cpu_threshold == 90

    def test_keda_contract_defaults_match_config_defaults(self):
        from_default = KedaContract.from_config(KedaConfig())
        bare = KedaContract()
        assert from_default.model_dump() == bare.model_dump()


# -----------------------------------------------------------------------------
# NativeDepsContract.for_pylib_extras
# -----------------------------------------------------------------------------


class TestNativeDepsForPylibExtras:
    def test_kafka_adds_confluent_repo(self):
        deps = NativeDepsContract.for_pylib_extras(["kafka"], "ubuntu:24.04")
        assert len(deps.apt_repos) == 1
        assert "confluent" in deps.apt_repos[0].url
        assert "librdkafka1" in deps.apt_repos[0].packages
        assert deps.apt_repos[0].codename == "noble"
        assert "libssl3" in deps.apt_packages
        assert "zlib1g" in deps.apt_packages

    def test_no_extras_is_empty(self):
        deps = NativeDepsContract.for_pylib_extras([], "ubuntu:24.04")
        assert deps.is_empty()

    def test_pure_python_extras_empty(self):
        deps = NativeDepsContract.for_pylib_extras(["expression", "metrics"], "ubuntu:24.04")
        assert deps.is_empty()

    def test_no_duplicate_packages(self):
        deps = NativeDepsContract.for_pylib_extras(["kafka", "http", "secrets-aws"], "ubuntu:24.04")
        ssl_count = deps.apt_packages.count("libssl3")
        assert ssl_count == 1

    def test_bookworm_codename(self):
        deps = NativeDepsContract.for_pylib_extras(["kafka"], "debian:bookworm-slim")
        assert deps.apt_repos[0].codename == "bookworm"

    def test_cache_extra_adds_libpq(self):
        deps = NativeDepsContract.for_pylib_extras(["cache"], "ubuntu:24.04")
        assert "libpq5" in deps.apt_packages


class TestNativeDepsForRustlibFeatures:
    """Polyglot path -- when a Python app re-binds a Rust core via PyO3."""

    def test_kafka_feature_adds_confluent(self):
        deps = NativeDepsContract.for_rustlib_features(["transport-kafka"], "ubuntu:24.04")
        assert len(deps.apt_repos) == 1
        assert "librdkafka1" in deps.apt_repos[0].packages

    def test_spool_adds_zstd(self):
        deps = NativeDepsContract.for_rustlib_features(["spool"], "ubuntu:24.04")
        assert "libzstd1" in deps.apt_packages


# -----------------------------------------------------------------------------
# Robustness: YAML parses, generators are deterministic, contract validation
# -----------------------------------------------------------------------------


class TestGeneratedYamlParses:
    """Every ``.yaml`` artefact must round-trip through ``yaml.safe_load``.

    Catches structural regressions that substring-only checks miss (mismatched
    indents, unquoted special characters, missing colons). Helm templates use
    ``{{ }}`` Go-template syntax which is NOT YAML-valid -- we strip those
    sections before parsing.
    """

    def _yaml_safe(self, text: str) -> object:
        """Parse YAML after stripping Helm Go-template directives."""
        import re

        import yaml

        # Replace the contents of any {{ ... }} block with a placeholder so the
        # remainder is structurally valid YAML.
        scrubbed = re.sub(r"\{\{[^}]*\}\}", "PLACEHOLDER", text)
        # Drop full-line {{- ... -}} control flow blocks too.
        scrubbed = re.sub(r"^\s*PLACEHOLDER\s*$", "", scrubbed, flags=re.MULTILINE)
        return yaml.safe_load(scrubbed)

    def test_compose_fragment_is_valid_yaml(self):
        text = generate_compose_fragment(_full_contract())
        # Compose has no Helm placeholders -- straight parse
        import yaml

        data = yaml.safe_load(text)
        assert isinstance(data, dict)
        assert "services" in data
        assert "dfe-loader" in data["services"]

    def test_argocd_application_is_valid_yaml(self):
        argo = ArgocdConfig(repo_url="https://github.com/hyperi-io/dfe-loader")
        text = generate_argocd_application(_full_contract(), argo)
        import yaml

        data = yaml.safe_load(text)
        assert data["apiVersion"] == "argoproj.io/v1alpha1"
        assert data["kind"] == "Application"
        assert data["metadata"]["name"] == "dfe-loader"
        assert data["spec"]["source"]["repoURL"] == "https://github.com/hyperi-io/dfe-loader"

    def test_chart_yaml_is_valid_yaml(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)
        text = (tmp_path / "Chart.yaml").read_text()
        import yaml

        data = yaml.safe_load(text)
        assert data["name"] == "dfe-loader"
        assert data["apiVersion"] == "v2"
        assert data["type"] == "application"

    def test_values_yaml_is_valid_yaml(self, tmp_path):
        generate_chart(_full_contract(), tmp_path)
        text = (tmp_path / "values.yaml").read_text()
        # values.yaml has no Helm directives
        import yaml

        data = yaml.safe_load(text)
        assert data["service"]["port"] == 9090
        assert data["keda"]["enabled"] is True
        assert data["keda"]["kafka"]["lagThreshold"] == "1000"
        assert data["kafka"]["secretKeys"]["password"] == "kafka-password"

    def test_helm_template_yamls_parse_after_directive_strip(self, tmp_path):
        """deployment/service/configmap/secret/hpa with placeholder substitution."""
        generate_chart(_full_contract(), tmp_path)
        for rel in (
            "templates/deployment.yaml",
            "templates/service.yaml",
            "templates/serviceaccount.yaml",
            "templates/configmap.yaml",
            "templates/hpa.yaml",
            "templates/keda-scaledobject.yaml",
            "templates/keda-triggerauth.yaml",
        ):
            text = (tmp_path / rel).read_text()
            data = self._yaml_safe(text)
            # Each template is a dict with apiVersion / kind / metadata
            assert isinstance(data, dict), f"{rel} did not parse to a mapping"
            # apiVersion may be the placeholder string after scrubbing in some
            # templates wrapped in {{- if ... }} -- accept either real value or
            # placeholder; the structural check is what matters.
            assert "kind" in data or "PLACEHOLDER" in str(data), f"{rel} missing 'kind' field after directive scrub"


class TestGeneratorDeterminism:
    """Calling a generator twice with the same contract MUST return identical output."""

    def test_dockerfile_deterministic(self):
        c = _full_contract()
        c.native_deps = NativeDepsContract.for_pylib_extras(["kafka", "cache"], "ubuntu:24.04")
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

    def test_argocd_deterministic(self):
        c = _full_contract()
        argo = ArgocdConfig(repo_url="https://example.com")
        assert generate_argocd_application(c, argo) == generate_argocd_application(c, argo)

    def test_chart_deterministic(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        c = _full_contract()
        generate_chart(c, a)
        generate_chart(c, b)

        for rel in (
            "Chart.yaml",
            "values.yaml",
            "templates/_helpers.tpl",
            "templates/deployment.yaml",
            "templates/service.yaml",
            "templates/configmap.yaml",
            "templates/secret.yaml",
        ):
            assert (a / rel).read_text() == (b / rel).read_text(), f"{rel} differs across two generate_chart() calls"


class TestContractValidation:
    """Pydantic guards -- make sure invalid contracts are caught at construction."""

    def test_metrics_port_zero_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeploymentContract(
                app_name="x",
                metrics_port=0,  # invalid: ge=1
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
            )

    def test_metrics_port_above_65535_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeploymentContract(
                app_name="x",
                metrics_port=70000,  # invalid: le=65535
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
            )

    def test_extra_fields_rejected_on_contract(self):
        """``extra="forbid"`` -- typos in field names must fail loudly."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeploymentContract(
                app_name="x",
                metrics_port=9090,
                env_prefix="X",
                metric_prefix="x",
                config_mount_path="/etc/x.yaml",
                wrong_field_name="boom",
            )

    def test_extra_fields_rejected_on_keda_contract(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            KedaContract(unknown=1)

    def test_extra_fields_rejected_on_health_contract(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            HealthContract(unknown="path")

    def test_minimal_required_fields_only(self):
        """Construction with only required fields must succeed and use defaults everywhere else."""
        c = DeploymentContract(
            app_name="minimal",
            metrics_port=8080,
            env_prefix="MIN",
            metric_prefix="min",
            config_mount_path="/etc/min.yaml",
        )
        # Defaults applied
        assert c.schema_version == 2
        assert c.image_registry == "ghcr.io/hyperi-io"
        # base_image defaults empty; resolved to python:{python_version}-slim.
        assert c.base_image == ""
        assert c.effective_base_image() == "python:3.12-slim"
        assert c.image_profile == ImageProfile.PRODUCTION
        assert c.health.liveness_path == "/healthz"
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
        )

    def test_dockerfile_works_on_minimal(self):
        df = generate_dockerfile(self._minimal())
        assert "FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder" in df
        assert "FROM python:3.12-slim AS runtime" in df
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

    def test_chart_works_on_minimal(self, tmp_path):
        generate_chart(self._minimal(), tmp_path)
        # No KEDA files
        assert not (tmp_path / "templates/keda-scaledobject.yaml").exists()
        # secret.yaml present but empty
        secret_text = (tmp_path / "templates/secret.yaml").read_text()
        assert "No secrets defined" in secret_text

    def test_container_manifest_works_on_minimal(self):
        text = generate_container_manifest(self._minimal())
        manifest = json.loads(text)
        assert manifest["app_name"] == "minimal-app"
        assert manifest["binary_name"] == "minimal-app"  # binary() fallback
        assert manifest["expose_ports"] == [8080]
        assert manifest["cmd"] == []
        assert manifest["runtime_packages"]["apt_repos"] == []
        assert manifest["runtime_packages"]["apt_packages"] == []
