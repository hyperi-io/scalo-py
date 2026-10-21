#  Project:   scalo
#  File:      tests/unit/test_openapi_readers.py
#  Purpose:   The shared spec readers: $ref pointers, JSON media entries and merged parameters
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``scalo._openapi`` over hand-written specs, with neither the CLI nor MCP behind it."""

import ast
import sys
from pathlib import Path

import pytest

import scalo._openapi
from scalo._openapi import (
    MAX_REF_HOPS,
    RefResolver,
    is_json_media_type,
    is_read_only,
    is_reserved_header,
    json_media,
    merge_all_of,
    merged_parameters,
    non_null_member,
    non_null_type,
    unescape_pointer,
    wire_value,
)


def _chain(hops: int) -> tuple[dict, dict]:
    """A spec and a schema whose ``$ref`` chain takes ``hops`` pointers to reach a string schema."""
    schemas = {f"N{index}": {"$ref": f"#/components/schemas/N{index + 1}"} for index in range(1, hops)}
    schemas[f"N{hops}"] = {"type": "string"}
    return {"components": {"schemas": schemas}}, {"$ref": "#/components/schemas/N1"}


class TestRefs:
    """Local pointers, including chains, cycles and dead ends."""

    def test_a_chain_is_followed_to_its_schema(self):
        spec, schema = _chain(3)

        assert RefResolver(spec).resolve(schema) == {"type": "string"}

    def test_a_schema_without_a_ref_comes_back_as_a_copy(self):
        schema = {"type": "integer"}
        resolved = RefResolver({}).resolve(schema)

        assert resolved == schema
        assert resolved is not schema

    def test_the_longest_chain_that_resolves(self):
        spec, schema = _chain(MAX_REF_HOPS - 1)

        assert RefResolver(spec).resolve(schema) == {"type": "string"}

    def test_a_chain_past_the_limit_resolves_to_empty(self):
        spec, schema = _chain(MAX_REF_HOPS)

        assert RefResolver(spec).resolve(schema) == {}

    def test_a_cycle_resolves_to_empty(self):
        spec = {
            "components": {
                "schemas": {"A": {"$ref": "#/components/schemas/B"}, "B": {"$ref": "#/components/schemas/A"}}
            }
        }

        assert RefResolver(spec).resolve({"$ref": "#/components/schemas/A"}) == {}

    def test_a_dead_pointer_resolves_to_empty(self):
        assert RefResolver({}).resolve({"$ref": "#/components/schemas/Missing"}) == {}
        assert RefResolver({}).target("https://elsewhere/schema") is None

    def test_a_pointer_through_a_non_mapping_names_nothing(self):
        assert RefResolver({"tags": ["a"]}).target("#/tags/0") is None

    @pytest.mark.parametrize("value", [None, "text", 3, ["a"]])
    def test_a_non_mapping_resolves_to_empty(self, value):
        assert RefResolver({}).resolve(value) == {}

    def test_escaped_pointer_segments(self):
        spec = {"paths": {"/a/b": {"x": 1}, "~c": {"y": 2}}}

        assert RefResolver(spec).target("#/paths/~1a~1b/x") == 1
        assert RefResolver(spec).target("#/paths/~0c/y") == 2


class TestJsonMedia:
    """The first JSON entry of a content map, by media type suffix."""

    def test_the_first_json_entry_wins(self):
        content = {
            "text/plain": {"schema": {"type": "string"}},
            "application/json": {"schema": {"type": "object"}},
            "application/problem+json": {"schema": {"type": "array"}},
        }

        assert json_media(content) == {"schema": {"type": "object"}}

    def test_a_json_suffix_and_media_type_parameters(self):
        assert json_media({"application/merge-patch+json; charset=utf-8": {"schema": {}}}) == {"schema": {}}

    def test_a_media_type_in_any_case(self):
        assert json_media({"text/plain": {}, "Application/JSON": {"schema": {}}}) == {"schema": {}}

    def test_no_json_entry(self):
        assert json_media({"text/csv": {"schema": {}}}) is None

    @pytest.mark.parametrize("content", [None, [], "application/json", {"application/json": "not a mapping"}])
    def test_malformed_content_has_no_entry(self, content):
        assert json_media(content) is None

    @pytest.mark.parametrize(
        ("media_type", "expected"),
        [
            ("application/json", True),
            ("Application/JSON", True),
            ("application/VND.foo+JSON", True),
            ("application/problem+json; charset=utf-8", True),
            (" application/merge-patch+json ;q=1", True),
            ("text/plain", False),
            ("application/json-seq-not;x=json", False),
            ("application/x-ndjson", False),
            ("application/json-seq", False),
            ("text/notjson", False),
            ("", False),
        ],
    )
    def test_a_content_type_header(self, media_type, expected):
        assert is_json_media_type(media_type) is expected


class TestMergedParameters:
    """Path-item parameters merge with the operation's, which win a clash."""

    def test_the_operation_wins_a_clash_and_keeps_first_seen_order(self):
        item = {
            "parameters": [
                {"in": "path", "name": "widget", "description": "item"},
                {"in": "query", "name": "view"},
            ]
        }
        operation = {"parameters": [{"in": "path", "name": "widget", "description": "operation"}]}

        merged = merged_parameters(item, operation, RefResolver({}))

        assert merged == [{"in": "path", "name": "widget", "description": "operation"}, {"in": "query", "name": "view"}]

    def test_one_name_in_two_locations_is_two_parameters(self):
        operation = {"parameters": [{"in": "query", "name": "id"}, {"in": "header", "name": "id"}]}

        assert len(merged_parameters({}, operation, RefResolver({}))) == 2

    def test_references_are_resolved(self):
        spec = {
            "components": {"parameters": {"Limit": {"in": "query", "name": "limit", "schema": {"type": "integer"}}}}
        }
        operation = {"parameters": [{"$ref": "#/components/parameters/Limit"}]}

        assert merged_parameters({}, operation, RefResolver(spec)) == [
            {"in": "query", "name": "limit", "schema": {"type": "integer"}}
        ]

    def test_a_parameter_without_a_string_location_and_name_is_left_out(self):
        operation = {
            "parameters": [
                {"in": "query"},
                {"name": "orphan"},
                {"in": "query", "name": 7},
                {"$ref": "#/components/parameters/Missing"},
                "not a parameter",
            ]
        }

        assert merged_parameters({}, operation, RefResolver({})) == []

    def test_no_parameters(self):
        assert merged_parameters({}, {}, RefResolver({})) == []


class _CountingResolver(RefResolver):
    """A resolver that refuses to work past a budget, so a runaway walk fails instead of hanging."""

    def __init__(self, spec: dict, budget: int) -> None:
        super().__init__(spec)
        self.calls = 0
        self.budget = budget

    def resolve(self, value):
        self.calls += 1
        if self.calls > self.budget:
            raise RuntimeError(f"more than {self.budget} resolutions")
        return super().resolve(value)


class TestMergeAllOf:
    """Properties and required names through allOf, cycles included."""

    def test_members_merge_and_a_later_one_wins_a_clash(self):
        spec = {"components": {"schemas": {"Base": {"properties": {"a": {"type": "string"}}, "required": ["a"]}}}}
        schema = {
            "allOf": [{"$ref": "#/components/schemas/Base"}, {"properties": {"a": {"type": "integer"}, "b": {}}}],
            "required": ["b"],
        }

        properties, required = merge_all_of(schema, RefResolver(spec))

        assert properties == {"a": {"type": "integer"}, "b": {}}
        assert required == ["b", "a"]

    def test_a_schema_that_names_itself_twice_ends_at_once(self):
        a = {"allOf": [{"$ref": "#/components/schemas/A"}, {"$ref": "#/components/schemas/A"}], "properties": {"x": {}}}
        resolver = _CountingResolver({"components": {"schemas": {"A": a}}}, budget=100)

        assert merge_all_of({"$ref": "#/components/schemas/A"}, resolver) == ({"x": {}}, [])
        assert resolver.calls < 10

    def test_schemas_that_each_name_the_next_twice_cost_one_visit_each(self):
        depth = 24
        schemas: dict[str, dict] = {
            f"S{i}": {"allOf": [{"$ref": f"#/components/schemas/S{i + 1}"}] * 2} for i in range(depth)
        }
        schemas[f"S{depth}"] = {"properties": {"x": {}}}
        resolver = _CountingResolver({"components": {"schemas": schemas}}, budget=1000)

        assert merge_all_of({"$ref": "#/components/schemas/S0"}, resolver) == ({"x": {}}, [])


class TestSchemaHelpers:
    """Nullable members, list types and readOnly, as every reader sees them."""

    def test_the_non_null_member_as_written(self):
        member = {"$ref": "#/components/schemas/T"}
        spec = {"components": {"schemas": {"T": {"type": "string"}}}}

        assert non_null_member({"anyOf": [{"type": "null"}, member]}, RefResolver(spec)) is member
        assert non_null_member({"oneOf": [{"type": "null"}]}, RefResolver(spec)) is None
        assert non_null_member({"type": "string"}, RefResolver(spec)) is None

    @pytest.mark.parametrize(
        ("schema", "expected"), [({"type": ["null", "integer"]}, "integer"), ({"type": "string"}, "string"), ({}, None)]
    )
    def test_the_non_null_type(self, schema, expected):
        assert non_null_type(schema) == expected

    def test_read_only_directly_by_reference_and_inside_a_nullable(self):
        spec = {"components": {"schemas": {"Stamp": {"type": "string", "readOnly": True}}}}
        resolver = RefResolver(spec)

        assert is_read_only({"type": "string", "readOnly": True}, resolver)
        assert is_read_only({"$ref": "#/components/schemas/Stamp"}, resolver)
        assert is_read_only({"anyOf": [{"$ref": "#/components/schemas/Stamp"}, {"type": "null"}]}, resolver)
        assert not is_read_only({"type": "string"}, resolver)


class TestWire:
    """Pointer segments, reserved headers and the values a request carries."""

    @pytest.mark.parametrize(("segment", "key"), [("~1a~1b", "/a/b"), ("~0c", "~c"), ("~01", "~1"), ("plain", "plain")])
    def test_a_pointer_segment(self, segment, key):
        assert unescape_pointer(segment) == key

    @pytest.mark.parametrize(
        "name",
        [
            "Accept",
            "authorization",
            "Content-Type",
            "Host",
            "Forwarded",
            "X-Real-IP",
            "X-Forwarded-For",
            "x-oidc-email",
        ],
    )
    def test_reserved_headers(self, name):
        assert is_reserved_header(name)

    @pytest.mark.parametrize("name", ["X-Trace", "If-Match", "X-Request-Id"])
    def test_headers_a_caller_sets(self, name):
        assert not is_reserved_header(name)

    def test_wire_values(self):
        assert wire_value(True) == "true"
        assert wire_value([False, 1, "a"]) == ["false", 1, "a"]
        assert wire_value(3) == 3


def test_it_imports_the_standard_library_only():
    """Every spec reader imports this, so a third-party import here would cost each of their extras it."""
    tree = ast.parse(Path(scalo._openapi.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported, "no import found: the check is reading the wrong file"
    assert imported <= sys.stdlib_module_names, f"non-stdlib imports: {sorted(imported - sys.stdlib_module_names)}"
