# Project:   scalo
# File:      tests/unit/deployment/test_contract_checks.py
# Purpose:   scalo-py refuses the contracts scalo-rs's validate() refuses
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""scalo-py refuses every contract that scalo-rs's ``DeploymentContract::validate()`` refuses.

Each case differs from a contract that passes in one field, and names the field scalo-rs reports, as the cases in
scalo-rs's ``src/deployment/checks.rs`` do. A refusal reads ``<field>: <reason>`` in both libraries.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from scalo.deployment.contract import (
    DeploymentContract,
    EnabledCondition,
    EqualsCondition,
    OneOfCondition,
    PortContract,
    SecurityContract,
    WritablePath,
)
from scalo.deployment.keda import KafkaLagTrigger, KedaContract


def _contract(app_name: str = "app", **changes: Any) -> DeploymentContract:
    return DeploymentContract(
        app_name=app_name,
        metrics_port=9090,
        env_prefix="APP",
        metric_prefix="app",
        image_registry="registry.example.com",
        **changes,
    )


def _with_port(name: str = "web", **changes: Any) -> DeploymentContract:
    return _contract(extra_ports=[PortContract(name=name, port=8080, **changes)])


def _with_writable(path: str = "/var/lib/app/spool", **changes: Any) -> DeploymentContract:
    return _contract(writable_paths=[WritablePath(name="spool", path=path, **changes)])


def _refusal(build: Callable[[], object]) -> str:
    """Return the message a contract that must be refused is refused with."""
    with pytest.raises(ValidationError) as caught:
        build()
    errors = caught.value.errors()
    assert [error["type"] for error in errors] == ["value_error"], errors
    return errors[0]["msg"].removeprefix("Value error, ")


def _refused_field(build: Callable[[], object]) -> str:
    """Return the field a refusal names, which is the message up to its first ``: ``."""
    return _refusal(build).split(": ", 1)[0]


# ---- App name ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["app", "my-app", "a", "dfe-receiver", "app2", "a--b", "a" * 63])
def test_an_app_name_that_is_a_service_name_passes(name: str) -> None:
    assert _contract(app_name=name).app_name == name


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("", "is not 1 to 63 characters long"),
        ("a" * 64, "is not 1 to 63 characters long"),
        ("\u00e9" * 32, "is not 1 to 63 characters long"),
        ("My-app", "holds a character other than a lowercase letter, a digit or '-'"),
        ("my_app", "holds a character other than a lowercase letter, a digit or '-'"),
        ("my.app", "holds a character other than a lowercase letter, a digit or '-'"),
        ("my app", "holds a character other than a lowercase letter, a digit or '-'"),
        ("app\n", "holds a character other than a lowercase letter, a digit or '-'"),
        ("-App", "holds a character other than a lowercase letter, a digit or '-'"),
        ("1app", "does not start with a lowercase letter"),
        ("-app", "does not start with a lowercase letter"),
        ("1app-", "does not start with a lowercase letter"),
        ("app-", "ends with '-'"),
    ],
)
def test_a_contract_whose_app_name_is_not_a_service_name_is_refused(name: str, reason: str) -> None:
    message = _refusal(lambda: _contract(app_name=name))
    assert message.startswith("app_name: ")
    assert reason in message
    assert message.endswith(
        "must be a Kubernetes Service name: 1 to 63 lowercase letters, digits and inner hyphens, starting with a letter"
    )


# ---- Extra ports ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["http", "grpc", "syslog-udp", "a", "h2c", "web-api-2", "abcdefghijklmno"])
def test_a_port_name_kubernetes_takes_passes(name: str) -> None:
    assert _with_port(name=name).extra_ports[0].name == name


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("", "is not 1 to 15 characters long"),
        ("abcdefghijklmnop", "is not 1 to 15 characters long"),
        ("\u00e9" * 8, "is not 1 to 15 characters long"),
        ("Web", "holds a character other than a lowercase letter, a digit or '-'"),
        ("web_api", "holds a character other than a lowercase letter, a digit or '-'"),
        ("web.api", "holds a character other than a lowercase letter, a digit or '-'"),
        ("web api", "holds a character other than a lowercase letter, a digit or '-'"),
        ("web\n", "holds a character other than a lowercase letter, a digit or '-'"),
        ("8080", "has no letter"),
        ("-web", "starts or ends with '-', or has two in a row"),
        ("web-", "starts or ends with '-', or has two in a row"),
        ("we--b", "starts or ends with '-', or has two in a row"),
    ],
)
def test_a_port_name_kubernetes_refuses_is_refused(name: str, reason: str) -> None:
    message = _refusal(lambda: _with_port(name=name))
    assert message.startswith("extra_ports[0].name: ")
    assert reason in message


def test_a_port_is_named_by_its_index_until_its_name_is_valid() -> None:
    ports = [PortContract(name="web", port=80), PortContract(name="Bad", port=81)]
    assert _refused_field(lambda: _contract(extra_ports=ports)) == "extra_ports[1].name"


@pytest.mark.parametrize("protocol", ["TCP", "tcp", "Udp", "SCTP", "sctp"])
def test_a_protocol_kubernetes_takes_passes_in_any_case(protocol: str) -> None:
    assert _with_port(protocol=protocol).extra_ports[0].protocol == protocol


@pytest.mark.parametrize("protocol", ["", "icmp", "tcp ", "sctp\n", "\u017fctp"])
def test_a_protocol_kubernetes_does_not_take_is_refused(protocol: str) -> None:
    assert _refused_field(lambda: _with_port(protocol=protocol)) == "extra_ports[web].protocol"


@pytest.mark.parametrize(
    "when",
    [
        EnabledCondition(path="config.a\nb"),
        EnabledCondition(path="config.a\x85"),
        EqualsCondition(path="config.a\x00", value="on"),
        EqualsCondition(path="config.a", value="o\tn"),
        OneOfCondition(path="config\r.a", values=["x"]),
        OneOfCondition(path="config.a", values=["x", "y\x7f"]),
    ],
)
def test_a_control_character_in_a_port_condition_is_refused(when: Any) -> None:
    assert _refused_field(lambda: _with_port(when=when)) == "extra_ports[web].when"


@pytest.mark.parametrize(
    "when",
    [
        EnabledCondition(path="config.grpc.enabled"),
        EqualsCondition(path="config.source.transport", value="direct"),
        OneOfCondition(path="config.syslog.protocol", values=["udp", "both"]),
    ],
)
def test_a_port_condition_without_a_control_character_passes(when: Any) -> None:
    assert _with_port(when=when).extra_ports[0].when == when


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bound_from", "grpc.listen\n"),
        ("app_protocol", "h2c\nx"),
        ("app_protocol", "h2c\x7f"),
    ],
)
def test_a_control_character_in_a_port_text_is_refused(field: str, value: str) -> None:
    assert _refused_field(lambda: _with_port(**{field: value})) == f"extra_ports[web].{field}"


def test_a_format_character_is_not_a_control_character() -> None:
    # U+200B and U+00AD are category Cf, which Rust's char::is_control leaves alone.
    text = "h2c\u200b\u00ad"
    assert _with_port(app_protocol=text).extra_ports[0].app_protocol == text


# ---- Writable paths ---------------------------------------------------------------


def test_writable_paths_with_good_names_and_paths_pass() -> None:
    contract = _contract(
        writable_paths=[
            WritablePath(name="spool", path="/var/lib/app/spool", size_limit="2Gi"),
            WritablePath(name="state-2", path="/var/lib/app/state", persistent=True, size="5Gi"),
        ]
    )
    assert [writable.name for writable in contract.writable_paths] == ["spool", "state-2"]


@pytest.mark.parametrize("path", ["/sp\nool", "/spool\n", "/spool\x00", "/sp\x85ool"])
def test_a_control_character_in_a_writable_path_is_refused(path: str) -> None:
    assert _refused_field(lambda: _with_writable(path=path)) == "writable_paths[spool].path"


def test_a_control_character_in_a_writable_size_is_refused() -> None:
    assert _refused_field(lambda: _with_writable(persistent=True, size="5\nGi")) == "writable_paths[spool].size"


def test_a_control_character_in_a_writable_size_limit_is_refused() -> None:
    assert _refused_field(lambda: _with_writable(size_limit="2\nGi")) == "writable_paths[spool].size_limit"


def test_a_control_character_in_a_writable_condition_is_refused() -> None:
    when = OneOfCondition(path="config.a", values=["x", "y\nz"])
    assert _refused_field(lambda: _with_writable(when=when)) == "writable_paths[spool].when"


@pytest.mark.parametrize(
    ("name", "path", "loc"),
    [
        ("spool\n", "/spool", ("name",)),
        ("spool", "spool", ("path",)),
    ],
)
def test_a_writable_name_or_path_outside_its_pattern_is_refused(name: str, path: str, loc: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError) as caught:
        WritablePath(name=name, path=path)
    assert [(error["type"], error["loc"]) for error in caught.value.errors()] == [("string_pattern_mismatch", loc)]


# ---- Security ---------------------------------------------------------------------


def test_an_added_capability_must_be_a_capability_name() -> None:
    assert SecurityContract(capabilities_add=["NET_ADMIN", "SYS_NICE"]).capabilities_add == ["NET_ADMIN", "SYS_NICE"]
    for bad in ["net_admin", "CAP NET", "NET-ADMIN", "NET_ADMIN\n", ""]:
        with pytest.raises(ValidationError) as caught:
            SecurityContract(capabilities_add=[bad])
        assert [error["type"] for error in caught.value.errors()] == ["string_pattern_mismatch"], bad


# ---- KEDA -------------------------------------------------------------------------


def test_keda_with_nothing_to_scale_on_is_refused() -> None:
    keda = KedaContract(kafka_trigger=KafkaLagTrigger.disabled(), cpu_enabled=False)
    message = _refusal(lambda: _contract(keda=keda))
    assert message.startswith("keda: ")
    assert "both off" in message


def test_a_cpu_only_keda_needs_a_replica_to_start_from() -> None:
    keda = KedaContract(kafka_trigger=KafkaLagTrigger.disabled(), min_replicas=0)
    message = _refusal(lambda: _contract(keda=keda))
    assert message.startswith("keda.min_replicas: ")
    assert "cannot wake a workload from zero" in message


@pytest.mark.parametrize(
    "keda",
    [
        pytest.param(KedaContract(kafka_trigger=KafkaLagTrigger.disabled(), min_replicas=1), id="cpu-only-one-replica"),
        pytest.param(KedaContract(min_replicas=0), id="kafka-scales-to-zero"),
        pytest.param(KedaContract(cpu_enabled=False), id="kafka-only"),
        pytest.param(
            KedaContract(enabled=False, kafka_trigger=KafkaLagTrigger.disabled(), cpu_enabled=False, min_replicas=0),
            id="off-is-off",
        ),
        pytest.param(None, id="absent"),
    ],
)
def test_keda_with_a_trigger_to_scale_on_passes(keda: KedaContract | None) -> None:
    assert _contract(keda=keda).keda == keda


# ---- config_schema $ref ------------------------------------------------------------


@pytest.mark.parametrize(
    ("reference", "reason"),
    [
        ("#/$defs/Missing", "points at nothing"),
        ("https://example.com/schema.json", "is not local to the schema"),
        ("#/allOf/0", "points at nothing"),
    ],
)
def test_a_broken_or_remote_ref_the_dial_search_follows_is_refused(reference: str, reason: str) -> None:
    schema = {"properties": {"a": {"$ref": reference}}, "allOf": [{"type": "string"}]}
    assert _refusal(lambda: _contract(config_schema=schema)) == f"config_schema $ref {json.dumps(reference)} {reason}"


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param(
            {"properties": {"a": {"$ref": "#/$defs/A"}}, "$defs": {"A": {"$ref": "#/$defs/Missing"}}},
            id="chained-ref",
        ),
        pytest.param({"allOf": [{"properties": {"a": {"$ref": "#/$defs/Missing"}}}]}, id="inside-allOf"),
        pytest.param({"anyOf": [{"properties": {"a": {"$ref": "#/$defs/Missing"}}}]}, id="inside-anyOf"),
        pytest.param({"oneOf": [{"properties": {"a": {"$ref": "#/$defs/Missing"}}}]}, id="inside-oneOf"),
        pytest.param(
            {"properties": {"a": {"x-scalo-dial": "big", "items": {"$ref": "#/$defs/Missing"}}}},
            id="inside-a-dial",
        ),
        pytest.param(
            {"properties": {"a": {"x-scalo-dial": "big", "anyOf": [{"$ref": "#/$defs/Missing"}]}}},
            id="inside-a-list-in-a-dial",
        ),
    ],
)
def test_a_broken_ref_reached_through_the_schema_is_refused(schema: dict[str, Any]) -> None:
    assert _refusal(lambda: _contract(config_schema=schema)).endswith('"#/$defs/Missing" points at nothing')


def test_a_dial_referring_to_itself_is_refused() -> None:
    schema = {
        "properties": {"a": {"$ref": "#/$defs/Loop", "x-scalo-dial": "big"}},
        "$defs": {"Loop": {"properties": {"next": {"$ref": "#/$defs/Loop"}}}},
    }
    assert _refusal(lambda: _contract(config_schema=schema)) == 'config_schema $ref "#/$defs/Loop" refers to itself'


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param(
            {
                "type": "object",
                "properties": {
                    "buffer": {"$ref": "#/$defs/Buffer"},
                    "limit": {"anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}], "x-scalo-dial": "big"},
                },
                "$defs": {
                    "Buffer": {
                        "properties": {
                            "rows": {"type": "integer", "x-scalo-dial": "big"},
                            "age": {"$ref": "#/$defs/Seconds", "x-scalo-dial": "small", "default": 5},
                        }
                    },
                    "Seconds": {"type": "integer", "minimum": 0},
                },
            },
            id="refs-resolve",
        ),
        pytest.param(
            {"$ref": "#/$defs/Node", "$defs": {"Node": {"properties": {"child": {"$ref": "#/$defs/Node"}}}}},
            id="recursion-without-a-marker",
        ),
        pytest.param({"properties": {"a": {"items": {"$ref": "#/$defs/Missing"}}}}, id="ref-the-search-never-reaches"),
        pytest.param({"$defs": {"Orphan": {"properties": {"x": {"$ref": "#/$defs/Missing"}}}}}, id="unreferenced-def"),
    ],
)
def test_a_schema_whose_followed_refs_resolve_passes(schema: dict[str, Any]) -> None:
    assert _contract(config_schema=schema).config_schema == schema


# ---- A contract that sets every field the checks read -------------------------------


def test_a_contract_setting_every_field_the_checks_read_passes() -> None:
    contract = _contract(
        extra_ports=[
            PortContract(name="http", port=8080, bound_from="http.listen", public=True),
            PortContract(name="grpc", port=6000, app_protocol="kubernetes.io/h2c", when=EnabledCondition(path="c.a")),
            PortContract(name="syslog-udp", port=514, protocol="udp", when=OneOfCondition(path="c.p", values=["a"])),
        ],
        writable_paths=[
            WritablePath(name="spool", path="/var/lib/app/spool", size_limit="2Gi", when=EnabledCondition(path="c.s")),
            WritablePath(name="state", path="/var/lib/app/state", persistent=True, size="5Gi"),
        ],
        security=SecurityContract(capabilities_add=["NET_BIND_SERVICE"]),
        keda=KedaContract(kafka_trigger=KafkaLagTrigger.disabled(), min_replicas=1),
        config_schema={"properties": {"rows": {"type": "integer", "x-scalo-dial": "big"}}},
    )
    assert len(contract.extra_ports) == 3
