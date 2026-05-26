# Project:   hyperi-pylib
# File:      deployment/generate.py
# Purpose:   Generate deployment artefacts from DeploymentContract
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Generate deployment artefacts from a ``DeploymentContract``.

Mirrors rustlib's ``hyperi_rustlib::deployment::generate``.

Apps provide ~20% customisation (ports, secrets, config); this module
generates ~80% boilerplate (Dockerfile, runtime stage fragment, container
manifest JSON, Compose fragment, full Helm chart, ArgoCD ``Application``).

For byte-level cross-language parity with rustlib's ``format!()`` macros, we
use raw Python f-strings rather than a templating engine. ``json.dumps`` is
used only for the container manifest where ``serde_json::to_string_pretty`` is
the rustlib equivalent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .contract import DeploymentContract, ImageProfile
from .contract_identity import ContractIdentity
from .errors import CreateDirError, WriteFileError
from .native_deps import NativeDepsContract
from .waves import WAVE_APPS

# ============================================================================
# Helpers
# ============================================================================

# Diagnostic tools installed in development images.
_DEV_TOOLS = (
    "bash",
    "strace",
    "tcpdump",
    "procps",
    "dnsutils",
    "net-tools",
    "less",
    "jq",
)


def _profile_label(profile: ImageProfile) -> str:
    """Map ImageProfile to its lowercase string label."""
    return "production" if profile == ImageProfile.PRODUCTION else "development"


def _expose_ports(contract: DeploymentContract) -> str:
    """Build the ``EXPOSE`` line: metrics_port + extra ports."""
    ports = [str(contract.metrics_port)] + [str(p.port) for p in contract.extra_ports]
    return " ".join(ports)


def _cmd_line(contract: DeploymentContract) -> str:
    """Build the ``CMD [...]`` line, or empty string when no args."""
    if not contract.entrypoint_args:
        return ""
    args = ", ".join(f'"{a}"' for a in contract.entrypoint_args)
    return f"\nCMD [{args}]"


def to_camel_suffix(name: str) -> str:
    """Convert ``foo_bar`` / ``foo-bar`` to ``fooBar`` (used for Helm secret helpers)."""
    out: list[str] = []
    capitalize_next = False
    for ch in name:
        if ch in ("_", "-"):
            capitalize_next = True
        elif capitalize_next:
            out.append(ch.upper())
            capitalize_next = False
        else:
            out.append(ch)
    return "".join(out)


def _build_apt_block(deps: NativeDepsContract, profile: ImageProfile) -> str:
    """Build the apt-get RUN block from native deps contract and image profile.

    When custom APT repos are needed (e.g., Confluent for librdkafka), emits
    the GPG key download, sources list entry, and repo-specific packages.
    Development profile adds diagnostic tools.
    """
    is_dev = profile == ImageProfile.DEVELOPMENT

    base_pkgs = ["ca-certificates", "curl", "netcat-openbsd", "iputils-ping"]
    if deps.apt_repos:
        base_pkgs.append("gnupg")
    if is_dev:
        base_pkgs.extend(_DEV_TOOLS)

    if deps.is_empty():
        return (
            "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
            f"    {' '.join(base_pkgs)} \\\n"
            "    && rm -rf /var/lib/apt/lists/*\n"
        )

    runtime_pkgs: list[str] = []
    for repo in deps.apt_repos:
        runtime_pkgs.extend(repo.packages)
    runtime_pkgs.extend(deps.apt_packages)

    parts: list[str] = []
    parts.append("# Runtime shared libraries for dynamically-linked extensions.\n")
    parts.append("RUN apt-get update && apt-get install -y --no-install-recommends \\\n")
    parts.append(f"    {' '.join(base_pkgs)} \\\n")

    for repo in deps.apt_repos:
        keyring_stem = Path(repo.keyring).stem or "custom-repo"
        parts.append(
            f"    && curl -fsSL {repo.key_url} \\\n"
            f"       | gpg --dearmor -o {repo.keyring} \\\n"
            f'    && echo "deb [signed-by={repo.keyring}] \\\n'
            f'       {repo.url} {repo.codename} main" \\\n'
            f"       > /etc/apt/sources.list.d/{keyring_stem}.list \\\n"
        )

    parts.append("    && apt-get update && apt-get install -y --no-install-recommends \\\n")
    parts.append(f"       {' '.join(runtime_pkgs)} \\\n")
    parts.append("    && rm -rf /var/lib/apt/lists/*\n")
    return "".join(parts)


# ============================================================================
# Dockerfile
# ============================================================================


def generate_dockerfile(
    contract: DeploymentContract,
    *,
    identity: ContractIdentity | None = None,
) -> str:
    """Generate a complete Dockerfile from the deployment contract.

    Mirrors rustlib's ``generate_dockerfile``. When ``native_deps`` is
    populated, the generated Dockerfile automatically includes custom APT repo
    setup and runtime package installation.

    When ``identity`` is provided, the Contract Identity Annotation Scheme v1
    keys are emitted as ``LABEL`` directives directly after the profile
    label. Pass ``None`` (the default) to preserve pre-identity output.
    """
    binary = contract.binary()
    apt_block = _build_apt_block(contract.native_deps, contract.image_profile)
    profile_label = _profile_label(contract.image_profile)
    expose = _expose_ports(contract)
    cmd = _cmd_line(contract)
    identity_block = "" if identity is None else f"{identity.as_dockerfile_labels()}\n"

    return (
        f"# Project:   {contract.app_name}\n"
        f"# File:      Dockerfile\n"
        f"# Purpose:   {profile_label} container image\n"
        f"#\n"
        f"# License:   FSL-1.1-ALv2\n"
        f"# Copyright: (c) 2026 HYPERI PTY LIMITED\n"
        f"#\n"
        f"# AUTOGENERATED — do not edit by hand.\n"
        f"# Generated by hyperi_pylib.deployment.generate_dockerfile()\n"
        f"# Schema version: {contract.schema_version}\n"
        f"# Source contract: {contract.app_name}::deployment::contract()\n"
        f"# Regenerate with: `{binary} emit-dockerfile > Dockerfile`\n"
        f"\n"
        f"FROM {contract.base_image}\n"
        f"\n"
        f'LABEL io.hyperi.profile="{profile_label}"\n'
        f"{identity_block}"
        f"\n"
        f"{apt_block}"
        f"COPY {binary} /usr/local/bin/{binary}\n"
        f"RUN chmod +x /usr/local/bin/{binary}\n"
        f"\n"
        f"# Ubuntu 24.04 ships with ubuntu user at UID 1000 — remove before creating appuser\n"
        f"RUN userdel -r ubuntu && useradd --create-home --uid 1000 appuser\n"
        f"USER appuser\n"
        f"\n"
        f"EXPOSE {expose}\n"
        f"\n"
        f"HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\\n"
        f"    CMD curl -sf http://localhost:{contract.metrics_port}{contract.health.liveness_path} > /dev/null || exit 1\n"
        f"\n"
        f'ENTRYPOINT ["{binary}"]{cmd}\n'
    )


# ============================================================================
# Container manifest (CI-consumable JSON)
# ============================================================================


def generate_container_manifest(
    contract: DeploymentContract,
    *,
    identity: ContractIdentity | None = None,
) -> str:
    """Generate a container manifest JSON for CI consumption.

    Mirrors rustlib's ``generate_container_manifest``. Output is the minimal
    subset of the deployment contract that CI needs to build the container
    image — no secrets, no K8s-specific config.

    When ``identity`` is provided, the three Contract Identity Annotation
    Scheme v1 keys are added to the ``labels`` dict. Pass ``None`` (the
    default) to preserve pre-identity output.
    """
    binary = contract.binary()
    profile_str = _profile_label(contract.image_profile)
    title = contract.oci_labels.title or contract.app_name

    apt_repos = [
        {
            "key_url": r.key_url,
            "keyring": r.keyring,
            "url": r.url,
            "codename": r.codename,
            "packages": list(r.packages),
        }
        for r in contract.native_deps.apt_repos
    ]

    expose_ports = [contract.metrics_port] + [p.port for p in contract.extra_ports]

    manifest = {
        "schema_version": "1",
        "app_name": contract.app_name,
        "binary_name": binary,
        "base_image": contract.base_image,
        "image_registry": contract.image_registry,
        "image_profile": profile_str,
        "runtime_packages": {
            "apt_repos": apt_repos,
            "apt_packages": list(contract.native_deps.apt_packages),
        },
        "expose_ports": expose_ports,
        "healthcheck": {
            "path": contract.health.liveness_path,
            "port": contract.metrics_port,
            "interval": "30s",
            "timeout": "3s",
            "start_period": "5s",
            "retries": 3,
        },
        "entrypoint": [binary],
        "cmd": list(contract.entrypoint_args),
        "user": "appuser",
        "uid": 1000,
        "labels": {
            "io.hyperi.profile": profile_str,
            "io.hyperi.app": contract.app_name,
            "io.hyperi.metrics_port": str(contract.metrics_port),
            "org.opencontainers.image.title": title,
            "org.opencontainers.image.description": contract.oci_labels.description,
            "org.opencontainers.image.vendor": contract.oci_labels.vendor,
            "org.opencontainers.image.licenses": contract.oci_labels.licenses,
        },
    }

    if identity is not None:
        manifest["labels"].update(
            {
                "io.hyperi.contract.version": "v1",
                "io.hyperi.contract.source-commit": identity.source_commit,
                "io.hyperi.contract.image-ref": identity.image_ref,
            }
        )

    return json.dumps(manifest, indent=2, sort_keys=False)


# ============================================================================
# Runtime stage fragment (for CI Dockerfile composition)
# ============================================================================


def generate_runtime_stage(
    contract: DeploymentContract,
    *,
    identity: ContractIdentity | None = None,
) -> str:
    """Generate only the runtime stage of a Dockerfile as a fragment.

    Mirrors rustlib's ``generate_runtime_stage``. CI composes the full
    Dockerfile by prepending its own build stages (cargo-chef pattern for
    Rust, multi-stage Python builds with ``uv sync`` for Python) and appending
    this runtime stage.

    When ``identity`` is provided, the Contract Identity Annotation Scheme v1
    keys are emitted as ``LABEL`` directives directly after the profile
    label. Pass ``None`` (the default) to preserve pre-identity output.
    """
    binary = contract.binary()
    apt_block = _build_apt_block(contract.native_deps, contract.image_profile)
    profile_label = _profile_label(contract.image_profile)
    title = contract.oci_labels.title or contract.app_name
    expose = _expose_ports(contract)
    cmd = _cmd_line(contract)
    identity_block = "" if identity is None else f"{identity.as_dockerfile_labels()}\n"

    return (
        f"# --- Runtime stage (generated by hyperi-pylib deployment contract) ---\n"
        f"FROM {contract.base_image} AS runtime\n"
        f"\n"
        f"# Static OCI labels (from contract)\n"
        f'LABEL org.opencontainers.image.title="{title}"\n'
        f'LABEL org.opencontainers.image.description="{contract.oci_labels.description}"\n'
        f'LABEL org.opencontainers.image.vendor="{contract.oci_labels.vendor}"\n'
        f'LABEL org.opencontainers.image.licenses="{contract.oci_labels.licenses}"\n'
        f'LABEL io.hyperi.profile="{profile_label}"\n'
        f"{identity_block}"
        f"\n"
        f"{apt_block}"
        f"# Dynamic OCI labels (injected by CI at build time)\n"
        f'ARG OCI_SOURCE=""\n'
        f'ARG OCI_REVISION=""\n'
        f'ARG OCI_VERSION=""\n'
        f'ARG OCI_CREATED=""\n'
        f'LABEL org.opencontainers.image.source="${{OCI_SOURCE}}"\n'
        f'LABEL org.opencontainers.image.revision="${{OCI_REVISION}}"\n'
        f'LABEL org.opencontainers.image.version="${{OCI_VERSION}}"\n'
        f'LABEL org.opencontainers.image.created="${{OCI_CREATED}}"\n'
        f"\n"
        f"COPY --from=builder /app/target/release/{binary} /usr/local/bin/{binary}\n"
        f"RUN chmod +x /usr/local/bin/{binary}\n"
        f"\n"
        f"RUN userdel -r ubuntu && useradd --create-home --uid 1000 appuser\n"
        f"USER appuser\n"
        f"\n"
        f"EXPOSE {expose}\n"
        f"\n"
        f"HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\\n"
        f"    CMD curl -sf http://localhost:{contract.metrics_port}{contract.health.liveness_path} > /dev/null || exit 1\n"
        f"\n"
        f'ENTRYPOINT ["{binary}"]{cmd}\n'
    )


# ============================================================================
# Docker Compose fragment
# ============================================================================


def generate_compose_fragment(contract: DeploymentContract) -> str:
    """Generate a Docker Compose service fragment from the deployment contract.

    Mirrors rustlib's ``generate_compose_fragment``.
    """
    binary = contract.binary()
    parts: list[str] = []

    parts.append("# Generated by hyperi-pylib deployment module\n")
    parts.append(f"services:\n  {contract.app_name}:\n")

    env_var = contract.env_prefix.replace("__", "_")
    parts.append(f"    image: {contract.image_registry}/{contract.app_name}:${{{env_var}_VERSION:-latest}}\n")

    if contract.depends_on:
        parts.append("    depends_on:\n")
        for dep in contract.depends_on:
            parts.append(f"      {dep}:\n        condition: service_healthy\n")

    parts.append("    ports:\n")
    parts.append(f'      - "{contract.metrics_port}:{contract.metrics_port}"\n')
    for p in contract.extra_ports:
        parts.append(f'      - "{p.port}:{p.port}"\n')

    parts.append("    volumes:\n")
    parts.append(f"      - ./config/{contract.config_filename()}:{contract.config_mount_path}:ro\n")

    parts.append(
        f"    healthcheck:\n"
        f'      test: ["CMD", "curl", "-sf", "http://localhost:{contract.metrics_port}{contract.health.liveness_path}"]\n'
        f"      interval: 10s\n"
        f"      timeout: 3s\n"
        f"      retries: 5\n"
    )

    if contract.entrypoint_args:
        args = ", ".join(f'"{a}"' for a in contract.entrypoint_args)
        parts.append(f'    command: ["{binary}", {args}]\n')

    return "".join(parts)


# ============================================================================
# Helm chart
# ============================================================================


def generate_chart(
    contract: DeploymentContract,
    output_dir: Path | str,
    *,
    identity: ContractIdentity | None = None,
) -> None:
    """Generate a complete Helm chart directory from the deployment contract.

    Writes ``Chart.yaml``, ``values.yaml``, and all template files to
    ``output_dir``. Mirrors rustlib's ``generate_chart``.

    When ``identity`` is provided, ``Chart.yaml`` carries the three Contract
    Identity Annotation Scheme v1 keys under a top-level ``annotations:``
    block. Pass ``None`` (the default) to preserve pre-identity output.
    """
    out = Path(output_dir)
    templates = out / "templates"
    try:
        templates.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise CreateDirError(str(templates), e)

    _write_file(out / "Chart.yaml", _gen_chart_yaml(contract, identity))
    _write_file(out / "values.yaml", _gen_values_yaml(contract))
    _write_file(templates / "_helpers.tpl", _gen_helpers_tpl(contract))
    _write_file(templates / "deployment.yaml", _gen_deployment_yaml(contract))
    _write_file(templates / "service.yaml", _gen_service_yaml(contract))
    _write_file(templates / "serviceaccount.yaml", _gen_serviceaccount_yaml(contract))
    _write_file(templates / "configmap.yaml", _gen_configmap_yaml(contract))
    _write_file(templates / "secret.yaml", _gen_secret_yaml(contract))
    _write_file(templates / "hpa.yaml", _gen_hpa_yaml(contract))

    if contract.keda is not None:
        _write_file(templates / "keda-scaledobject.yaml", _gen_keda_scaledobject_yaml(contract))
        _write_file(templates / "keda-triggerauth.yaml", _gen_keda_triggerauth_yaml(contract))

    _write_file(templates / "NOTES.txt", _gen_notes_txt(contract))


def _write_file(path: Path, content: str) -> None:
    try:
        path.write_text(content)
    except OSError as e:
        raise WriteFileError(str(path), e)


# ---- Chart file generators --------------------------------------------------


def _gen_chart_yaml(
    c: DeploymentContract,
    identity: ContractIdentity | None = None,
) -> str:
    desc = c.description if c.description else c.app_name
    annotations_block = ""
    if identity is not None:
        annotations_block = f"\nannotations:\n{identity.as_yaml_annotations(indent=2)}\n"
    return (
        f"apiVersion: v2\n"
        f"name: {c.app_name}\n"
        f"description: {desc}\n"
        f"type: application\n"
        f"version: 0.1.0\n"
        f'appVersion: "1.0.0"\n'
        f"{annotations_block}"
        f"\n"
        f"keywords:\n"
        f"  - hyperi\n"
        f"  - dfe\n"
        f"\n"
        f"maintainers:\n"
        f"  - name: HyperI\n"
        f"    url: https://github.com/hyperi-io\n"
    )


def _gen_values_yaml(c: DeploymentContract) -> str:
    parts: list[str] = []

    parts.append(
        f"# {c.app_name} Helm chart values\n"
        f"#\n"
        f"# Generated by hyperi-pylib deployment module.\n"
        f"# Contract points validated by pytest.\n"
        f"\n"
    )

    parts.append(
        f"# -- Number of replicas (ignored when KEDA is enabled)\n"
        f"replicaCount: 1\n"
        f"\n"
        f"image:\n"
        f"  repository: {c.image_registry}/{c.app_name}\n"
        f"  # -- Defaults to Chart appVersion\n"
        f'  tag: ""\n'
        f"  pullPolicy: IfNotPresent\n"
        f"\n"
        f"imagePullSecrets: []\n"
        f'nameOverride: ""\n'
        f'fullnameOverride: ""\n'
        f"\n"
    )

    parts.append(
        "serviceAccount:\n"
        "  create: true\n"
        "  annotations: {}\n"
        "  # -- If not set, name is generated from fullname\n"
        '  name: ""\n'
        "\n"
    )

    parts.append(
        f"# -- Pod annotations (Prometheus scrape config included by default)\n"
        f"podAnnotations:\n"
        f'  prometheus.io/scrape: "true"\n'
        f'  prometheus.io/port: "{c.metrics_port}"\n'
        f'  prometheus.io/path: "{c.health.metrics_path}"\n'
        f"\n"
        f"podLabels: {{}}\n"
        f"\n"
    )

    parts.append(
        'resources:\n  requests:\n    cpu: 250m\n    memory: 256Mi\n  limits:\n    cpu: "2"\n    memory: 1Gi\n\n'
    )

    parts.append(f"# -- Metrics and health endpoint service\nservice:\n  type: ClusterIP\n  port: {c.metrics_port}\n\n")

    parts.append(f"# -- Application configuration (mounted as {c.config_mount_path})\n")
    if c.default_config is not None:
        parts.append("config:\n")
        # Lazy-import yaml so the deployment module doesn't hard-require it
        # for projects that never call generate_chart with a default_config.
        try:
            import yaml  # type: ignore[import-not-found]

            yaml_str = yaml.safe_dump(c.default_config, default_flow_style=False, sort_keys=False)
            for line in yaml_str.splitlines():
                if line == "---":
                    continue
                parts.append(f"  {line}\n")
        except ImportError as e:  # pragma: no cover — pyyaml is a core dep
            raise WriteFileError("values.yaml (default_config)", e)
    else:
        parts.append("config: {}\n")
    parts.append("\n")

    for group in c.secrets:
        parts.append(f'# -- {group.group_name} credentials\n{group.group_name}:\n  existingSecret: ""\n  secretKeys:\n')
        for env in group.env_vars:
            parts.append(f"    {env.key_name}: {env.secret_key}\n")
        for env in group.env_vars:
            parts.append(f'  {env.key_name}: ""\n')
        parts.append("\n")

    if c.keda is not None:
        parts.append(
            f"# -- KEDA autoscaling (requires KEDA operator installed)\n"
            f"keda:\n"
            f"  enabled: true\n"
            f"  minReplicaCount: {c.keda.min_replicas}\n"
            f"  maxReplicaCount: {c.keda.max_replicas}\n"
            f"  pollingInterval: {c.keda.polling_interval}\n"
            f"  cooldownPeriod: {c.keda.cooldown_period}\n"
            f"  kafka:\n"
            f"    # -- Scale when consumer group lag exceeds this per partition\n"
            f'    lagThreshold: "{c.keda.kafka_lag_threshold}"\n'
            f"    # -- Wake from zero replicas when lag exceeds this\n"
            f'    activationLagThreshold: "{c.keda.activation_lag_threshold}"\n'
            f"    # -- Override topic (default: first topic from config)\n"
            f'    topic: ""\n'
            f"    # -- Override consumer group (default: from config)\n"
            f'    consumerGroup: ""\n'
            f"  cpu:\n"
            f"    enabled: {str(c.keda.cpu_enabled).lower()}\n"
            f"    # -- CPU utilisation percentage threshold\n"
            f'    threshold: "{c.keda.cpu_threshold}"\n'
            f"\n"
        )

    parts.append(
        "# -- Standard HPA fallback (when KEDA is not installed)\n"
        "# Mutually exclusive with keda.enabled\n"
        "autoscaling:\n"
        "  enabled: false\n"
        "  minReplicas: 1\n"
        "  maxReplicas: 10\n"
        "  targetCPUUtilizationPercentage: 80\n"
        "\n"
        "nodeSelector: {}\n"
        "tolerations: []\n"
        "affinity: {}\n"
    )

    return "".join(parts)


def _gen_helpers_tpl(c: DeploymentContract) -> str:
    app = c.app_name
    parts: list[str] = []

    parts.append(
        f"{{{{/*\n"
        f"Expand the name of the chart.\n"
        f"*/}}}}\n"
        f'{{{{- define "{app}.name" -}}}}\n'
        f'{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}\n'
        f"{{{{- end }}}}\n"
        f"\n"
        f"{{{{/*\n"
        f"Create a default fully qualified app name.\n"
        f"Truncated at 63 chars because some K8s name fields are limited.\n"
        f"*/}}}}\n"
        f'{{{{- define "{app}.fullname" -}}}}\n'
        f"{{{{- if .Values.fullnameOverride }}}}\n"
        f'{{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}}}\n'
        f"{{{{- else }}}}\n"
        f"{{{{- $name := default .Chart.Name .Values.nameOverride }}}}\n"
        f"{{{{- if contains $name .Release.Name }}}}\n"
        f'{{{{- .Release.Name | trunc 63 | trimSuffix "-" }}}}\n'
        f"{{{{- else }}}}\n"
        f'{{{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}}}\n'
        f"{{{{- end }}}}\n"
        f"{{{{- end }}}}\n"
        f"{{{{- end }}}}\n"
        f"\n"
        f"{{{{/*\n"
        f"Create chart name and version as used by the chart label.\n"
        f"*/}}}}\n"
        f'{{{{- define "{app}.chart" -}}}}\n'
        f'{{{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}}}\n'
        f"{{{{- end }}}}\n"
        f"\n"
        f"{{{{/*\n"
        f"Common labels.\n"
        f"*/}}}}\n"
        f'{{{{- define "{app}.labels" -}}}}\n'
        f'helm.sh/chart: {{{{ include "{app}.chart" . }}}}\n'
        f'{{{{ include "{app}.selectorLabels" . }}}}\n'
        f"{{{{- if .Chart.AppVersion }}}}\n"
        f"app.kubernetes.io/version: {{{{ .Chart.AppVersion | quote }}}}\n"
        f"{{{{- end }}}}\n"
        f"app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}\n"
        f"{{{{- end }}}}\n"
        f"\n"
        f"{{{{/*\n"
        f"Selector labels.\n"
        f"*/}}}}\n"
        f'{{{{- define "{app}.selectorLabels" -}}}}\n'
        f'app.kubernetes.io/name: {{{{ include "{app}.name" . }}}}\n'
        f"app.kubernetes.io/instance: {{{{ .Release.Name }}}}\n"
        f"{{{{- end }}}}\n"
        f"\n"
        f"{{{{/*\n"
        f"Service account name.\n"
        f"*/}}}}\n"
        f'{{{{- define "{app}.serviceAccountName" -}}}}\n'
        f"{{{{- if .Values.serviceAccount.create }}}}\n"
        f'{{{{- default (include "{app}.fullname" .) .Values.serviceAccount.name }}}}\n'
        f"{{{{- else }}}}\n"
        f'{{{{- default "default" .Values.serviceAccount.name }}}}\n'
        f"{{{{- end }}}}\n"
        f"{{{{- end }}}}\n"
    )

    for group in c.secrets:
        helper = f"{to_camel_suffix(group.group_name)}SecretName"
        parts.append(
            f"\n"
            f"{{{{/*\n"
            f"{group.group_name} secret name — use existing or generate from fullname.\n"
            f"*/}}}}\n"
            f'{{{{- define "{app}.{helper}" -}}}}\n'
            f"{{{{- if .Values.{group.group_name}.existingSecret }}}}\n"
            f"{{{{- .Values.{group.group_name}.existingSecret }}}}\n"
            f"{{{{- else }}}}\n"
            f'{{{{- printf "%s-{group.group_name}" (include "{app}.fullname" .) }}}}\n'
            f"{{{{- end }}}}\n"
            f"{{{{- end }}}}\n"
        )

    return "".join(parts)


def _gen_deployment_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    parts: list[str] = []

    parts.append(
        f"apiVersion: apps/v1\n"
        f"kind: Deployment\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.fullname" . }}}}\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"spec:\n"
        f"  {{{{- if not (or .Values.keda.enabled .Values.autoscaling.enabled) }}}}\n"
        f"  replicas: {{{{ .Values.replicaCount }}}}\n"
        f"  {{{{- end }}}}\n"
        f"  selector:\n"
        f"    matchLabels:\n"
        f'      {{{{- include "{app}.selectorLabels" . | nindent 6 }}}}\n'
        f"  template:\n"
        f"    metadata:\n"
        f"      annotations:\n"
        f'        checksum/config: {{{{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}}}\n'
        f"        {{{{- with .Values.podAnnotations }}}}\n"
        f"        {{{{- toYaml . | nindent 8 }}}}\n"
        f"        {{{{- end }}}}\n"
        f"      labels:\n"
        f'        {{{{- include "{app}.labels" . | nindent 8 }}}}\n'
        f"        {{{{- with .Values.podLabels }}}}\n"
        f"        {{{{- toYaml . | nindent 8 }}}}\n"
        f"        {{{{- end }}}}\n"
        f"    spec:\n"
        f"      {{{{- with .Values.imagePullSecrets }}}}\n"
        f"      imagePullSecrets:\n"
        f"        {{{{- toYaml . | nindent 8 }}}}\n"
        f"      {{{{- end }}}}\n"
        f'      serviceAccountName: {{{{ include "{app}.serviceAccountName" . }}}}\n'
        f"      containers:\n"
        f"        - name: {{{{ .Chart.Name }}}}\n"
        f'          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag | default .Chart.AppVersion }}}}"\n'
        f"          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}\n"
    )

    if c.entrypoint_args:
        parts.append("          args:\n")
        for arg in c.entrypoint_args:
            parts.append(f'            - "{arg}"\n')

    parts.append(
        "          ports:\n"
        "            - name: metrics\n"
        "              containerPort: {{ .Values.service.port }}\n"
        "              protocol: TCP\n"
    )
    for port in c.extra_ports:
        parts.append(
            f"            - name: {port.name}\n"
            f"              containerPort: {port.port}\n"
            f"              protocol: {port.protocol}\n"
        )

    if c.secrets:
        parts.append("          env:\n")
        for group in c.secrets:
            helper = f"{to_camel_suffix(group.group_name)}SecretName"
            parts.append(
                f"            # {group.group_name} credentials via Secret (figment env cascade overrides file config)\n"
            )
            for env in group.env_vars:
                parts.append(
                    f"            - name: {env.env_var}\n"
                    f"              valueFrom:\n"
                    f"                secretKeyRef:\n"
                    f'                  name: {{{{ include "{app}.{helper}" . }}}}\n'
                    f"                  key: {{{{ .Values.{group.group_name}.secretKeys.{env.key_name} }}}}\n"
                )

    parts.append(
        f"          livenessProbe:\n"
        f"            httpGet:\n"
        f"              path: {c.health.liveness_path}\n"
        f"              port: metrics\n"
        f"            initialDelaySeconds: 10\n"
        f"            periodSeconds: 10\n"
        f"            failureThreshold: 3\n"
        f"          readinessProbe:\n"
        f"            httpGet:\n"
        f"              path: {c.health.readiness_path}\n"
        f"              port: metrics\n"
        f"            initialDelaySeconds: 5\n"
        f"            periodSeconds: 5\n"
        f"            failureThreshold: 2\n"
        f"          startupProbe:\n"
        f"            httpGet:\n"
        f"              path: {c.health.liveness_path}\n"
        f"              port: metrics\n"
        f"            failureThreshold: 30\n"
        f"            periodSeconds: 5\n"
    )

    parts.append(
        f"          volumeMounts:\n"
        f"            - name: config\n"
        f"              mountPath: {c.config_dir()}\n"
        f"              readOnly: true\n"
    )

    parts.append(
        "          {{- with .Values.resources }}\n"
        "          resources:\n"
        "            {{- toYaml . | nindent 12 }}\n"
        "          {{- end }}\n"
    )

    parts.append(
        f"      volumes:\n"
        f"        - name: config\n"
        f"          configMap:\n"
        f'            name: {{{{ include "{app}.fullname" . }}}}-config\n'
    )

    parts.append(
        "      {{- with .Values.nodeSelector }}\n"
        "      nodeSelector:\n"
        "        {{- toYaml . | nindent 8 }}\n"
        "      {{- end }}\n"
        "      {{- with .Values.affinity }}\n"
        "      affinity:\n"
        "        {{- toYaml . | nindent 8 }}\n"
        "      {{- end }}\n"
        "      {{- with .Values.tolerations }}\n"
        "      tolerations:\n"
        "        {{- toYaml . | nindent 8 }}\n"
        "      {{- end }}\n"
    )

    return "".join(parts)


def _gen_service_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    parts: list[str] = []
    parts.append(
        f"apiVersion: v1\n"
        f"kind: Service\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.fullname" . }}}}\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"spec:\n"
        f"  type: {{{{ .Values.service.type }}}}\n"
        f"  ports:\n"
        f"    - port: {{{{ .Values.service.port }}}}\n"
        f"      targetPort: metrics\n"
        f"      protocol: TCP\n"
        f"      name: metrics\n"
    )
    for port in c.extra_ports:
        parts.append(
            f"    - port: {port.port}\n"
            f"      targetPort: {port.port}\n"
            f"      protocol: {port.protocol}\n"
            f"      name: {port.name}\n"
        )
    parts.append(f'  selector:\n    {{{{- include "{app}.selectorLabels" . | nindent 4 }}}}\n')
    return "".join(parts)


def _gen_serviceaccount_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    return (
        f"{{{{- if .Values.serviceAccount.create -}}}}\n"
        f"apiVersion: v1\n"
        f"kind: ServiceAccount\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.serviceAccountName" . }}}}\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"  {{{{- with .Values.serviceAccount.annotations }}}}\n"
        f"  annotations:\n"
        f"    {{{{- toYaml . | nindent 4 }}}}\n"
        f"  {{{{- end }}}}\n"
        f"automountServiceAccountToken: false\n"
        f"{{{{- end }}}}\n"
    )


def _gen_configmap_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    return (
        f"apiVersion: v1\n"
        f"kind: ConfigMap\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.fullname" . }}}}-config\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"data:\n"
        f"  {c.config_filename()}: |\n"
        f"    {{{{- toYaml .Values.config | nindent 4 }}}}\n"
    )


def _gen_secret_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    parts: list[str] = []
    first = True
    for group in c.secrets:
        if not first:
            parts.append("---\n")
        first = False
        helper = f"{to_camel_suffix(group.group_name)}SecretName"
        parts.append(
            f"{{{{- if not .Values.{group.group_name}.existingSecret }}}}\n"
            f"apiVersion: v1\n"
            f"kind: Secret\n"
            f"metadata:\n"
            f'  name: {{{{ include "{app}.{helper}" . }}}}\n'
            f"  labels:\n"
            f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
            f"type: Opaque\n"
            f"data:\n"
        )
        for env in group.env_vars:
            parts.append(
                f"  {{{{ .Values.{group.group_name}.secretKeys.{env.key_name} }}}}: "
                f"{{{{ .Values.{group.group_name}.{env.key_name} | b64enc | quote }}}}\n"
            )
        parts.append("{{- end }}\n")
    if not c.secrets:
        parts.append("# No secrets defined in deployment contract\n")
    return "".join(parts)


def _gen_hpa_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    return (
        f"{{{{- if and .Values.autoscaling.enabled (not .Values.keda.enabled) }}}}\n"
        f"# Standard HPA fallback — use when KEDA operator is not installed.\n"
        f"# Mutually exclusive with keda.enabled (KEDA creates its own HPA).\n"
        f"apiVersion: autoscaling/v2\n"
        f"kind: HorizontalPodAutoscaler\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.fullname" . }}}}\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"spec:\n"
        f"  scaleTargetRef:\n"
        f"    apiVersion: apps/v1\n"
        f"    kind: Deployment\n"
        f'    name: {{{{ include "{app}.fullname" . }}}}\n'
        f"  minReplicas: {{{{ .Values.autoscaling.minReplicas }}}}\n"
        f"  maxReplicas: {{{{ .Values.autoscaling.maxReplicas }}}}\n"
        f"  metrics:\n"
        f"    - type: Resource\n"
        f"      resource:\n"
        f"        name: cpu\n"
        f"        target:\n"
        f"          type: Utilization\n"
        f"          averageUtilization: {{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}\n"
        f"{{{{- end }}}}\n"
    )


def _gen_keda_scaledobject_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    has_kafka_secret = any(g.group_name == "kafka" for g in c.secrets)
    auth_ref = (
        f'      authenticationRef:\n        name: {{{{ include "{app}.fullname" . }}}}-kafka-auth\n'
        if has_kafka_secret
        else ""
    )
    return (
        f"{{{{- if .Values.keda.enabled }}}}\n"
        f"apiVersion: keda.sh/v1alpha1\n"
        f"kind: ScaledObject\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.fullname" . }}}}\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"spec:\n"
        f"  scaleTargetRef:\n"
        f'    name: {{{{ include "{app}.fullname" . }}}}\n'
        f"  minReplicaCount: {{{{ .Values.keda.minReplicaCount }}}}\n"
        f"  maxReplicaCount: {{{{ .Values.keda.maxReplicaCount }}}}\n"
        f"  pollingInterval: {{{{ .Values.keda.pollingInterval }}}}\n"
        f"  cooldownPeriod: {{{{ .Values.keda.cooldownPeriod }}}}\n"
        f"  triggers:\n"
        f"    # Kafka consumer group lag (primary scaler)\n"
        f"    - type: kafka\n"
        f"{auth_ref}"
        f"      metadata:\n"
        f"        bootstrapServers: {{{{ .Values.config.kafka.brokers | quote }}}}\n"
        f"        consumerGroup: {{{{ .Values.keda.kafka.consumerGroup | default .Values.config.kafka.group_id | quote }}}}\n"
        f"        topic: {{{{ .Values.keda.kafka.topic | default (index .Values.config.kafka.topics 0) | quote }}}}\n"
        f"        lagThreshold: {{{{ .Values.keda.kafka.lagThreshold | quote }}}}\n"
        f"        activationLagThreshold: {{{{ .Values.keda.kafka.activationLagThreshold | quote }}}}\n"
        f"        saslType: scram_sha512\n"
        f"        tls: disable\n"
        f"    {{{{- if .Values.keda.cpu.enabled }}}}\n"
        f"    # CPU utilisation (secondary scaler)\n"
        f"    - type: cpu\n"
        f"      metricType: Utilization\n"
        f"      metadata:\n"
        f"        value: {{{{ .Values.keda.cpu.threshold | quote }}}}\n"
        f"    {{{{- end }}}}\n"
        f"{{{{- end }}}}\n"
    )


def _gen_keda_triggerauth_yaml(c: DeploymentContract) -> str:
    app = c.app_name
    if not any(g.group_name == "kafka" for g in c.secrets):
        return "# No kafka secret group — KEDA TriggerAuthentication not generated\n"
    helper = f"{to_camel_suffix('kafka')}SecretName"
    return (
        f"{{{{- if .Values.keda.enabled }}}}\n"
        f"apiVersion: keda.sh/v1alpha1\n"
        f"kind: TriggerAuthentication\n"
        f"metadata:\n"
        f'  name: {{{{ include "{app}.fullname" . }}}}-kafka-auth\n'
        f"  labels:\n"
        f'    {{{{- include "{app}.labels" . | nindent 4 }}}}\n'
        f"spec:\n"
        f"  secretTargetRef:\n"
        f"    - parameter: sasl\n"
        f'      name: {{{{ include "{app}.{helper}" . }}}}\n'
        f"      key: {{{{ .Values.kafka.secretKeys.username }}}}\n"
        f"    - parameter: password\n"
        f'      name: {{{{ include "{app}.{helper}" . }}}}\n'
        f"      key: {{{{ .Values.kafka.secretKeys.password }}}}\n"
        f"{{{{- end }}}}\n"
    )


def _gen_notes_txt(c: DeploymentContract) -> str:
    app = c.app_name
    return (
        f"{app} has been deployed.\n"
        f"\n"
        f"1. Get the metrics/health endpoint:\n"
        f'   kubectl port-forward svc/{{{{ include "{app}.fullname" . }}}} {{{{ .Values.service.port }}}}:{{{{ .Values.service.port }}}}\n'
        f"   curl http://localhost:{{{{ .Values.service.port }}}}{c.health.liveness_path}\n"
        f"   curl http://localhost:{{{{ .Values.service.port }}}}{c.health.metrics_path}\n"
        f"\n"
        f"{{{{- if .Values.keda.enabled }}}}\n"
        f"\n"
        f"2. Check KEDA autoscaling status:\n"
        f'   kubectl get scaledobject {{{{ include "{app}.fullname" . }}}}\n'
        f"   kubectl get hpa\n"
        f"{{{{- end }}}}\n"
        f"\n"
        f"3. View logs:\n"
        f'   kubectl logs -l app.kubernetes.io/name={{{{ include "{app}.name" . }}}} -f\n'
    )


# ============================================================================
# ArgoCD Application
# ============================================================================


@dataclass
class ArgocdConfig:
    """Configuration for ArgoCD ``Application`` generation.

    All fields have sensible defaults. ``repo_url`` is required (no sensible
    default — the Helm chart that the Application points at is whatever
    ``generate_chart`` writes to a repo path).
    """

    argocd_namespace: str = "argocd"
    """ArgoCD namespace (where the ``Application`` CR lives)."""

    dest_namespace: str = "dfe"
    """Destination namespace for the deployed app."""

    dest_server: str = "https://kubernetes.default.svc"
    """Destination cluster (``server`` field)."""

    repo_url: str = ""
    """Source git repo URL (where the Helm chart lives). Required."""

    target_revision: str = "main"
    """Source git revision (branch/tag)."""

    chart_path: str = "chart"
    """Path within the repo to the Helm chart."""

    project: str = "default"
    """ArgoCD project."""

    sync_wave: int = WAVE_APPS
    """Sync wave (lower runs first). Defaults to :data:`~hyperi_pylib.deployment.WAVE_APPS`."""

    extra_ignore_differences: list[str] = field(default_factory=list)
    """Additional ``ignoreDifferences`` entries appended to the canonical
    defaults (HPA replicas, ClusterIP, webhook caBundle). Each entry is
    a raw YAML fragment matching the ArgoCD ignoreDifferences shape
    (e.g. ``"- group: apps\\n  kind: Deployment\\n  jsonPointers:\\n    - /spec/template/spec/containers/0/image"``).
    Consumer extension point; defaults to empty."""


def _format_extra_ignore_differences(entries: list[str]) -> str:
    """Indent consumer-supplied ignoreDifferences entries by 4 spaces.

    Args:
        entries: Raw YAML fragments, each starting with ``- group:`` and using
            two-space internal indentation.

    Returns:
        Indented lines joined by newlines, with a trailing newline, or empty
        string when ``entries`` is empty.
    """
    if not entries:
        return ""
    lines = []
    for entry in entries:
        for line in entry.splitlines():
            lines.append(f"    {line}")
    return "\n".join(lines) + "\n"


def generate_argocd_application(
    contract: DeploymentContract,
    argo: ArgocdConfig,
    *,
    identity: ContractIdentity | None = None,
) -> str:
    """Generate an ArgoCD ``Application`` CR YAML from the deployment contract.

    The CR points at a Helm chart in a git repo (typically the chart
    ``generate_chart`` produces). Apply with::

        kubectl apply -n argocd -f application.yaml

    When ``identity`` is provided, the three Contract Identity Annotation
    Scheme v1 keys land under ``metadata.annotations:`` alongside the
    existing ``argocd.argoproj.io/sync-wave`` entry. Pass ``None`` (the
    default) to preserve pre-identity output.
    """
    extras_block = _format_extra_ignore_differences(argo.extra_ignore_differences)
    identity_lines = "" if identity is None else f"{identity.as_yaml_annotations(indent=4)}\n"
    return (
        f"# AUTOGENERATED — do not edit by hand.\n"
        f"# Generated by hyperi_pylib.deployment.generate_argocd_application()\n"
        f"# Schema version: {contract.schema_version}\n"
        f"# Source contract: {contract.app_name}::deployment::contract()\n"
        f"# Regenerate with: `{contract.binary()} emit-argocd > application.yaml`\n"
        f"apiVersion: argoproj.io/v1alpha1\n"
        f"kind: Application\n"
        f"metadata:\n"
        f"  name: {contract.app_name}\n"
        f"  namespace: {argo.argocd_namespace}\n"
        f"  annotations:\n"
        f'    argocd.argoproj.io/sync-wave: "{argo.sync_wave}"\n'
        f"{identity_lines}"
        f"  finalizers:\n"
        f"    - resources-finalizer.argocd.argoproj.io\n"
        f"spec:\n"
        f"  project: {argo.project}\n"
        f"\n"
        f"  source:\n"
        f"    repoURL: {argo.repo_url}\n"
        f"    targetRevision: {argo.target_revision}\n"
        f"    path: {argo.chart_path}\n"
        f"    helm:\n"
        f"      releaseName: {contract.app_name}\n"
        f"\n"
        f"  destination:\n"
        f"    server: {argo.dest_server}\n"
        f"    namespace: {argo.dest_namespace}\n"
        f"\n"
        f"  syncPolicy:\n"
        f"    automated:\n"
        f"      prune: true\n"
        f"      selfHeal: true\n"
        f"      allowEmpty: false\n"
        f"    syncOptions:\n"
        f"      - CreateNamespace=true\n"
        f"      - PrunePropagationPolicy=foreground\n"
        f"      - PruneLast=true\n"
        f"      - ServerSideApply=true\n"
        f"    retry:\n"
        f"      limit: 5\n"
        f"      backoff:\n"
        f"        duration: 5s\n"
        f"        factor: 2\n"
        f"        maxDuration: 3m\n"
        f"\n"
        f"  ignoreDifferences:\n"
        f"    - group: apps\n"
        f"      kind: Deployment\n"
        f"      jsonPointers:\n"
        f"        - /spec/replicas\n"
        f'    - group: ""\n'
        f"      kind: Service\n"
        f"      jsonPointers:\n"
        f"        - /spec/clusterIP\n"
        f"        - /spec/clusterIPs\n"
        f"    - group: admissionregistration.k8s.io\n"
        f"      kind: ValidatingWebhookConfiguration\n"
        f"      jqPathExpressions:\n"
        f"        - .webhooks[].clientConfig.caBundle\n"
        f"{extras_block}"
    )


__all__ = [
    "ArgocdConfig",
    "generate_argocd_application",
    "generate_chart",
    "generate_compose_fragment",
    "generate_container_manifest",
    "generate_dockerfile",
    "generate_runtime_stage",
    "to_camel_suffix",
]
