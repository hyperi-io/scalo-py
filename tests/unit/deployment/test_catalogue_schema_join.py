# Project:   scalo
# File:      tests/unit/deployment/test_catalogue_schema_join.py
# Purpose:   The catalogue-to-schema join: schema_path resolution and its findings
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""A catalogue field's ``schema_path`` must reach a leaf of the config schema.

The rules and messages are scalo-rs's ``check_catalogue_against_schema``. The
fixture under ``tests/fixtures/reflectable-config/`` is the reference pair
scalo-rs emits, so scalo-py has to accept it as it stands.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from scalo.deployment import (
    Capability,
    DeploymentContract,
    DeploymentError,
    FieldSpec,
    check_catalogue_against_schema,
    check_config_artifact_drift,
    emit_config_artifacts,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "reflectable-config"
PREFIX = "capability store, field protocol: "
BOTH = ["http", "native"]
AT = "store.protocol"
PROTOCOL = {"type": "string", "enum": ["http", "native"]}

PLAIN = {"properties": {"protocol": PROTOCOL}}
NESTED = {"properties": {"store": {"type": "object", "properties": {"protocol": PROTOCOL}}}}
BEHIND_REF = {
    "properties": {"store": {"$ref": "#/$defs/Store"}},
    "$defs": {
        "Store": {
            "type": "object",
            "properties": {"protocol": {"description": "Wire protocol.", "$ref": "#/$defs/Protocol"}},
        },
        "Protocol": PROTOCOL,
    },
}
OPTION = {
    "properties": {"store": {"properties": {"protocol": {"anyOf": [{"$ref": "#/$defs/Protocol"}, {"type": "null"}]}}}},
    "$defs": {"Protocol": PROTOCOL},
}
OPTION_INLINE = {
    "properties": {
        "store": {"properties": {"protocol": {"type": ["string", "null"], "enum": ["http", "native", None]}}}
    }
}
ONE_OF_CONST = {
    "properties": {
        "store": {
            "properties": {
                "protocol": {
                    "oneOf": [
                        {"type": "string", "const": "http", "description": "Over HTTP."},
                        {"type": "string", "const": "native", "description": "The native protocol."},
                    ]
                }
            }
        }
    }
}
ONE_OF_MIXED = {
    "properties": {
        "store": {
            "properties": {
                "protocol": {"oneOf": [{"type": "string", "enum": ["http"]}, {"type": "string", "const": "native"}]}
            }
        }
    }
}
ONE_OF_OPEN = {
    "properties": {
        "store": {
            "properties": {
                "protocol": {"oneOf": [PROTOCOL, {"type": "object", "properties": {"custom": {"type": "string"}}}]}
            }
        }
    }
}
DRAFT7 = {
    "properties": {"store": {"allOf": [{"$ref": "#/definitions/Store"}]}},
    "definitions": {
        "Store": {"properties": {"protocol": {"$ref": "#/definitions/Protocol"}}},
        "Protocol": PROTOCOL,
    },
}
ESCAPED = {
    "properties": {"store": {"$ref": "#/$defs/store~1v2"}},
    "$defs": {"store/v2": {"properties": {"protocol": PROTOCOL}}},
}
FOREIGN = {"properties": {"store": {"$ref": "https://example.com/store.json"}}}
OPEN = {"properties": {"store": {"properties": {"protocol": {"type": "string"}}}}}

ARRAY_OF_OBJECTS = {
    "properties": {"tables": {"$ref": "#/$defs/Tables"}},
    "$defs": {
        "Tables": {"type": ["array", "null"], "items": {"$ref": "#/$defs/Table"}},
        "Table": {"properties": {"source": {"properties": {"protocol": PROTOCOL}}}},
    },
}
ARRAY_OF_ENUM = {"properties": {"protocols": {"type": "array", "items": PROTOCOL}}}
ARRAY_OF_ARRAYS = {"properties": {"matrix": {"type": "array", "items": {"type": "array", "items": PROTOCOL}}}}
TUPLE = {"properties": {"pair": {"type": "array", "prefixItems": [PROTOCOL, PROTOCOL], "items": False}}}
MAP_OF_OBJECTS = {
    "properties": {
        "stores": {
            "type": "object",
            "additionalProperties": {"anyOf": [{"$ref": "#/$defs/Store"}, {"type": "null"}]},
        }
    },
    "$defs": {"Store": {"properties": {"protocol": PROTOCOL}}},
}
MAP_OF_ARRAYS = {
    "properties": {"routes": {"type": "object", "additionalProperties": {"type": "array", "items": PROTOCOL}}}
}
PATTERN_MAP = {
    "properties": {
        "stores": {
            "type": "object",
            "additionalProperties": False,
            "patternProperties": {"^[a-z]+$": {"properties": {"protocol": PROTOCOL}}},
        }
    }
}
TWO_PATTERNS = {
    "properties": {
        "stores": {
            "type": "object",
            "patternProperties": {
                "^a": {"properties": {"protocol": PROTOCOL}},
                "^b": {"properties": {"protocol": PROTOCOL}},
            },
        }
    }
}

# (name, schema, schema_path, enum_values, the piece of the one finding expected or None)
CASES: list[tuple[str, dict[str, Any] | None, str | None, list[str], str | None]] = [
    ("plain property", PLAIN, "protocol", BOTH, None),
    ("nested struct", NESTED, AT, BOTH, None),
    ("behind $ref", BEHIND_REF, AT, BOTH, None),
    ("Option behind anyOf", OPTION, AT, BOTH, None),
    ("Option of an inline enum", OPTION_INLINE, AT, BOTH, None),
    ("enum via oneOf/const", ONE_OF_CONST, AT, BOTH, None),
    ("oneOf of enum and const arms", ONE_OF_MIXED, AT, BOTH, None),
    ("draft-07 definitions behind allOf", DRAFT7, AT, BOTH, None),
    ("JSON-pointer-escaped $ref", ESCAPED, AT, BOTH, None),
    ("catalogue order is not compared", NESTED, AT, ["native", "http"], None),
    ("path without enum_values", OPEN, AT, [], None),
    ("no schema_path, no enum_values", NESTED, None, [], None),
    (
        "path missing",
        NESTED,
        "store.proto",
        BOTH,
        'names no option in the config schema (no "proto" under "store")',
    ),
    ("path missing at the top", NESTED, "sink.protocol", BOTH, '(no "sink" at the top level)'),
    ("empty segment", NESTED, "store..protocol", BOTH, "(the path has an empty segment)"),
    ("$ref outside the document", FOREIGN, AT, BOTH, '(no "protocol" under "store")'),
    (
        "enum set differs",
        BEHIND_REF,
        AT,
        ["http"],
        'enum_values ["http"] but "store.protocol" in the schema allows ["http", "native"]',
    ),
    (
        "leaf has no enum",
        OPEN,
        AT,
        BOTH,
        'enum_values ["http", "native"] but "store.protocol" in the schema has no enum',
    ),
    ("open oneOf has no enum", ONE_OF_OPEN, AT, BOTH, "in the schema has no enum"),
    (
        "enum_values without schema_path",
        NESTED,
        None,
        BOTH,
        'enum_values ["http", "native"] but no schema_path',
    ),
    (
        "schema absent",
        None,
        AT,
        BOTH,
        'schema_path "store.protocol" is set but the contract has no config_schema',
    ),
    ("array of objects behind $ref", ARRAY_OF_OBJECTS, "tables[].source.protocol", BOTH, None),
    ("array of enum", ARRAY_OF_ENUM, "protocols[]", BOTH, None),
    ("array of arrays", ARRAY_OF_ARRAYS, "matrix[][]", BOTH, None),
    ("map of objects behind anyOf", MAP_OF_OBJECTS, "stores{}.protocol", BOTH, None),
    ("map of arrays", MAP_OF_ARRAYS, "routes{}[]", BOTH, None),
    ("map by one patternProperties", PATTERN_MAP, "stores{}.protocol", BOTH, None),
    (
        "an array without [] has no enum",
        ARRAY_OF_ENUM,
        "protocols",
        BOTH,
        '"protocols" in the schema has no enum',
    ),
    ("name missing after []", ARRAY_OF_OBJECTS, "tables[].sink", [], '(no "sink" under "tables[]")'),
    ("[] on an object", NESTED, "store[].protocol", BOTH, '("store" is not an array (segment "store[]"))'),
    (
        "{} on an array",
        ARRAY_OF_ENUM,
        "protocols{}",
        BOTH,
        '("protocols" is not a map (segment "protocols{}"))',
    ),
    (
        "second step on the wrong kind",
        MAP_OF_ARRAYS,
        "routes{}{}",
        BOTH,
        '("routes{}" is not a map (segment "routes{}{}"))',
    ),
    (
        "{} on several patternProperties",
        TWO_PATTERNS,
        "stores{}.protocol",
        BOTH,
        '("stores" is not a map (segment "stores{}"))',
    ),
    (
        "[] on a tuple",
        TUPLE,
        "pair[]",
        BOTH,
        '("pair" is a tuple (prefixItems), which [] can\'t step into (segment "pair[]"))',
    ),
    (
        "segment with an index",
        ARRAY_OF_ENUM,
        "protocols[0]",
        BOTH,
        '(segment "protocols[0]" is not a name followed by any of [] and {})',
    ),
    ("segment with no name", ARRAY_OF_ENUM, "[]", BOTH, '(segment "[]" is not a name followed by any of [] and {})'),
]


def _contract(schema: dict[str, Any] | None, capabilities: list[Capability]) -> DeploymentContract:
    """A contract holding only the two halves under test, built unvalidated so a foreign ``$ref`` can be set."""
    return DeploymentContract.model_construct(config_schema=schema, capabilities=capabilities)


@pytest.mark.parametrize(("name", "schema", "path", "values", "want"), CASES, ids=[c[0] for c in CASES])
def test_catalogue_check_follows_each_schema_shape(
    name: str, schema: dict[str, Any] | None, path: str | None, values: list[str], want: str | None
) -> None:
    field = FieldSpec(name="protocol", enum_values=values, schema_path=path)
    findings = check_catalogue_against_schema(_contract(schema, [Capability.service("store", fields=[field])]))
    if want is None:
        assert findings == [], name
    else:
        assert len(findings) == 1, findings
        assert findings[0].startswith(PREFIX), findings[0]
        assert want in findings[0], findings[0]


def test_catalogue_check_walks_children_in_order() -> None:
    schema = {"properties": {"store": {"properties": {"host": {"type": "string"}}}}}
    capability = Capability.service(
        "store",
        fields=[
            FieldSpec.string("host", schema_path="store.host"),
            FieldSpec.string("port", schema_path="store.port"),
        ],
        children=[
            Capability.service("tls", fields=[FieldSpec.enumeration("mode", ["off", "verify"])]),
        ],
    )
    findings = check_catalogue_against_schema(_contract(schema, [capability]))
    assert len(findings) == 2, findings
    assert findings[0].startswith("capability store, field port: ")
    assert findings[1].startswith("capability store/tls, field mode: ")


def test_schema_path_is_emitted_only_when_set() -> None:
    assert "schema_path" not in FieldSpec.string("region").model_dump()
    assert FieldSpec.string("region", schema_path="a.b").model_dump()["schema_path"] == "a.b"


def test_drift_check_fails_when_the_catalogue_and_schema_disagree(tmp_path: Path) -> None:
    schema = {"properties": {"protocol": PROTOCOL}}
    field = FieldSpec.enumeration("protocol", ["http"], schema_path="protocol")
    contract = _contract(schema, [Capability.service("store", fields=[field])])
    emit_config_artifacts(contract, tmp_path)
    with pytest.raises(DeploymentError) as raised:
        check_config_artifact_drift(contract, tmp_path)
    message = str(raised.value)
    assert "capability-catalog.json" in message
    assert 'capability store, field protocol: enum_values ["http"]' in message


def test_reflectable_config_fixture_joins() -> None:
    """The reference pair scalo-rs emits passes the check scalo-py runs."""
    schema = json.loads((FIXTURE / "config-schema.json").read_text(encoding="utf-8"))
    catalogue = json.loads((FIXTURE / "capability-catalog.json").read_text(encoding="utf-8"))
    contract = _contract(schema, [Capability.model_validate(entry) for entry in catalogue])
    assert check_catalogue_against_schema(contract) == []
    assert [c.model_dump() for c in contract.capabilities] == catalogue
