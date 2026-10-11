# Project:   scalo
# File:      deployment/generate.py
# Purpose:   Generate deployment artefacts from DeploymentContract
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Generate Python-native deployment artefacts from a ``DeploymentContract``.

Apps provide ~20% customisation (ports, secrets, config); this module
generates ~80% boilerplate for Python/uv apps: the runtime-stage fragment
(``Dockerfile.runtime``, the canonical artefact), a reference uv builder
stage, an optional composed full Dockerfile, the container manifest JSON and
the Compose fragment. The Kubernetes objects come from the scalo-service
library chart, which renders the serialised contract.

Generation is Python-specific (uv venv, console-script entrypoint,
``python:*-slim`` base) -- it does not produce Rust artefacts. The container
manifest JSON stays schema-compatible with scalo-rs's so CI tooling reads
either uniformly. Artefact text is built with deterministic f-strings (no
timestamps/random ids) so golden snapshots and CI drift-diffs are stable.
"""

import json
from pathlib import Path

from .contract import DeploymentContract, ImageProfile, OciLabels
from .contract_identity import ContractIdentity
from .native_deps import NativeDepsContract

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


def _label_line(key: str, value: str) -> str:
    """A ``LABEL key="value"`` line, or nothing for an empty value, so an unset field writes no label."""
    return f'LABEL {key}="{value}"\n' if value else ""


def _ip_header(labels: OciLabels) -> str:
    """The header's ``# License`` and ``# Copyright`` lines and the ``#`` closing them, each only when set."""
    lines = ""
    if labels.licenses:
        lines += f"# License:   {labels.licenses}\n"
    if labels.copyright:
        lines += f"# Copyright: {labels.copyright}\n"
    return f"{lines}#\n" if lines else ""


def _cmd_line(contract: DeploymentContract) -> str:
    """Build the ``CMD [...]`` line, or empty string when no args."""
    if not contract.entrypoint_args:
        return ""
    args = ", ".join(f'"{a}"' for a in contract.entrypoint_args)
    return f"\nCMD [{args}]"


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
        # Download to a file rather than piping into gpg: `sh` has no pipefail,
        # so `curl ... | gpg` discards curl's exit status and a failed fetch
        # leaves an empty keyring instead of failing the build (hadolint DL4006).
        parts.append(f"    && curl -fsSL {repo.key_url} -o /tmp/repo-key.asc \\\n")
        if repo.key_fingerprint:
            # Assert the key is the pinned one BEFORE it is trusted. Written to a
            # file and grepped rather than piped, for the same exit-status reason.
            parts.append(
                "    && gpg --show-keys --with-colons --with-fingerprint /tmp/repo-key.asc \\\n"
                "       > /tmp/repo-key.info \\\n"
                f'    && grep -q "^fpr:::::::::{repo.key_fingerprint}:" /tmp/repo-key.info \\\n'
                "    && rm -f /tmp/repo-key.info \\\n"
            )
        parts.append(
            f"    && gpg --dearmor -o {repo.keyring} /tmp/repo-key.asc \\\n"
            "    && rm -f /tmp/repo-key.asc \\\n"
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
    """Generate a complete multi-stage Python Dockerfile (uv builder + venv runtime).

    Convenience/example artefact = :func:`generate_builder_stage` +
    :func:`generate_runtime_stage`. The canonical CI artefact is the runtime
    stage alone (``Dockerfile.runtime``); CI composes its own builder. This full
    Dockerfile is what the build smoke test exercises.

    When ``identity`` is provided, the Contract Identity Annotation Scheme v1
    keys are emitted in the runtime stage.

    The header carries a ``# License`` line and a ``# Copyright`` line only when
    ``oci_labels.licenses`` and ``oci_labels.copyright`` are set.
    """
    binary = contract.binary()
    profile_label = _profile_label(contract.image_profile)

    header = (
        f"# Project:   {contract.app_name}\n"
        f"# File:      Dockerfile\n"
        f"# Purpose:   {profile_label} container image\n"
        f"#\n"
        f"{_ip_header(contract.oci_labels)}"
        f"# AUTOGENERATED -- do not edit by hand.\n"
        f"# Generated by scalo.deployment.generate_dockerfile()\n"
        f"# Schema version: {contract.schema_version}\n"
        f"# Source contract: {contract.app_name}::deployment::contract()\n"
        f"# Regenerate with: `{binary} generate-artefacts`\n"
        f"\n"
    )

    return f"{header}{generate_builder_stage(contract)}\n{generate_runtime_stage(contract, identity=identity)}"


# ============================================================================
# Container manifest (CI-consumable JSON)
# ============================================================================


def generate_container_manifest(
    contract: DeploymentContract,
    *,
    identity: ContractIdentity | None = None,
) -> str:
    """Generate a container manifest JSON for CI consumption.

    Mirrors scalo-rs's ``generate_container_manifest``. Output is the minimal
    subset of the deployment contract that CI needs to build the container
    image -- no secrets, no K8s-specific config.

    When ``identity`` is provided, the three Contract Identity Annotation
    Scheme v1 keys are added to the ``labels`` dict. Pass ``None`` (the
    default) to preserve pre-identity output.

    scalo's own label keys sit under ``oci_labels.label_namespace``, and an
    unset vendor or licence writes no label.
    """
    binary = contract.binary()
    profile_str = _profile_label(contract.image_profile)
    title = contract.oci_labels.title or contract.app_name
    namespace = contract.oci_labels.label_namespace

    labels = {
        f"{namespace}.profile": profile_str,
        f"{namespace}.app": contract.app_name,
        f"{namespace}.metrics_port": str(contract.metrics_port),
        "org.opencontainers.image.title": title,
        "org.opencontainers.image.description": contract.oci_labels.description,
    }
    for key, value in (
        ("org.opencontainers.image.vendor", contract.oci_labels.vendor),
        ("org.opencontainers.image.licenses", contract.oci_labels.licenses),
    ):
        if value:
            labels[key] = value
    if identity is not None:
        labels.update(identity.as_labels(namespace))

    apt_repos = [
        {
            "key_url": r.key_url,
            "key_fingerprint": r.key_fingerprint,
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
        "base_image": contract.effective_base_image(),
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
        "labels": labels,
    }

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

    The canonical artefact scalo-py owns. CI (or the app) composes the full
    Dockerfile by prepending a uv builder stage (see
    :func:`generate_builder_stage`) that produces ``/app/.venv``, then this
    runtime stage copies the venv and puts its ``bin/`` on ``PATH``.

    When ``identity`` is provided, the Contract Identity Annotation Scheme v1
    keys are emitted as ``LABEL`` directives directly after the profile
    label. Pass ``None`` (the default) to preserve pre-identity output.

    The profile and identity labels sit under ``oci_labels.label_namespace``,
    and an unset vendor or licence writes no label.
    """
    binary = contract.binary()
    apt_block = _build_apt_block(contract.native_deps, contract.image_profile)
    profile_label = _profile_label(contract.image_profile)
    title = contract.oci_labels.title or contract.app_name
    namespace = contract.oci_labels.label_namespace
    vendor = _label_line("org.opencontainers.image.vendor", contract.oci_labels.vendor)
    licenses = _label_line("org.opencontainers.image.licenses", contract.oci_labels.licenses)
    expose = _expose_ports(contract)
    cmd = _cmd_line(contract)
    identity_block = "" if identity is None else f"{identity.as_dockerfile_labels(namespace)}\n"
    healthcheck = ""
    if contract.emit_healthcheck:
        # Kubernetes ignores HEALTHCHECK (it uses the pod spec's probes);
        # Compose honours it. Contract-gated so a cluster-only image can drop
        # the dead weight.
        healthcheck = (
            f"# Shell form maps any curl failure to exit 1, the only unhealthy status Docker defines.\n"
            f"# hadolint ignore=DL3025\n"
            f"HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\\n"
            f"    CMD curl -sf http://localhost:{contract.metrics_port}"
            f"{contract.health.liveness_path} > /dev/null || exit 1\n"
            f"\n"
        )

    return (
        f"# --- Runtime stage (generated by scalo deployment contract) ---\n"
        f"FROM {contract.effective_base_image()} AS runtime\n"
        f"\n"
        f"# Static OCI labels (from contract)\n"
        f'LABEL org.opencontainers.image.title="{title}"\n'
        f'LABEL org.opencontainers.image.description="{contract.oci_labels.description}"\n'
        f"{vendor}"
        f"{licenses}"
        f'LABEL {namespace}.profile="{profile_label}"\n'
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
        f"# Copy the uv-built virtualenv from the builder and put it on PATH.\n"
        f"COPY --from=builder /app /app\n"
        f'ENV PATH="/app/.venv/bin:$PATH"\n'
        f"\n"
        f"RUN useradd --create-home --uid 1000 appuser\n"
        f"# Numeric, so Kubernetes runAsNonRoot can verify it without reading /etc/passwd.\n"
        f"USER 1000\n"
        f"\n"
        f"EXPOSE {expose}\n"
        f"\n"
        f"{healthcheck}"
        f'ENTRYPOINT ["{binary}"]{cmd}\n'
    )


# ============================================================================
# Builder stage (reference; composed before the runtime stage)
# ============================================================================


def generate_builder_stage(contract: DeploymentContract) -> str:
    """Generate the reference uv builder stage.

    Apps/CI compose this before :func:`generate_runtime_stage`. It builds
    ``/app/.venv`` from the locked dependencies with uv. It carries **no
    credentials** -- apps with private package indexes inject them via
    ``--build-arg`` at ``docker build`` time.

    The dependency install is deliberately split in two: the manifests are
    copied and synced *without* the project first, so an edit under ``src/``
    reuses the cached dependency layer instead of reinstalling the whole
    graph. The two-phase form also sidesteps a real failure mode -- a
    single-phase sync breaks for any package whose metadata references files
    outside the copied set (e.g. ``project.license-files``).
    """
    return (
        f"# --- Builder stage (reference; compose before the runtime stage) ---\n"
        f"FROM {contract.effective_builder_image()} AS builder\n"
        f"\n"
        f"WORKDIR /app\n"
        f"\n"
        f"# Compile bytecode at build time rather than on first import (startup).\n"
        f"ENV UV_COMPILE_BYTECODE=1\n"
        f"\n"
        f"# Phase 1: dependency manifests only, so this layer caches independently\n"
        f"# of source changes.\n"
        f"#\n"
        f"# UV_NO_BUILD is set on THIS command only, not as a stage-wide ENV:\n"
        f"# it must cover dependencies (a silent source build is invisible --\n"
        f"# green build, permanently slower service) but NOT the project, which\n"
        f"# is a local source tree with no wheel to install and would fail with\n"
        f'# "marked as --no-build but has no binary distribution". Note uv\'s\n'
        f"# naming trap: --no-build requires a wheel, --no-binary is the inverse.\n"
        f"COPY pyproject.toml uv.lock ./\n"
        f"RUN UV_NO_BUILD=1 uv sync --frozen --no-dev --no-install-project\n"
        f"\n"
        f"# Phase 2: the project itself -- only this layer rebuilds on a source edit.\n"
        f"COPY src/ src/\n"
        f"RUN uv sync --frozen --no-dev\n"
    )


# ============================================================================
# .dockerignore
# ============================================================================


def generate_dockerignore(contract: DeploymentContract) -> str:
    """Generate a ``.dockerignore`` for the build context.

    Less critical here than usual because the builder uses explicit ``COPY``
    paths rather than ``COPY . .``, so junk cannot land in an image layer by
    accident. It still matters: the whole context is transferred to the
    daemon on every build, and a local ``.venv`` or ``.git`` makes that
    transfer far bigger than the handful of files actually copied.
    """
    _ = contract  # uniform generator signature; output is contract-independent
    return (
        "# AUTOGENERATED -- do not edit by hand.\n"
        "# Generated by scalo.deployment.generate_dockerignore()\n"
        "#\n"
        "# The builder COPYs explicit paths, so this is about the size of the\n"
        "# context sent to the daemon, not about what ends up in the image.\n"
        "\n"
        "# VCS\n"
        ".git\n"
        ".gitignore\n"
        ".gitattributes\n"
        "\n"
        "# Local Python environments and caches\n"
        ".venv\n"
        "venv\n"
        "__pycache__\n"
        "*.py[cod]\n"
        ".mypy_cache\n"
        ".ruff_cache\n"
        ".pytest_cache\n"
        ".coverage\n"
        "coverage.xml\n"
        "htmlcov\n"
        "\n"
        "# Build outputs\n"
        "dist\n"
        "build\n"
        "*.egg-info\n"
        "\n"
        "# Secrets and local overrides -- must never reach the daemon\n"
        ".env\n"
        ".env.*\n"
        "!.env.sample\n"
        "*.pem\n"
        "*.key\n"
        "\n"
        "# Editor / OS noise\n"
        ".idea\n"
        ".vscode\n"
        ".DS_Store\n"
        "\n"
        "# Docs and CI are not needed to build the wheel\n"
        "docs\n"
        "*.md\n"
        "!README.md\n"
    )


# ============================================================================
# Docker Compose fragment
# ============================================================================


def generate_compose_fragment(contract: DeploymentContract) -> str:
    """Generate a Docker Compose service fragment from the deployment contract.

    Mirrors scalo-rs's ``generate_compose_fragment``.
    """
    binary = contract.binary()
    parts: list[str] = []

    parts.append("# Generated by scalo deployment module\n")
    parts.append(f"services:\n  {contract.app_name}:\n")

    env_var = contract.env_prefix.replace("__", "_")
    parts.append(f"    image: {contract.image_registry}/{contract.app_name}:${{{env_var}_VERSION:-latest}}\n")

    if contract.depends_on:
        parts.append("    depends_on:\n")
        for dep in contract.depends_on:
            parts.append(f"      {dep}:\n        condition: service_healthy\n")

    # The observability port is deliberately NOT published to the host. The
    # whole point of a separate port is that operators reach it and users do
    # not; publishing it on a single-box deployment gives that away. It stays
    # reachable from inside the compose network (and from the healthcheck,
    # which runs in the container), which is where a scrape belongs.
    parts.append(f'    expose:\n      - "{contract.metrics_port}"\n')
    if contract.extra_ports:
        parts.append("    ports:\n")
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

    # Compose is a supported production target for small environments, and an
    # unlimited service on a single box is how one container takes the host
    # down.
    parts.append(
        "    deploy:\n"
        "      resources:\n"
        "        limits:\n"
        '          cpus: "2"\n'
        "          memory: 1G\n"
        "        reservations:\n"
        '          cpus: "0.25"\n'
        "          memory: 256M\n"
    )

    if contract.entrypoint_args:
        args = ", ".join(f'"{a}"' for a in contract.entrypoint_args)
        parts.append(f'    command: ["{binary}", {args}]\n')

    return "".join(parts)


__all__ = [
    "generate_builder_stage",
    "generate_compose_fragment",
    "generate_container_manifest",
    "generate_dockerfile",
    "generate_dockerignore",
    "generate_runtime_stage",
]
