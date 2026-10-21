#  Project:   scalo
#  File:      tests/unit/mcp/test_tools.py
#  Purpose:   tools_from_spec turns x-scalo opt-ins into tools, and refuses a spec they cannot keep
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``tools_from_spec`` over the service's real spec, and over specs that break one rule each."""

import copy

import pytest
from common.mcp_service import TOOLS, Store, build_app
from jsonschema import Draft202012Validator

from scalo.api import EXTENSION
from scalo.mcp import Argument, McpSpecError, tools_from_spec


@pytest.fixture(scope="module")
def spec() -> dict:
    app, _ = build_app(Store())
    return app.openapi()


@pytest.fixture(scope="module")
def tools(spec) -> dict:
    return {tool.name: tool for tool in tools_from_spec(spec)}


def _operation(spec: dict, method: str, path: str) -> dict:
    return spec["paths"][path][method]


class TestFromTheServiceSpec:
    def test_the_tools_are_the_opt_ins_sorted_by_name(self, tools):
        assert list(tools) == TOOLS

    def test_a_get_takes_its_path_and_response_format(self, tools):
        tool = tools["svc_sources_get"]
        schema = tool.input_schema

        assert (tool.read_only, tool.dry_run, tool.if_match) == (True, False, False)
        assert schema["required"] == ["source"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["response_format"]["$ref"] == "#/$defs/View"
        assert schema["$defs"]["View"]["enum"] == ["basic", "full"]
        assert Argument("response_format", "query", "view") in tool.arguments

    def test_an_apply_takes_a_body_dry_run_and_preview_token_but_no_precondition_headers(self, tools):
        tool = tools["svc_sources_apply"]
        properties = tool.input_schema["properties"]

        assert (tool.dry_run, tool.if_match, tool.if_none_match, tool.body) == (True, True, True, True)
        assert sorted(properties) == ["body", "dry_run", "preview_token", "source"]
        assert properties["dry_run"]["default"] is True
        assert properties["body"] == {"$ref": "#/$defs/SourceSpec"}
        assert tool.input_schema["required"] == ["source", "body"]
        assert {argument.wire for argument in tool.arguments} == {"source"}

    def test_a_post_action_previews_without_an_etag_but_commits_its_preview_token(self, tools):
        tool = tools["svc_sources_deploy"]

        assert (tool.dry_run, tool.if_match) == (True, False)
        assert sorted(tool.input_schema["properties"]) == ["dry_run", "preview_token", "source"]
        assert tool.task

    def test_a_list_keeps_its_paging_parameters(self, tools):
        properties = tools["svc_sources_list"].input_schema["properties"]

        assert {"page_size", "page_token", "filter", "order_by"} <= set(properties)

    def test_every_input_schema_is_valid_json_schema(self, tools):
        for tool in tools.values():
            Draft202012Validator.check_schema(tool.input_schema)

    def test_generating_twice_gives_the_same_tools(self, spec):
        assert tools_from_spec(spec) == tools_from_spec(copy.deepcopy(spec))

    def test_a_spec_without_opt_ins_has_no_tools(self, spec):
        bare = copy.deepcopy(spec)
        for item in bare["paths"].values():
            for operation in item.values():
                operation[EXTENSION].pop("mcp", None)

        assert tools_from_spec(bare) == ()


def _spec(paths: dict, schemas: dict | None = None) -> dict:
    return {"openapi": "3.1.0", "paths": paths, "components": {"schemas": schemas or {}}}


def _write(tool: str, *, method: str = "put", parameters: list | None = None, body: dict | None = None) -> dict:
    operation = {
        "operationId": tool,
        "parameters": parameters if parameters is not None else [{"name": "dry_run", "in": "query"}],
        EXTENSION: {"read_only": False, "mcp": {"tool": tool, "read_only": False, "destructive": False, "task": False}},
        "responses": {"200": {"description": "ok"}},
    }
    if body is not None:
        operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": body}}}
    return {method: operation}


def _read(tool: str) -> dict:
    return {
        "get": {
            "operationId": tool,
            EXTENSION: {
                "read_only": True,
                "mcp": {"tool": tool, "read_only": True, "destructive": False, "task": False},
            },
            "responses": {"200": {"description": "ok"}},
        }
    }


class TestRefusals:
    """A spec whose tools could not keep the contract fails generation, naming why."""

    def test_two_tools_with_one_name(self):
        spec = _spec({"/a": _read("same"), "/b": _read("same")})

        with pytest.raises(McpSpecError, match="names both GET /a and GET /b"):
            tools_from_spec(spec)

    def test_a_name_mcp_does_not_allow(self):
        with pytest.raises(McpSpecError, match="not one MCP allows"):
            tools_from_spec(_spec({"/a": _read("has space")}))

    def test_a_write_hinted_read_only_cannot_skip_its_preview(self):
        spec = _spec({"/a": _write("w")})
        spec["paths"]["/a"]["put"][EXTENSION]["mcp"]["read_only"] = True

        with pytest.raises(McpSpecError, match="disagrees"):
            tools_from_spec(spec)

    def test_a_write_without_dry_run(self):
        with pytest.raises(McpSpecError, match="takes no dry_run"):
            tools_from_spec(_spec({"/a": _write("w", parameters=[])}))

    def test_an_if_match_write_with_no_get_to_read_the_etag_from(self):
        parameters = [{"name": "dry_run", "in": "query"}, {"name": "If-Match", "in": "header"}]

        with pytest.raises(McpSpecError, match="has no GET"):
            tools_from_spec(_spec({"/a": _write("w", parameters=parameters)}))

    def test_a_parameter_that_takes_a_reserved_argument_name(self):
        parameters = [{"name": "dry_run", "in": "query"}, {"name": "body", "in": "query"}]

        with pytest.raises(McpSpecError, match="two arguments are named 'body'"):
            tools_from_spec(_spec({"/a": _write("w", parameters=parameters, body={"type": "object"})}))

    def test_a_reference_that_leads_nowhere(self):
        with pytest.raises(McpSpecError, match="names no schema"):
            tools_from_spec(_spec({"/a": _write("w", body={"$ref": "#/components/schemas/Gone"})}))

    def test_a_reference_outside_the_schemas(self):
        with pytest.raises(McpSpecError, match="not under"):
            tools_from_spec(_spec({"/a": _write("w", body={"$ref": "#/paths/~1a"})}))


class TestSchemas:
    def test_a_schema_that_references_itself_is_copied_once(self):
        node = {
            "type": "object",
            "properties": {"children": {"type": "array", "items": {"$ref": "#/components/schemas/Node"}}},
        }
        spec = _spec({"/a": _write("w", body={"$ref": "#/components/schemas/Node"})}, {"Node": node})

        (tool,) = tools_from_spec(spec)

        assert tool.input_schema["$defs"]["Node"]["properties"]["children"]["items"] == {"$ref": "#/$defs/Node"}
        Draft202012Validator.check_schema(tool.input_schema)

    def test_a_header_parameter_reads_as_snake_case(self):
        parameters = [{"name": "dry_run", "in": "query"}, {"name": "X-Trace-Id", "in": "header", "required": True}]

        (tool,) = tools_from_spec(_spec({"/a": _write("w", method="post", parameters=parameters)}))

        assert Argument("x_trace_id", "header", "X-Trace-Id") in tool.arguments
        assert tool.input_schema["required"] == ["x_trace_id"]

    def test_transport_headers_and_cookies_are_never_arguments(self):
        parameters = [
            {"name": "dry_run", "in": "query"},
            {"name": "Authorization", "in": "header"},
            {"name": "session", "in": "cookie"},
        ]

        (tool,) = tools_from_spec(_spec({"/a": _write("w", method="post", parameters=parameters)}))

        assert tool.arguments == ()
        assert sorted(tool.input_schema["properties"]) == ["dry_run", "preview_token"]

    @pytest.mark.parametrize(
        "header", ["X-Forwarded-For", "x-forwarded-host", "X-Real-IP", "Forwarded", "X-Oidc-Email", "Host"]
    )
    def test_a_header_a_proxy_owns_is_never_an_argument(self, header):
        parameters = [{"name": "dry_run", "in": "query"}, {"name": header, "in": "header", "required": True}]

        (tool,) = tools_from_spec(_spec({"/a": _write("w", method="post", parameters=parameters)}))

        assert tool.arguments == ()
        assert "required" not in tool.input_schema

    def test_a_read_takes_no_precondition_header(self):
        spec = _spec({"/a": _read("r")})
        spec["paths"]["/a"]["get"]["parameters"] = [
            {"name": "If-None-Match", "in": "header"},
            {"name": "If-Match", "in": "header"},
            {"name": "q", "in": "query"},
        ]

        (tool,) = tools_from_spec(spec)

        assert tool.arguments == (Argument("q", "query", "q"),)
        assert sorted(tool.input_schema["properties"]) == ["q"]

    def test_a_parameter_description_reaches_its_argument(self):
        parameters = [{"name": "dry_run", "in": "query"}, {"name": "q", "in": "query", "description": "What to find"}]

        (tool,) = tools_from_spec(_spec({"/a": _write("w", method="post", parameters=parameters)}))

        assert tool.input_schema["properties"]["q"]["description"] == "What to find"
