# Project:   scalo
# File:      tests/unit/deployment/test_contract_parity.py
# Purpose:   scalo-py parses and re-emits the deployment contract scalo-rs emits
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""scalo-py reads the contract scalo-rs writes, and writes it back unchanged.

``tests/fixtures/contract-parity/deployment-contract.json`` is scalo-rs's
``tests/fixtures/contract-parity/deployment-contract.json``, copied verbatim.
scalo-rs pins it from its own serialiser and sets every optional field, so a
field scalo-rs adds and scalo-py lacks fails here as ``extra_forbidden``.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scalo.deployment import (
    BaseDistro,
    DeploymentContract,
    EnabledCondition,
    EqualsCondition,
    KafkaLagTrigger,
    KedaConfig,
    KedaContract,
    NativeDepsContract,
    OneOfCondition,
    PortContract,
    ResourceList,
    ResourcesContract,
    SecretEnvContract,
    SecretGroupContract,
    SecurityContract,
    ServiceAccount,
    WritablePath,
    generate_chart,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "contract-parity" / "deployment-contract.json"

# Keys scalo-py writes that scalo-rs neither writes nor reads.
PYTHON_ONLY = {
    "builder_image",
    "python_version",
    "emit_healthcheck",
    "native_deps.distro_codename",
}


def _raw() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _missing_or_changed(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Paths under ``expected`` whose value ``actual`` drops or changes."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        found: list[str] = []
        for key, value in expected.items():
            child = f"{path}.{key}" if path else key
            if key not in actual:
                found.append(child)
            else:
                found.extend(_missing_or_changed(value, actual[key], child))
        return found
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        found = []
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            found.extend(_missing_or_changed(left, right, f"{path}.{index}"))
        return found
    return [] if expected == actual else [path]


def _added(expected: Any, actual: Any, path: str = "") -> set[str]:
    """Paths ``actual`` carries that ``expected`` does not."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        found: set[str] = set()
        for key, value in actual.items():
            child = f"{path}.{key}" if path else key
            if key not in expected:
                found.add(child)
            else:
                found |= _added(expected[key], value, child)
        return found
    if isinstance(expected, list) and isinstance(actual, list):
        found = set()
        for index, (left, right) in enumerate(zip(expected, actual, strict=False)):
            found |= _added(left, right, f"{path}.{index}")
        return found
    return set()


def _set(raw: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """A copy of ``raw`` with ``value`` at the dotted ``path``; a numeric segment indexes a list."""
    doc = copy.deepcopy(raw)
    node: Any = doc
    *parents, leaf = path.split(".")
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(leaf)] = value
    else:
        node[leaf] = value
    return doc


def _delete(raw: dict[str, Any], path: str) -> dict[str, Any]:
    doc = copy.deepcopy(raw)
    node: Any = doc
    *parents, leaf = path.split(".")
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    del node[leaf]
    return doc


def _error_locs(raw: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as caught:
        DeploymentContract.model_validate(raw)
    return [(err["type"], ".".join(str(part) for part in err["loc"])) for err in caught.value.errors()]


# ---- The scalo-rs contract parses and round-trips -----------------------------


def test_the_scalo_rs_contract_parses() -> None:
    contract = DeploymentContract.model_validate(_raw())
    assert contract.app_name == "parity-app"
    assert [p.when for p in contract.extra_ports] == [
        None,
        EnabledCondition(path="config.grpc.enabled"),
        EqualsCondition(path="config.source.transport", value="direct"),
        OneOfCondition(path="config.syslog.protocol", values=["udp", "both"]),
    ]
    assert [p.bound_from for p in contract.extra_ports] == [
        "http.bind_address",
        "grpc.bind_address",
        None,
        "syslog.bind_address",
    ]
    assert contract.unbound_listen_paths == ["client.bind_address"]
    assert contract.keda is not None
    assert contract.keda.enabled is True
    assert contract.keda.kafka_trigger == KafkaLagTrigger.under("config.source")
    assert contract.native_deps.distro is BaseDistro.TRIXIE
    assert contract.native_deps.unresolved_base_image == "registry.example.com/base@sha256:0123"
    assert contract.native_deps.contradicted_base_image == "debian:bookworm-slim"


def test_the_scalo_rs_contract_parses_every_v4_field() -> None:
    contract = DeploymentContract.model_validate(_raw())
    assert contract.schema_version == 4
    assert contract.health.startup_budget_seconds == 120
    assert [(p.public, p.app_protocol) for p in contract.extra_ports] == [
        (True, ""),
        (False, "kubernetes.io/h2c"),
        (False, ""),
        (False, ""),
    ]
    assert contract.secrets[0].optional is True
    assert contract.writable_paths == [
        WritablePath(
            name="spool",
            path="/var/lib/parity-app/spool",
            size_limit="2Gi",
            when=EnabledCondition(path="config.spool.enabled"),
        ),
        WritablePath(name="state", path="/var/lib/parity-app/state", persistent=True, size="5Gi"),
    ]
    assert contract.termination_grace_seconds == 60
    assert contract.resources == ResourcesContract(
        requests=ResourceList(cpu="250m", memory="256Mi"),
        limits=ResourceList(cpu="2", memory="1Gi"),
    )
    assert contract.security == SecurityContract(
        run_as_user=1001, run_as_group=1002, fs_group=1003, capabilities_add=["NET_BIND_SERVICE"]
    )
    assert contract.singleton is False
    assert contract.service_account is ServiceAccount.NONE
    assert contract.config_schema is not None
    assert contract.config_schema["$defs"]["SourceSection"]["properties"]["batch_size"]["x-scalo-dial"] == "big"


def test_the_scalo_rs_contract_round_trips() -> None:
    first = DeploymentContract.model_validate(_raw())
    again = DeploymentContract.from_json(first.to_json())
    assert again == first


def test_emitting_keeps_every_key_and_value_scalo_rs_wrote() -> None:
    raw = _raw()
    emitted = json.loads(DeploymentContract.model_validate(raw).to_json())
    assert _missing_or_changed(raw, emitted) == []
    assert _added(raw, emitted) == PYTHON_ONLY


def test_the_secret_field_carries_the_scalo_marker() -> None:
    schema = DeploymentContract.model_validate(_raw()).config_schema
    assert schema is not None
    password = schema["$defs"]["SourceSection"]["properties"]["password"]
    assert [key for key in password if key.startswith("x-")] == ["x-scalo-secret"]
    assert password["writeOnly"] is True


# ---- What it still refuses ----------------------------------------------------


@pytest.mark.parametrize(
    "parent",
    [
        "",
        "extra_ports.0",
        "extra_ports.1.when",
        "keda",
        "keda.kafka_trigger",
        "native_deps",
        "health",
        "oci_labels",
        "secrets.0",
        "writable_paths.0",
        "writable_paths.0.when",
        "resources",
        "resources.requests",
        "security",
    ],
)
def test_an_unknown_key_is_refused(parent: str) -> None:
    path = f"{parent}.surprise" if parent else "surprise"
    errors = _error_locs(_set(_raw(), path, 1))
    assert len(errors) == 1, errors
    kind, loc = errors[0]
    assert kind == "extra_forbidden"
    assert loc.endswith("surprise")


@pytest.mark.parametrize(
    ("path", "value", "kind"),
    [
        ("extra_ports.0.bound_from", 8080, "string_type"),
        ("extra_ports.1.when", "config.grpc.enabled", "model_attributes_type"),
        ("extra_ports.1.when.kind", "always", "union_tag_invalid"),
        ("extra_ports.2.when.value", ["direct"], "string_type"),
        ("extra_ports.3.when.values", "udp", "list_type"),
        ("unbound_listen_paths", "client.bind_address", "list_type"),
        ("keda.enabled", "maybe", "bool_parsing"),
        ("keda.kafka_trigger", ["config.source"], "model_type"),
        ("keda.kafka_trigger.brokers_path", None, "string_type"),
        ("native_deps.distro", "plucky", "enum"),
        ("native_deps.unresolved_base_image", 1, "string_type"),
        ("native_deps.contradicted_base_image", ["debian"], "string_type"),
        ("health.startup_budget_seconds", "soon", "int_parsing"),
        ("extra_ports.0.public", "maybe", "bool_parsing"),
        ("extra_ports.1.app_protocol", 2, "string_type"),
        ("secrets.0.optional", "maybe", "bool_parsing"),
        ("writable_paths", {"name": "spool"}, "list_type"),
        ("writable_paths.0.when.kind", "always", "union_tag_invalid"),
        ("termination_grace_seconds", -1, "greater_than_equal"),
        ("termination_grace_seconds", 2**32, "less_than_equal"),
        ("resources.limits.cpu", 2, "string_type"),
        ("security.run_as_user", -1, "greater_than_equal"),
        ("security.read_only_root_filesystem", "maybe", "bool_parsing"),
        ("security.capabilities_add", "NET_ADMIN", "list_type"),
        ("singleton", "maybe", "bool_parsing"),
        ("service_account", "external", "enum"),
        ("service_account", "None", "enum"),
        ("service_account", True, "enum"),
    ],
)
def test_a_wrong_type_is_refused(path: str, value: Any, kind: str) -> None:
    errors = _error_locs(_set(_raw(), path, value))
    assert [error[0] for error in errors] == [kind], errors


def test_a_condition_missing_its_value_is_refused() -> None:
    errors = _error_locs(_delete(_raw(), "extra_ports.2.when.value"))
    assert errors == [("missing", "extra_ports.2.when.equals.value")]


# ---- What v4 refuses ------------------------------------------------------------

DIAL = "config_schema.$defs.SourceSection.properties.batch_size.x-scalo-dial"


def test_a_startup_budget_of_zero_is_refused() -> None:
    errors = _error_locs(_set(_raw(), "health.startup_budget_seconds", 0))
    assert errors == [("greater_than_equal", "health.startup_budget_seconds")]


def test_a_writable_path_not_starting_with_a_slash_is_refused() -> None:
    errors = _error_locs(_set(_raw(), "writable_paths.0.path", "var/lib/parity-app/spool"))
    assert errors == [("string_pattern_mismatch", "writable_paths.0.path")]


@pytest.mark.parametrize("tier", ["huge", "Big", "", True, 1, None, ["big"]])
def test_a_dial_marker_outside_big_and_small_is_refused(tier: Any) -> None:
    with pytest.raises(ValidationError) as caught:
        DeploymentContract.model_validate(_set(_raw(), DIAL, tier))
    errors = caught.value.errors()
    assert [(err["type"], err["loc"]) for err in errors] == [("value_error", ("config_schema",))]
    assert "$defs.SourceSection.properties.batch_size: x-scalo-dial is" in errors[0]["msg"]


@pytest.mark.parametrize("tier", ["big", "small"])
def test_a_dial_marker_of_big_or_small_is_kept(tier: str) -> None:
    emitted = json.loads(DeploymentContract.model_validate(_set(_raw(), DIAL, tier)).to_json())
    batch_size = emitted["config_schema"]["$defs"]["SourceSection"]["properties"]["batch_size"]
    assert batch_size["x-scalo-dial"] == tier


def test_a_dial_marker_is_checked_at_any_depth() -> None:
    schema = {"type": "array", "items": [{"anyOf": [{"type": "integer", "x-scalo-dial": "medium"}]}]}
    errors = _error_locs(_set(_raw(), "config_schema", schema))
    assert errors == [("value_error", "config_schema")]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("writable_paths.0.name", "Spool_Dir"),
        ("writable_paths.0.name", "-spool"),
        ("writable_paths.0.name", "spool-"),
        ("writable_paths.0.name", ""),
        ("writable_paths.0.name", "a" * 51),
        ("writable_paths.0.path", ""),
        ("security.capabilities_add.0", "net_bind_service"),
        ("security.capabilities_add.0", "CAP NET"),
        ("security.capabilities_add.0", ""),
    ],
)
def test_a_name_outside_its_pattern_is_refused(path: str, value: str) -> None:
    errors = _error_locs(_set(_raw(), path, value))
    assert errors == [("string_pattern_mismatch", path)]


def test_a_fifty_character_writable_name_is_taken() -> None:
    contract = DeploymentContract.model_validate(_set(_raw(), "writable_paths.0.name", "a" * 50))
    assert contract.writable_paths[0].name == "a" * 50


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("writable_paths.1.name", "spool", "writable_paths[spool].name is declared twice"),
        ("writable_paths.1.path", "/var/lib/parity-app/spool/", "is mounted by another path"),
        ("singleton", True, "KEDA must be off"),
    ],
)
def test_a_contract_breaking_a_cross_field_rule_is_refused(path: str, value: Any, message: str) -> None:
    with pytest.raises(ValidationError) as caught:
        DeploymentContract.model_validate(_set(_raw(), path, value))
    errors = caught.value.errors()
    assert [err["type"] for err in errors] == ["value_error"]
    assert message in errors[0]["msg"]


def test_a_persistent_path_without_a_size_is_refused() -> None:
    errors = _error_locs(_set(_raw(), "writable_paths.1.size", " "))
    assert errors == [("value_error", "writable_paths.1")]


def test_a_singleton_with_keda_off_or_absent_is_taken() -> None:
    off = _set(_set(_raw(), "singleton", True), "keda.enabled", False)
    assert DeploymentContract.model_validate(off).singleton is True
    absent = _set(_set(_raw(), "singleton", True), "keda", None)
    assert DeploymentContract.model_validate(absent).keda is None


# ---- Fields left unset keep the contract's earlier shape ------------------------


def _bare() -> DeploymentContract:
    return DeploymentContract(
        app_name="bare",
        metrics_port=9090,
        env_prefix="BARE",
        metric_prefix="bare",
        config_mount_path="/etc/bare/config.yaml",
        image_registry="registry.example.com",
        extra_ports=[PortContract(name="http", port=8080)],
    )


def test_a_contract_without_the_listener_fields_omits_their_keys() -> None:
    emitted = json.loads(_bare().to_json())
    assert "unbound_listen_paths" not in emitted
    assert set(emitted["extra_ports"][0]) == {"name", "port", "protocol"}
    for key in ("distro", "unresolved_base_image", "contradicted_base_image"):
        assert key not in emitted["native_deps"]


def test_a_contract_without_the_v4_fields_emits_their_defaults_as_scalo_rs_does() -> None:
    bare = _bare().model_copy(
        update={
            "secrets": [
                SecretGroupContract(
                    group_name="source",
                    env_vars=[SecretEnvContract(env_var="BARE__PASSWORD", key_name="password", secret_key="pw")],
                )
            ]
        }
    )
    emitted = json.loads(bare.to_json())
    assert emitted["schema_version"] == 4
    assert emitted["health"]["startup_budget_seconds"] == 150
    assert emitted["termination_grace_seconds"] == 45
    assert emitted["security"] == {
        "run_as_user": 1000,
        "run_as_group": 1000,
        "fs_group": 1000,
        "read_only_root_filesystem": True,
    }
    assert emitted["singleton"] is False
    assert "service_account" not in emitted
    assert "writable_paths" not in emitted
    assert "resources" not in emitted
    assert "optional" not in emitted["secrets"][0]


def test_service_account_none_is_emitted_and_own_is_left_out() -> None:
    none = _bare().model_copy(update={"service_account": ServiceAccount.NONE})
    assert json.loads(none.to_json())["service_account"] == "none"
    assert DeploymentContract.from_json(none.to_json()).service_account is ServiceAccount.NONE
    own = DeploymentContract.model_validate({**json.loads(_bare().to_json()), "service_account": "own"})
    assert own.service_account is ServiceAccount.OWN
    assert "service_account" not in json.loads(own.to_json())
    assert _bare().service_account is ServiceAccount.OWN


def test_unset_parts_of_v4_fields_are_left_out() -> None:
    contract = _bare().model_copy(
        update={
            "writable_paths": [WritablePath(name="spool", path="/var/lib/bare/spool")],
            "resources": ResourcesContract(limits=ResourceList(memory="1Gi")),
        }
    )
    emitted = json.loads(contract.to_json())
    assert emitted["writable_paths"] == [{"name": "spool", "path": "/var/lib/bare/spool", "size": "1Gi"}]
    assert emitted["resources"] == {"limits": {"memory": "1Gi"}}


def test_a_v3_contract_loads_with_the_v4_defaults() -> None:
    raw = _set(_raw(), "schema_version", 3)
    for path in (
        "writable_paths",
        "termination_grace_seconds",
        "resources",
        "security",
        "singleton",
        "service_account",
        "config_mount_path",
        "health.startup_budget_seconds",
        "extra_ports.0.public",
        "extra_ports.1.app_protocol",
        "secrets.0.optional",
    ):
        raw = _delete(raw, path)
    contract = DeploymentContract.model_validate(raw)
    assert contract.schema_version == 3
    assert contract.writable_paths == []
    assert contract.termination_grace_seconds == 45
    assert contract.resources.is_empty()
    assert contract.security == SecurityContract()
    assert contract.singleton is False
    assert contract.service_account is ServiceAccount.OWN
    assert contract.config_mount_path == ""
    assert contract.health.startup_budget_seconds == 150
    assert contract.extra_ports[0].public is False
    assert contract.extra_ports[1].app_protocol == ""
    assert contract.secrets[0].optional is False


def test_a_keda_contract_from_before_enabled_and_kafka_trigger_loads_as_on() -> None:
    keda = KedaContract.model_validate(
        {
            "min_replicas": 1,
            "max_replicas": 10,
            "polling_interval": 15,
            "cooldown_period": 300,
            "kafka_lag_threshold": 1000,
            "activation_lag_threshold": 0,
            "cpu_enabled": True,
            "cpu_threshold": 80,
        }
    )
    assert keda.enabled is True
    assert keda.kafka_trigger == KafkaLagTrigger.under("config.kafka")
    assert keda.kafka_trigger.enabled is True


def test_a_keda_contract_emits_enabled_and_its_trigger() -> None:
    contract = _bare().model_copy(update={"keda": KedaContract()})
    keda = json.loads(contract.to_json())["keda"]
    assert keda["enabled"] is True
    assert keda["kafka_trigger"] == {
        "enabled": True,
        "brokers_path": "config.kafka.brokers",
        "group_path": "config.kafka.group_id",
        "topics_path": "config.kafka.topics",
    }


# ---- Builders mirror scalo-rs -------------------------------------------------


def test_kafka_lag_trigger_under_and_disabled() -> None:
    source = KafkaLagTrigger.under("config.source")
    assert source.enabled is True
    assert (source.brokers_path, source.group_path, source.topics_path) == (
        "config.source.brokers",
        "config.source.group_id",
        "config.source.topics",
    )
    off = KafkaLagTrigger.disabled()
    assert off.enabled is False
    assert off.model_dump(exclude={"enabled"}) == KafkaLagTrigger().model_dump(exclude={"enabled"})


def test_from_config_carries_enabled() -> None:
    assert KedaContract.from_config(KedaConfig()).enabled is True
    assert KedaContract.from_config(KedaConfig(enabled=False)).enabled is False


def test_a_gated_port_serialises_in_the_scalo_rs_shape() -> None:
    port = PortContract(
        name="relay",
        port=6000,
        protocol="UDP",
        when=OneOfCondition(path="config.source.transport", values=["direct", "grpc"]),
        bound_from="source.grpc.listen",
    )
    assert json.loads(port.model_dump_json()) == {
        "name": "relay",
        "port": 6000,
        "protocol": "UDP",
        "when": {"kind": "one_of", "path": "config.source.transport", "values": ["direct", "grpc"]},
        "bound_from": "source.grpc.listen",
    }
    assert EnabledCondition(path="config.grpc.enabled").model_dump() == {
        "kind": "enabled",
        "path": "config.grpc.enabled",
    }
    assert EqualsCondition(path="config.t", value="direct").model_dump() == {
        "kind": "equals",
        "path": "config.t",
        "value": "direct",
    }


def test_native_deps_constructors_record_the_distro() -> None:
    assert NativeDepsContract.for_scalo_extras(["kafka"], "ubuntu:24.04").distro is BaseDistro.TRIXIE
    bookworm = NativeDepsContract.for_scalo_features(
        ["directory-config-git"], "debian:bookworm-slim", distro_codename="bookworm"
    )
    assert bookworm.distro is BaseDistro.BOOKWORM
    assert NativeDepsContract.for_scalo_extras([], "x", distro_codename="plucky").distro is None


# ---- KEDA off generates what no KEDA contract does -----------------------------


def test_a_disabled_keda_contract_generates_no_scaled_object(tmp_path: Path) -> None:
    off = _bare().model_copy(update={"keda": KedaContract(enabled=False)})
    none = _bare()
    generate_chart(off, tmp_path / "off")
    generate_chart(none, tmp_path / "none")
    assert not (tmp_path / "off" / "templates" / "keda-scaledobject.yaml").exists()
    assert not (tmp_path / "off" / "templates" / "keda-triggerauth.yaml").exists()
    values_off = (tmp_path / "off" / "values.yaml").read_text(encoding="utf-8")
    values_none = (tmp_path / "none" / "values.yaml").read_text(encoding="utf-8")
    assert values_off == values_none
