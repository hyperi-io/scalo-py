# Project:   scalo
# File:      tests/unit/deployment/test_capability_parity.py
# Purpose:   Cross-language parity for the reflectable-config catalog (scalo-py#3)
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Parity + mechanism tests for the reflectable-config capability catalog.

The catalog shape MUST match scalo-rs (``scalo::deployment::Capability``) so
dfe-engine reflects on Rust- and Python-produced contracts through one code
path. The golden below is the shared shape from
``scalo-rs/docs/reflectable-config-shape.md``; if this fails, the Python and
Rust encodings have diverged.
"""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field, SecretStr

from scalo.deployment import (
    Capability,
    FieldSpec,
    FieldType,
    check_config_artifact_drift,
    config_schema_json,
    emit_config_artifacts,
)
from scalo.deployment.contract import DeploymentContract

# The golden shape (matches the Rust worked example): kind/name/description
# always present; maturity/fields/children omitted when empty; a FieldSpec emits
# name/type/required/description always, and default/secret/enum_values only when
# set (secret omitted when false).
GOLDEN = {
    "kind": "source",
    "name": "aws",
    "description": "AWS audit sources.",
    "maturity": "stable",
    "fields": [
        {"name": "id", "type": "string", "required": True, "description": "Connection id."},
        {
            "name": "region",
            "type": "string",
            "required": False,
            "default": "us-east-1",
            "description": "AWS region.",
        },
        {
            "name": "secret_access_key",
            "type": "secret",
            "required": False,
            "description": "AWS secret key.",
            "secret": True,
        },
    ],
    "children": [
        {
            "kind": "service",
            "name": "cloudwatch_logs",
            "description": "CloudWatch Logs.",
            "fields": [
                {
                    "name": "log_group_name",
                    "type": "string",
                    "required": True,
                    "description": "Log group.",
                }
            ],
        }
    ],
}


def _sample() -> Capability:
    return Capability.source(
        "aws",
        description="AWS audit sources.",
        maturity="stable",
        fields=[
            FieldSpec.string("id", required=True, description="Connection id."),
            FieldSpec.string("region", default="us-east-1", description="AWS region."),
            FieldSpec.secret_field("secret_access_key", description="AWS secret key."),
        ],
        children=[
            Capability.service(
                "cloudwatch_logs",
                description="CloudWatch Logs.",
                fields=[FieldSpec.string("log_group_name", required=True, description="Log group.")],
            )
        ],
    )


def test_capability_matches_rust_golden_shape() -> None:
    assert _sample().model_dump() == GOLDEN


def test_capability_json_round_trips() -> None:
    cap = _sample()
    dumped = json.loads(cap.model_dump_json())
    assert dumped == GOLDEN


def test_fieldtype_values_are_snake_case() -> None:
    assert FieldType.SECRET.value == "secret"
    assert FieldType.DURATION.value == "duration"
    assert [t.value for t in FieldType] == [
        "string",
        "int",
        "float",
        "bool",
        "secret",
        "enum",
        "duration",
        "list",
        "map",
        "object",
    ]


def test_empty_collections_and_false_secret_are_omitted() -> None:
    plain = FieldSpec.string("region").model_dump()
    assert set(plain) == {"name", "type", "required", "description"}
    assert "secret" not in plain
    assert "enum_values" not in plain

    cap = Capability.service("plain").model_dump()
    assert set(cap) == {"kind", "name", "description"}


def test_enum_values_emitted_when_present() -> None:
    f = FieldSpec.enumeration("include", ["all", "web", "git"], description="Which.").model_dump()
    assert f["type"] == "enum"
    assert f["enum_values"] == ["all", "web", "git"]


def test_config_schema_marks_secretstr_fields() -> None:
    class Cfg(BaseModel):
        host: str
        password: SecretStr

    schema = config_schema_json(Cfg)
    pw = schema["properties"]["password"]
    assert pw.get("x-scalo-secret") is True
    assert pw.get("writeOnly") is True
    # Non-secret field untouched.
    assert "x-scalo-secret" not in schema["properties"]["host"]


# The order scalo-rs's SensitiveString emits, per reflectable-config-shape.md "Secret marker".
SECRET_TAIL = ["x-scalo-secret", "writeOnly"]


def _vendor_keys(node: dict) -> list[str]:
    return [key for key in node if key.startswith("x-")]


@pytest.mark.parametrize(
    "extra",
    [{"x-scalo-secret": True}, {"x-scalo-secret": True, "writeOnly": True}],
    ids=["marker", "marker-and-writeonly"],
)
def test_author_marked_secret_ends_with_the_marker_in_order(extra: dict) -> None:
    """The marker opts a field in, and is emitted last but for ``writeOnly``, in scalo-rs's order."""

    class Cfg(BaseModel):
        token: str = Field(json_schema_extra=extra)

    token = config_schema_json(Cfg)["properties"]["token"]
    assert list(token)[-2:] == SECRET_TAIL, token
    assert all(token[key] is True for key in SECRET_TAIL)
    assert _vendor_keys(token) == ["x-scalo-secret"], token


def test_secretstr_ends_with_the_marker_in_order() -> None:
    class Cfg(BaseModel):
        password: SecretStr

    pw = config_schema_json(Cfg)["properties"]["password"]
    assert list(pw)[-2:] == SECRET_TAIL, pw
    assert pw["format"] == "password"
    assert _vendor_keys(pw) == ["x-scalo-secret"], pw


def test_a_false_marker_does_not_opt_a_field_in() -> None:
    class Cfg(BaseModel):
        note: str = Field(json_schema_extra={"x-scalo-secret": False})

    note = config_schema_json(Cfg)["properties"]["note"]
    assert note["x-scalo-secret"] is False
    assert "writeOnly" not in note


def test_an_unknown_vendor_key_does_not_opt_a_field_in() -> None:
    class Cfg(BaseModel):
        note: str = Field(json_schema_extra={"x-other-secret": True})

    note = config_schema_json(Cfg)["properties"]["note"]
    assert "x-scalo-secret" not in note
    assert "writeOnly" not in note


def test_nested_secret_is_marked_inside_defs() -> None:
    class Inner(BaseModel):
        key: SecretStr

    class Outer(BaseModel):
        inner: Inner

    key = config_schema_json(Outer)["$defs"]["Inner"]["properties"]["key"]
    assert list(key)[-2:] == SECRET_TAIL, key


def _contract_with_catalog() -> DeploymentContract:
    return DeploymentContract(
        app_name="demo",
        metrics_port=9090,
        env_prefix="DEMO",
        metric_prefix="demo",
        config_mount_path="/etc/demo/demo.yaml",
        image_registry="registry.example.com",
        config_schema={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"region": {"type": "string"}},
        },
        capabilities=[_sample()],
    )


def test_emit_writes_four_files_and_drift_passes(tmp_path: Path) -> None:
    contract = _contract_with_catalog()
    written = emit_config_artifacts(contract, tmp_path)
    names = {p.name for p in written}
    assert names == {
        "config-schema.json",
        "config-schema.yaml",
        "capability-catalog.json",
        "capability-catalog.yaml",
    }
    # Fresh emit -> no drift.
    check_config_artifact_drift(contract, tmp_path)


def test_drift_check_catches_planted_drift(tmp_path: Path) -> None:
    contract = _contract_with_catalog()
    emit_config_artifacts(contract, tmp_path)
    (tmp_path / "capability-catalog.json").write_text("[]\n", encoding="utf-8")
    from scalo.deployment import DeploymentError

    with pytest.raises(DeploymentError):
        check_config_artifact_drift(contract, tmp_path)


def test_emit_is_deterministic(tmp_path: Path) -> None:
    contract = _contract_with_catalog()
    a = tmp_path / "a"
    b = tmp_path / "b"
    emit_config_artifacts(contract, a)
    emit_config_artifacts(contract, b)
    for name in ("config-schema.json", "capability-catalog.json"):
        assert (a / name).read_text() == (b / name).read_text()


def test_contract_schema_version_is_v3() -> None:
    contract = _contract_with_catalog()
    assert contract.schema_version == 3
