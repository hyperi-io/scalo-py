# Project:   scalo
# File:      deployment/contract.py
# Purpose:   Deployment contract Pydantic models
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Deployment contract Pydantic models for Python apps.

scalo-py is the Tier-2 producer of the scalo deployment contract (scalo-rs is
Tier 1 for Rust services). Apps build a ``DeploymentContract`` from their
``Config`` defaults; generation functions create Python-native deployment
artefacts (uv/venv runtime-stage Dockerfile, Helm chart, Compose fragment,
ArgoCD Application) and validation functions check existing artefacts against
the contract.

The serialised JSON (``deployment-contract.json`` / ``container-manifest.json``)
stays schema-compatible with scalo-rs's so CI tooling reads either uniformly;
the *generation* is Python-specific (uv venv, console-script entrypoint,
``python:*-slim`` base) -- it does not produce Rust artefacts.
"""

import json
import string
import unicodedata
from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .capability import Capability
from .contract_identity import DEFAULT_LABEL_NAMESPACE
from .emit import DIAL_KEYWORD, DIAL_TIERS
from .keda import KedaContract
from .native_deps import NativeDepsContract
from .registry import DEFAULT_PYTHON_VERSION, default_base_image, default_builder_image


class ImageProfile(StrEnum):
    """Container image profile -- controls what goes into the generated Dockerfile.

    Both profiles use the same linking strategy (dynamic). The difference is
    optimisation level, debug tooling, and image metadata.

    Image tagging convention:

    | Profile | Tag | Example |
    |---------|-----|---------|
    | ``production`` | ``:<version>``, ``:latest`` | ``my-loader:1.15.0`` |
    | ``development`` | ``:<version>-dev``, ``:latest-dev`` | ``my-loader:1.15.0-dev`` |
    """

    PRODUCTION = "production"
    """Minimal production image -- stripped binary, no debug tools."""

    DEVELOPMENT = "development"
    """Development image -- includes diagnostic tools (bash, strace, tcpdump,
    procps, dnsutils, net-tools). Same binary, same linking."""


# ---- Defaults (module-level so they appear in JSON Schema docs) -------------

# Must equal scalo-rs's CONTRACT_SCHEMA_VERSION, the version data/contract.schema.json pins.
DEFAULT_SCHEMA_VERSION = 4
MAX_SUPPORTED_SCHEMA_VERSION = 4

_U32_MAX = 2**32 - 1
"""The largest value scalo-rs reads into a ``u32`` field."""

_WRITABLE_NAME_PATTERN = r"^[a-z0-9]([-a-z0-9]{0,48}[a-z0-9])?$"
"""1 to 50 lowercase letters, digits and inner hyphens, so ``writable-<name>`` stays a 63-character volume name."""

_CAPABILITY_PATTERN = r"^[A-Z0-9_]+$"
"""An upper-case Linux capability name without the ``CAP_`` prefix, e.g. ``NET_ADMIN``."""

_KUBERNETES_PROTOCOLS = ("TCP", "UDP", "SCTP")
"""The protocols Kubernetes takes on a container or Service port."""

_MAX_PORT_NAME_LEN = 15
"""The longest port name Kubernetes takes (an RFC 6335 ``IANA_SVC_NAME``)."""

_MAX_APP_NAME_LEN = 63
"""The longest Kubernetes Service name (an RFC 1035 label)."""

_DNS_LABEL_CHARS = frozenset(string.ascii_lowercase + string.digits + "-")
"""The characters a Kubernetes port or Service name is made of."""


def _quoted(text: str) -> str:
    """Return ``text`` in double quotes with control characters escaped, so a message shows what was refused."""
    return json.dumps(text)


def _has_control(text: str) -> bool:
    """True when ``text`` holds a Unicode control character (category Cc), as Rust's ``char::is_control`` counts one."""
    return any(unicodedata.category(char) == "Cc" for char in text)


def _control_text(texts: Iterable[str]) -> str | None:
    """Return the first of ``texts`` that holds a control character, or None."""
    return next((text for text in texts if _has_control(text)), None)


def _holds_a_control_character(text: str) -> str:
    """Describe why ``text`` cannot be printed by a generator onto the one line it gets."""
    return f"{_quoted(text)} holds a control character, which would break the line a generator prints it on"


def _dial_fault(node: Any, path: tuple[str, ...]) -> str | None:
    """Describe the first ``DIAL_KEYWORD`` under ``node`` whose value is not in ``DIAL_TIERS``, or None.

    Every object and array is searched, as the contract's JSON Schema checks
    the keyword wherever it appears.
    """
    if isinstance(node, dict):
        if DIAL_KEYWORD in node and node[DIAL_KEYWORD] not in DIAL_TIERS:
            where = ".".join(path) or "the schema root"
            return f'{where}: {DIAL_KEYWORD} is {json.dumps(node[DIAL_KEYWORD])}, and it must be "big" or "small"'
        children = [(str(key), child) for key, child in node.items() if key != DIAL_KEYWORD]
    elif isinstance(node, list):
        children = [(str(index), child) for index, child in enumerate(node)]
    else:
        return None
    for key, child in children:
        if fault := _dial_fault(child, (*path, key)):
            return fault
    return None


class _BrokenRefError(ValueError):
    """A ``$ref`` in ``config_schema`` that is not local, points at nothing, or refers to itself."""

    def __init__(self, reference: str, reason: str) -> None:
        super().__init__(f"config_schema $ref {_quoted(reference)} {reason}")


def _local_ref(root: Any, reference: str) -> Any:
    """Return the node the local ``$ref`` names in ``root``, reading it as a JSON pointer over objects only."""
    if not reference.startswith("#"):
        raise _BrokenRefError(reference, "is not local to the schema")
    node = root
    for part in reference[1:].split("/"):
        if not part:
            continue
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or key not in node:
            raise _BrokenRefError(reference, "points at nothing")
        node = node[key]
    return node


def _inline_refs(root: Any, node: Any, seen: frozenset[str]) -> None:
    """Follow every ``$ref`` under ``node`` as inlining a dial does, raising on a broken or self-referring one."""
    if isinstance(node, list):
        for item in node:
            _inline_refs(root, item, seen)
    elif isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str):
            if reference in seen:
                raise _BrokenRefError(reference, "refers to itself")
            _inline_refs(root, _local_ref(root, reference), seen | {reference})
        for key, child in node.items():
            if key != "$ref":
                _inline_refs(root, child, seen)


def _follow_dial_refs(root: Any, node: Any, seen: frozenset[str]) -> None:
    """Walk ``node`` as the dial search does, raising on a ``$ref`` it follows that is broken.

    The search takes ``properties``, ``allOf``, ``anyOf``, ``oneOf`` and each ``$ref`` once, and stops at a node
    marked as a dial, whose whole subtree is then inlined.
    """
    if not isinstance(node, dict):
        return
    if DIAL_KEYWORD in node:
        _inline_refs(root, node, frozenset())
        return
    reference = node.get("$ref")
    if isinstance(reference, str) and reference not in seen:
        _follow_dial_refs(root, _local_ref(root, reference), seen | {reference})
    properties = node.get("properties")
    if isinstance(properties, dict):
        for name in sorted(properties):
            _follow_dial_refs(root, properties[name], seen)
    for combinator in ("allOf", "anyOf", "oneOf"):
        branches = node.get(combinator)
        if isinstance(branches, list):
            for branch in branches:
                _follow_dial_refs(root, branch, seen)


class OciLabels(BaseModel):
    """OCI image labels for the container.

    Static labels are set from the contract. Dynamic labels (source, revision,
    version, created) are injected by CI at build time via ``--build-arg``.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    """Image title (defaults to app_name when empty)."""

    description: str = ""
    """Image description."""

    vendor: str = ""
    """Image vendor, the ``org.opencontainers.image.vendor`` label. Empty by
    default, and an empty vendor writes no label."""

    label_namespace: str = DEFAULT_LABEL_NAMESPACE
    """Reverse-DNS namespace of the keys scalo stamps itself:
    ``<namespace>.profile``, ``<namespace>.app`` and ``<namespace>.metrics_port``
    on the image, and the three ``<namespace>.contract.*`` identity keys on
    every artefact. Defaults to ``io.scalo``."""

    licenses: str = ""
    """The app's licence (SPDX). Drives both the
    ``org.opencontainers.image.licenses`` label and the generated Dockerfile's
    ``# License`` header line. Empty by default, and an empty licence writes
    neither."""

    copyright: str = ""
    """The app's copyright line for the generated Dockerfile's ``# Copyright``
    header line. Empty by default, and an empty copyright writes no line."""


class HealthContract(BaseModel):
    """Health probe endpoint paths.

    There is no startup path. A ``startupProbe`` targets ``liveness_path``:
    Kubernetes suspends liveness until the startup probe passes, so one path
    gives both a generous boot budget and a tight liveness period without the
    two drifting apart.
    """

    model_config = ConfigDict(extra="forbid")

    liveness_path: str = "/livez"
    readiness_path: str = "/readyz"
    metrics_path: str = "/metrics"

    startup_budget_seconds: int = Field(default=150, ge=1, le=_U32_MAX)
    """Longest the app may take from start to a passing liveness probe, in seconds.

    The chart's startup probe allows this long before it restarts the pod.
    """


class EnabledCondition(BaseModel):
    """The listener exists while the value at ``path`` counts as true.

    True is anything but false, null, zero or empty, as the chart reads it.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["enabled"] = "enabled"
    path: str
    """Dotted ``.Values`` path of the switch, e.g. ``config.grpc.enabled``."""


class EqualsCondition(BaseModel):
    """The listener exists while the value at ``path``, as a string, equals ``value``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["equals"] = "equals"
    path: str
    """Dotted ``.Values`` path of the setting."""

    value: str
    """The value that turns the listener on."""


class OneOfCondition(BaseModel):
    """The listener exists while the value at ``path``, as a string, is one of ``values``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["one_of"] = "one_of"
    path: str
    """Dotted ``.Values`` path of the setting."""

    values: list[str]
    """The values that turn the listener on."""


type PortCondition = Annotated[
    EnabledCondition | EqualsCondition | OneOfCondition,
    Field(discriminator="kind"),
]
"""When a port's listener exists, as a test on a chart values path, tagged by ``kind``."""


def _condition_texts(condition: PortCondition) -> Iterator[str]:
    """Yield every string a port condition carries: its path, then its value or values."""
    yield condition.path
    if isinstance(condition, EqualsCondition):
        yield condition.value
    elif isinstance(condition, OneOfCondition):
        yield from condition.values


class PortContract(BaseModel):
    """Additional container port beyond the metrics port."""

    model_config = ConfigDict(extra="forbid")

    name: str
    """Port name (e.g., ``http``): 1 to 15 lowercase letters, digits and single inner hyphens, with a letter."""

    port: int = Field(ge=1, le=65535)
    """Port number (e.g., 8080)."""

    protocol: str = "TCP"
    """``TCP``, ``UDP`` or ``SCTP``, in any case (default: ``TCP``)."""

    when: PortCondition | None = Field(default=None, exclude_if=lambda value: value is None)
    """The values condition under which the listener behind this port exists.

    None means it always listens, and is left out of the emitted contract.
    """

    bound_from: str | None = Field(default=None, exclude_if=lambda value: value is None)
    """Dotted ``default_config`` path of the listen address this port serves, e.g. ``grpc.listen``.

    Left out of the emitted contract when unset.
    """

    public: bool = Field(default=False, exclude_if=lambda value: not value)
    """Clients outside the cluster connect here.

    A chart can put such ports on a load balancer, and whether it does is a
    deployment choice. Left out of the emitted contract when false.
    """

    app_protocol: str = Field(default="", exclude_if=lambda value: not value)
    """The application protocol a proxy speaks to this port, e.g. ``kubernetes.io/h2c`` for gRPC without TLS.

    Written to the Service port's ``appProtocol``. Empty writes none and is
    left out of the emitted contract.
    """


class SecretEnvContract(BaseModel):
    """A single environment variable sourced from a K8s Secret."""

    model_config = ConfigDict(extra="forbid")

    env_var: str
    """Full env var name (e.g., ``MYAPP__KAFKA__PASSWORD``)."""

    key_name: str
    """Key name in values.yaml secretKeys and default values (e.g., ``password``)."""

    secret_key: str
    """Default K8s secret key name (e.g., ``kafka-password``)."""


class SecretGroupContract(BaseModel):
    """A group of secrets from the same K8s Secret (e.g., ``kafka``, ``clickhouse``)."""

    model_config = ConfigDict(extra="forbid")

    group_name: str
    """Group name. Used in values.yaml section name and helper template names."""

    env_vars: list[SecretEnvContract]
    """Environment variables injected from this secret group."""

    optional: bool = Field(default=False, exclude_if=lambda value: not value)
    """The app starts without this group, so a missing Secret or key leaves the variable unset.

    Left out of the emitted contract when false.
    """


class WritablePath(BaseModel):
    """A directory the app writes at run time.

    A chart mounts each one as a volume, so the container's root filesystem can
    stay read-only. An ephemeral path is an ``emptyDir``, and a persistent one
    is a claim that outlives the pod.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_WRITABLE_NAME_PATTERN)
    """Volume name, e.g. ``spool``. A persistent path's claim is named ``<chart name>-<name>``."""

    path: str = Field(pattern=r"^/")
    """Absolute mount path, e.g. ``/var/lib/my-app/spool``."""

    size_limit: str = Field(default="", exclude_if=lambda value: not value)
    """Size cap for an ephemeral path, as a Kubernetes quantity (e.g. ``2Gi``). Empty means no cap."""

    persistent: bool = Field(default=False, exclude_if=lambda value: not value)
    """Keep the contents across pod restarts with a persistent volume claim."""

    size: str = "1Gi"
    """Requested size of a persistent path's claim, as a Kubernetes quantity."""

    when: PortCondition | None = Field(default=None, exclude_if=lambda value: value is None)
    """The values condition under which the app writes here. None means always."""

    @model_validator(mode="after")
    def _persistent_has_a_size(self) -> Self:
        """Refuse a persistent path with no claim size, as scalo-rs's ``validate()`` does."""
        if self.persistent and not self.size.strip():
            raise ValueError(f'writable path {self.name}: a persistent path needs a size for its claim, e.g. "1Gi"')
        return self

    @model_validator(mode="after")
    def _text_holds_no_control_character(self) -> Self:
        """Refuse a path, size or condition a generator could not print on one line, as scalo-rs's ``validate()`` does."""
        field = f"writable_paths[{self.name}]"
        if _has_control(self.path):
            raise ValueError(f"{field}.path: {_quoted(self.path)} is not an absolute path on one line")
        for part, text in (("size", self.size), ("size_limit", self.size_limit)):
            if _has_control(text):
                raise ValueError(f"{field}.{part}: {_holds_a_control_character(text)}")
        if self.when is not None and (text := _control_text(_condition_texts(self.when))) is not None:
            raise ValueError(f"{field}.when: {_holds_a_control_character(text)}")
        return self


class ResourceList(BaseModel):
    """One CPU and memory pair, as Kubernetes quantities. An empty value is unset."""

    model_config = ConfigDict(extra="forbid")

    cpu: str = Field(default="", exclude_if=lambda value: not value)
    """CPU, e.g. ``250m`` or ``2``."""

    memory: str = Field(default="", exclude_if=lambda value: not value)
    """Memory, e.g. ``256Mi``."""

    def is_empty(self) -> bool:
        """True when neither CPU nor memory is set."""
        return not self.cpu and not self.memory


class ResourcesContract(BaseModel):
    """CPU and memory requests and limits, as Kubernetes quantities."""

    model_config = ConfigDict(extra="forbid")

    requests: ResourceList = Field(default_factory=ResourceList, exclude_if=lambda value: value.is_empty())
    """What the scheduler reserves for the container."""

    limits: ResourceList = Field(default_factory=ResourceList, exclude_if=lambda value: value.is_empty())
    """The most the container may use."""

    def is_empty(self) -> bool:
        """True when no request or limit is set."""
        return self.requests.is_empty() and self.limits.is_empty()


class SecurityContract(BaseModel):
    """The identity and privileges the container runs with.

    The defaults match the image the Dockerfile generator writes: uid and gid
    1000, a read-only root filesystem and no added capability.
    """

    model_config = ConfigDict(extra="forbid")

    run_as_user: int = Field(default=1000, ge=0, le=_U32_MAX)
    """Numeric user the process runs as. 0 lets it run as root."""

    run_as_group: int = Field(default=1000, ge=0, le=_U32_MAX)
    """Numeric primary group."""

    fs_group: int = Field(default=1000, ge=0, le=_U32_MAX)
    """Group that owns mounted volumes."""

    read_only_root_filesystem: bool = True
    """Mount the root filesystem read-only, so writes go to ``writable_paths``."""

    capabilities_add: list[Annotated[str, Field(pattern=_CAPABILITY_PATTERN)]] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    """Linux capabilities added after every other one is dropped, upper case without ``CAP_``, e.g. ``NET_ADMIN``."""


def _label_fault(name: str, max_len: int) -> str | None:
    """Describe why ``name`` is not 1 to ``max_len`` bytes of lowercase letters, digits and hyphens, or None."""
    if not name or len(name.encode("utf-8", errors="replace")) > max_len:
        return f"is not 1 to {max_len} characters long"
    if not set(name) <= _DNS_LABEL_CHARS:
        return "holds a character other than a lowercase letter, a digit or '-'"
    return None


def _app_name_fault(name: str) -> str | None:
    """Describe why ``name`` is not a Kubernetes Service name, or None when it is one."""
    if fault := _label_fault(name, _MAX_APP_NAME_LEN):
        return fault
    if not name[0].isalpha():
        return "does not start with a lowercase letter"
    if name.endswith("-"):
        return "ends with '-'"
    return None


def _port_name_fault(name: str) -> str | None:
    """Describe why ``name`` is not a port name Kubernetes takes, or None when it is one."""
    if fault := _label_fault(name, _MAX_PORT_NAME_LEN):
        return fault
    if not any(char.isalpha() for char in name):
        return "has no letter"
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return "starts or ends with '-', or has two in a row"
    return None


def _port_fault(index: int, port: PortContract) -> str | None:
    """Describe why ``port`` cannot be generated into an artefact, or None when it can.

    A port is named by ``index`` until its name is known to be printable.
    """
    if fault := _port_name_fault(port.name):
        return (
            f"extra_ports[{index}].name: {_quoted(port.name)} {fault}, and Kubernetes takes a port name of "
            f"1 to {_MAX_PORT_NAME_LEN} lowercase letters, digits and single inner hyphens, with at least one letter"
        )
    field = f"extra_ports[{port.name}]"
    # isascii keeps the fold to ASCII, as Rust's eq_ignore_ascii_case does, since U+017F upper-cases to "S".
    if not (port.protocol.isascii() and port.protocol.upper() in _KUBERNETES_PROTOCOLS):
        return f"{field}.protocol: {_quoted(port.protocol)} is not a protocol Kubernetes takes -- use TCP, UDP or SCTP"
    if port.when is not None and (text := _control_text(_condition_texts(port.when))) is not None:
        return f"{field}.when: {_holds_a_control_character(text)}"
    if port.bound_from is not None and _has_control(port.bound_from):
        return f"{field}.bound_from: {_holds_a_control_character(port.bound_from)}"
    if _has_control(port.app_protocol):
        return f"{field}.app_protocol: {_holds_a_control_character(port.app_protocol)}"
    return None


class DeploymentContract(BaseModel):
    """Deployment-facing contract points derived from the app config cascade.

    Apps build this from their ``Config.default()``. Validation functions
    compare Helm charts and Dockerfiles against these values. Generation
    functions create deployment artefacts (Dockerfile, Helm chart, Compose
    fragment) from scratch.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = DEFAULT_SCHEMA_VERSION
    """Contract schema version. CI checks this and fails if unsupported."""

    app_name: str
    """Application name (e.g., ``my-loader``) -- matched against ``Chart.yaml`` ``name``.

    Every object the chart renders is named after it, so it is a Kubernetes Service name: 1 to 63 lowercase
    letters, digits and inner hyphens, starting with a letter.
    """

    binary_name: str = ""
    """Binary name (e.g., ``my-loader``). Defaults to app_name when empty."""

    description: str = ""
    """One-line description for ``Chart.yaml``."""

    metrics_port: int = Field(ge=1, le=65535)
    """Metrics/health listen port (e.g., 9090)."""

    health: HealthContract = Field(default_factory=HealthContract)
    """Health probe endpoint paths."""

    env_prefix: str
    """Environment variable prefix (e.g., ``MYAPP``).

    Used with ``__`` nesting for the Dynaconf config cascade.
    """

    metric_prefix: str
    """Prometheus metric namespace/prefix (e.g., ``loader``)."""

    config_mount_path: str = ""
    """Config file mount path (e.g., ``/etc/myapp/config.yaml``).

    Empty means the app reads no config file, so no ConfigMap is mounted.
    """

    image_registry: str
    """Container registry base the image is pushed to and pulled from (e.g.,
    ``registry.example.com/team``). Required: there is no default, and a blank
    value is refused. Read it from the cascade with
    :func:`~scalo.deployment.image_registry_from_cascade`."""

    extra_ports: list[PortContract] = Field(default_factory=list)
    """Additional ports beyond metrics (e.g., HTTP data port for receiver)."""

    unbound_listen_paths: list[str] = Field(default_factory=list, exclude_if=lambda value: not value)
    """``default_config`` listen paths that need no port, e.g. the bind address of a client that only sends.

    Left out of the emitted contract when empty.
    """

    entrypoint_args: list[str] = Field(default_factory=list)
    """Default ENTRYPOINT args (e.g., ``["--config", "/etc/app/loader.yaml"]``)."""

    secrets: list[SecretGroupContract] = Field(default_factory=list)
    """Secret groups injected from K8s Secrets."""

    default_config: Any | None = None
    """App-specific config YAML for ``values.yaml`` (any JSON-serialisable shape)."""

    depends_on: list[str] = Field(default_factory=list)
    """Docker Compose service dependencies (e.g., ``["kafka", "clickhouse"]``)."""

    keda: KedaContract | None = None
    """KEDA autoscaling contract (None if KEDA not used)."""

    base_image: str = ""
    """Base container image for the runtime stage.

    Leave empty (the default) to use the language-appropriate
    ``python:{python_version}-slim``. Set explicitly to override. Read it via
    :meth:`effective_base_image`.
    """

    builder_image: str = ""
    """Builder-stage image (the uv image that produces ``/app/.venv``).

    Leave empty (the default) for the Astral uv image matching
    ``python_version``. Set explicitly to override -- mirrors ``base_image``.
    Read it via :meth:`effective_builder_image`.

    The default deliberately trails the runtime by one Debian release; see
    :func:`~scalo.deployment.registry.default_builder_image` for the
    ``glibc(runtime) >= glibc(build)`` rule that pins the direction.
    """

    python_version: str = DEFAULT_PYTHON_VERSION
    """Python version for the runtime/base image (e.g. ``"3.14"``).

    Drives the default base image (``python:{python_version}-slim``) and the
    uv builder image when ``base_image`` / ``builder_image`` are left empty.
    """

    native_deps: NativeDepsContract = Field(default_factory=NativeDepsContract)
    """Runtime native dependencies for the container image.

    Use ``NativeDepsContract.for_scalo_extras`` to auto-populate from scalo-py
    optional-dependency names; the Dockerfile generator emits the correct
    APT repo setup and package installation commands.
    """

    image_profile: ImageProfile = ImageProfile.PRODUCTION
    """Image profile -- production (minimal) or development (debug tools)."""

    emit_healthcheck: bool = True
    """Emit a ``HEALTHCHECK`` directive in the runtime stage.

    Kubernetes ignores ``HEALTHCHECK`` entirely -- it uses the probes from
    the pod spec -- so for a cluster-only image the directive is dead weight.
    It is still on by default because Compose DOES use it, and Compose is a
    supported target. Set False for images that only ever run in K8s.

    ``curl`` stays in the image either way: the standard keeps small debug
    utilities, and it earns its place on those merits.
    """

    oci_labels: OciLabels = Field(default_factory=OciLabels)
    """OCI image labels (static -- dynamic labels injected by CI at build time)."""

    config_schema: dict[str, Any] | None = None
    """Reflectable JSON Schema (draft 2020-12) of the app's full ``Config``,
    derived via pydantic ``model_json_schema`` (scalo-py#3). ``None`` when not
    provided. Secret fields carry the ``x-scalo-secret`` marker, and operator
    dials carry ``x-scalo-dial`` (``big`` or ``small``, see ``DIAL_KEYWORD``).
    Also written to ``config-schema.{json,yaml}`` by
    :func:`scalo.deployment.emit_config_artifacts`."""

    capabilities: list[Capability] = Field(default_factory=list)
    """Capability catalog -- the runtime-data surface a schema cannot derive
    (service names + their knobs). Hand-authored per app. Also written to
    ``capability-catalog.{json,yaml}``."""

    writable_paths: list[WritablePath] = Field(default_factory=list, exclude_if=lambda value: not value)
    """Directories the app writes at run time, so the root filesystem can stay read-only.

    A chart always adds a scratch ``/tmp`` beside these. Left out of the
    emitted contract when empty.
    """

    termination_grace_seconds: int = Field(default=45, ge=0, le=_U32_MAX)
    """Seconds between SIGTERM and SIGKILL.

    The default leaves time for a pre-stop pause, a gRPC drain and a final
    commit after the endpoints drop the pod.
    """

    resources: ResourcesContract = Field(default_factory=ResourcesContract, exclude_if=lambda value: value.is_empty())
    """The app's own CPU and memory requests and limits.

    Empty values leave the chart's defaults in place, and deployment values
    override both. Left out of the emitted contract when empty.
    """

    security: SecurityContract = Field(default_factory=SecurityContract)
    """The user, group and Linux capabilities the image runs with."""

    singleton: bool = False
    """Exactly one pod may run: replicas stay at one, nothing autoscales it, and a new pod starts only after the old one has stopped."""

    @field_validator("app_name")
    @classmethod
    def _app_name_is_a_service_name(cls, value: str) -> str:
        """Refuse an ``app_name`` that is not a Kubernetes Service name, as scalo-rs's ``validate()`` does."""
        if fault := _app_name_fault(value):
            raise ValueError(
                f"app_name: {_quoted(value)} {fault}, and every object the chart renders is named after it, so it "
                f"must be a Kubernetes Service name: 1 to {_MAX_APP_NAME_LEN} lowercase letters, digits and inner "
                "hyphens, starting with a letter"
            )
        return value

    @field_validator("config_schema")
    @classmethod
    def _dial_markers_are_tiers(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Refuse an ``x-scalo-dial`` marker that is not ``big`` or ``small``, wherever it sits."""
        if value is not None and (fault := _dial_fault(value, ())):
            raise ValueError(fault)
        return value

    @field_validator("config_schema")
    @classmethod
    def _dial_refs_resolve(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Refuse a ``$ref`` the dial search follows that is remote, points at nothing or loops, as scalo-rs's ``validate()`` does."""
        if value is not None:
            _follow_dial_refs(value, value, frozenset())
        return value

    @model_validator(mode="after")
    def _extra_ports_are_valid(self) -> Self:
        """Refuse a port Kubernetes would not take, or one a generator could not print, as scalo-rs's ``validate()`` does."""
        for index, port in enumerate(self.extra_ports):
            if fault := _port_fault(index, port):
                raise ValueError(fault)
        return self

    @model_validator(mode="after")
    def _writable_paths_are_unique(self) -> Self:
        """Refuse two writable paths with one name or one mount path, as scalo-rs's ``validate()`` does."""
        names: set[str] = set()
        paths: set[str] = set()
        for writable in self.writable_paths:
            if writable.name in names:
                raise ValueError(f"writable_paths[{writable.name}].name is declared twice")
            mount = writable.path.rstrip("/")
            if mount in paths:
                raise ValueError(f"writable_paths[{writable.name}].path {writable.path!r} is mounted by another path")
            names.add(writable.name)
            paths.add(mount)
        return self

    @model_validator(mode="after")
    def _singleton_leaves_keda_off(self) -> Self:
        """Refuse a singleton with KEDA on: a singleton runs exactly one pod."""
        if self.singleton and self.keda is not None and self.keda.enabled:
            raise ValueError("a singleton runs exactly one pod, so KEDA must be off: set keda=None")
        return self

    @model_validator(mode="after")
    def _keda_has_a_trigger_to_scale_on(self) -> Self:
        """Refuse KEDA left on with no trigger, or with CPU as the only one and none to start from, as scalo-rs does."""
        keda = self.keda
        if keda is None or not keda.enabled or keda.kafka_trigger.enabled:
            return self
        if not keda.cpu_enabled:
            raise ValueError(
                "keda: the Kafka lag trigger and the CPU trigger are both off, so KEDA would have nothing to "
                "scale on; set keda=None to turn autoscaling off"
            )
        if keda.min_replicas == 0:
            raise ValueError(
                "keda.min_replicas: CPU is the only trigger, and KEDA's CPU scaler cannot wake a workload from "
                "zero; set min_replicas to 1 or more, or keep the Kafka lag trigger"
            )
        return self

    @field_validator("image_registry")
    @classmethod
    def _registry_is_set(cls, value: str) -> str:
        """Refuse a blank registry: an image named without one resolves to Docker Hub."""
        if not value.strip():
            raise ValueError(
                "no registry is set, so the chart, compose file and container manifest would "
                "name an image nothing pushed. Set `image_registry` in the contract, or "
                "`deployment.image_registry` in the config cascade"
            )
        return value

    # ---- Convenience accessors (mirror scalo-rs's impl block) ---------------

    def binary(self) -> str:
        """Effective binary name -- falls back to app_name when binary_name empty."""
        return self.binary_name if self.binary_name else self.app_name

    def effective_base_image(self) -> str:
        """Runtime base image -- explicit ``base_image`` or ``python:{python_version}-slim``."""
        return self.base_image if self.base_image else default_base_image(self.python_version)

    def effective_builder_image(self) -> str:
        """Builder image -- explicit ``builder_image`` or the matching uv image."""
        return self.builder_image if self.builder_image else default_builder_image(self.python_version)

    def config_filename(self) -> str:
        """Config file name from the mount path (e.g., ``loader.yaml``)."""
        if "/" not in self.config_mount_path:
            # A bare filename IS the filename. Returning a hardcoded
            # "config.yaml" here would rename the app's config behind its back.
            return self.config_mount_path or "config.yaml"
        return self.config_mount_path.rsplit("/", 1)[-1]

    def config_dir(self) -> str:
        """Config mount directory (e.g., ``/etc/app``)."""
        if "/" not in self.config_mount_path:
            return "/etc"
        head = self.config_mount_path.rsplit("/", 1)[0]
        return head if head else "/"

    def to_json(self) -> str:
        """Serialise to indent=2 JSON for ``--emit-contract`` CLI support."""
        return self.model_dump_json(indent=2, by_alias=False, exclude_none=False)

    def with_dev_profile(self) -> Self:
        """Return a clone with ``ImageProfile.DEVELOPMENT`` set."""
        return self.model_copy(update={"image_profile": ImageProfile.DEVELOPMENT}, deep=True)

    @classmethod
    def from_json(cls, raw: str) -> Self:
        """Parse a contract from a JSON string."""
        return cls.model_validate(json.loads(raw))


__all__ = [
    "DEFAULT_SCHEMA_VERSION",
    "MAX_SUPPORTED_SCHEMA_VERSION",
    "DeploymentContract",
    "EnabledCondition",
    "EqualsCondition",
    "HealthContract",
    "ImageProfile",
    "OciLabels",
    "OneOfCondition",
    "PortCondition",
    "PortContract",
    "ResourceList",
    "ResourcesContract",
    "SecretEnvContract",
    "SecretGroupContract",
    "SecurityContract",
    "WritablePath",
]
