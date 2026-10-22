#  Project:   scalo
#  File:      tests/unit/cli_openapi/test_spec.py
#  Purpose:   Reading a spec into operations: placement, parameters, bodies, refs and loading
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``iter_operations`` and ``load_spec`` over a hand-written spec with no scalo.api behind it."""

import json
import threading
from pathlib import Path

import pytest

import scalo.cli.openapi
from scalo.cli.openapi import SpecCli, SpecError, load_spec
from scalo.cli.openapi.naming import api_segments, derive_group_and_verb, kebab
from scalo.cli.openapi.skeleton import skeleton
from scalo.cli.openapi.spec import Field, iter_operations

WIDGETS = Path(__file__).resolve().parents[2] / "fixtures" / "openapi" / "widgets.yaml"


@pytest.fixture(scope="module")
def widgets() -> dict:
    return load_spec(WIDGETS)


@pytest.fixture(scope="module")
def operations(widgets) -> dict:
    return {op.command_path: op for op in iter_operations(widgets)}


class TestPlacement:
    """x-scalo first, then a dotted operationId, then the path."""

    def test_every_operation_is_placed(self, operations):
        assert sorted(operations) == [
            ("maintenance", "debug"),
            ("maintenance", "flush"),
            ("reports", "daily", "run"),
            ("widgets", "apply"),
            ("widgets", "create"),
            ("widgets", "delete"),
            ("widgets", "get"),
            ("widgets", "list"),
            ("widgets", "parts", "list"),
            ("widgets", "rotate"),
        ]

    def test_x_scalo_hints(self, operations):
        flush = operations[("maintenance", "flush")]

        assert flush.aliases == ("purge",)
        assert not flush.hidden
        assert operations[("maintenance", "debug")].hidden

    def test_read_only_follows_the_method_without_x_scalo(self, operations):
        assert operations[("widgets", "list")].read_only
        assert not operations[("widgets", "create")].read_only

    def test_an_operation_without_an_id_is_named_by_method_and_path(self, operations):
        assert operations[("widgets", "rotate")].operation_id == "POST /api/v1/widgets/{widget}/rotate"
        assert operations[("reports", "daily", "run")].operation_id == "reports.daily.run"

    def test_a_malformed_x_scalo_falls_back(self):
        spec = {
            "paths": {"/things": {"get": {"operationId": "things.list", "x-scalo": {"hierarchy": [1], "verb": "x"}}}}
        }

        assert next(iter_operations(spec)).command_path == ("things", "list")

    def test_hidden_operations_have_no_command(self, widgets):
        paths = SpecCli(widgets, name="w").command_paths()

        assert ("maintenance", "debug") not in paths
        assert ("maintenance", "flush") in paths
        assert ("maintenance", "purge") not in paths


class TestNaming:
    """The path fallback, with scalo.api's verbs."""

    @pytest.mark.parametrize(
        ("path", "method", "expected"),
        [
            ("/api/v1/orgs", "get", (["orgs"], "list")),
            ("/api/v1/orgs", "post", (["orgs"], "create")),
            ("/api/v1/orgs/{org}", "get", (["orgs"], "get")),
            ("/api/v1/orgs/{org}", "put", (["orgs"], "apply")),
            ("/api/v1/orgs/{org}", "patch", (["orgs"], "update")),
            ("/api/v1/orgs/{org}", "delete", (["orgs"], "delete")),
            ("/api/v1/orgs/{org}", "post", (["orgs"], "post")),
            ("/api/v1/orgs/{org}/sync", "post", (["orgs"], "sync")),
            ("/api/v1/orgs/reindex", "post", (["orgs"], "reindex")),
            ("/api/v1/auth/backingServices", "get", (["auth", "backing-services"], "list")),
            ("/api/v1", "get", ([], "get")),
        ],
    )
    def test_derived_names(self, path, method, expected):
        assert derive_group_and_verb(path, method, {"orgs"}) == expected

    def test_a_collection_without_an_item_route_takes_a_post_as_an_action(self):
        assert derive_group_and_verb("/api/v1/jobs", "post", set()) == ([], "jobs")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("backing_services", "backing-services"),
            ("BackingServices", "backing-services"),
            ("Backing_Services", "backing-services"),
            ("API-Keys", "api-keys"),
        ],
    )
    def test_kebab_is_always_lower_case(self, name, expected):
        assert kebab(name) == expected

    def test_an_explicit_base_path(self):
        assert api_segments("/svc/v2/things", "/svc/v2") == ["things"]
        assert api_segments("/other/things", "/svc/v2") == ["other", "things"]
        assert api_segments("/things") == ["things"]


class TestParameters:
    """Parameters merge from the path item, refs resolve, and client headers are left out."""

    def test_path_item_parameters_and_header_options(self, operations):
        names = {(f.location, f.name) for f in operations[("widgets", "get")].parameters}

        assert names == {("path", "widget"), ("header", "X-Trace")}

    def test_a_referenced_parameter_with_an_enum(self, operations):
        colour = next(f for f in operations[("widgets", "list")].parameters if f.name == "colour")

        assert colour == Field(
            name="colour",
            location="query",
            type="str",
            description="Only widgets of this colour",
            enum=("red", "green"),
        )

    def test_arrays_and_nullable_types(self, operations):
        fields = {f.name: f for f in operations[("widgets", "list")].parameters}

        assert (fields["tag"].type, fields["tag"].item_type) == ("array", "str")
        assert (fields["limit"].type, fields["limit"].default) == ("int", 10)

    def test_a_list_without_page_token_is_not_paginated(self, operations):
        assert not operations[("widgets", "list")].paginated

    def test_headers_a_client_or_a_proxy_sets_are_never_options(self):
        headers = ["Host", "X-Forwarded-For", "X-Forwarded-Proto", "X-Real-IP", "Forwarded", "X-Oidc-Email", "X-Trace"]
        spec = {
            "paths": {
                "/things": {"get": {"parameters": [{"name": name, "in": "header"} for name in headers]}},
            }
        }

        assert [field.name for field in next(iter_operations(spec)).parameters] == ["X-Trace"]


class TestBodies:
    """Request bodies flatten through allOf, and non-JSON-object bodies keep only --body."""

    def test_all_of_merges_properties_and_required(self, operations):
        fields = {f.name: f for f in operations[("widgets", "create")].body}

        assert set(fields) == {"name", "size", "enabled", "parent", "parts"}
        assert fields["name"].required
        assert fields["parts"].required
        assert (fields["parts"].type, fields["parts"].item_type) == ("array", "object")
        assert fields["parent"].type == "object"

    def test_a_json_suffixed_media_type_is_a_json_body(self, operations):
        put = operations[("widgets", "apply")]

        assert put.body == ()
        assert put.body_schema == {"type": "object"}

    def test_no_body(self, operations):
        assert operations[("widgets", "rotate")].body_schema is None

    def test_read_only_properties_are_neither_options_nor_skeleton_fields(self):
        item = {
            "type": "object",
            "properties": {"id": {"type": "string", "readOnly": True}, "name": {"type": "string"}},
        }
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "readOnly": True},
                "name": {"type": "string"},
                "items": {"type": "array", "items": item},
            },
        }
        spec = {"paths": {"/things": {"post": {"requestBody": {"content": {"application/json": {"schema": schema}}}}}}}
        operation = next(iter_operations(spec))

        assert [field.name for field in operation.body] == ["name", "items"]
        assert skeleton(operation, spec)["body"] == {"name": None, "items": [{"name": None}]}

    def test_an_all_of_that_names_itself_twice_reads_in_time(self):
        schema = {"allOf": [{"$ref": "#/components/schemas/A"}, {"$ref": "#/components/schemas/A"}]}
        spec = {
            "components": {"schemas": {"A": schema}},
            "paths": {
                "/a": {
                    "post": {
                        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/A"}}}}
                    }
                }
            },
        }
        finished = threading.Event()

        def read() -> None:
            SpecCli(spec, name="a")
            finished.set()

        threading.Thread(target=read, daemon=True).start()

        assert finished.wait(5), "a self-referencing allOf did not finish reading in 5 s"


class TestPublicSurface:
    """The package exports what the docs name and nothing else."""

    def test_the_exports(self):
        assert sorted(scalo.cli.openapi.__all__) == [
            "Credential",
            "Invocation",
            "Response",
            "ScaloHttpTransport",
            "SpecCli",
            "SpecError",
            "Store",
            "Transport",
            "TransportError",
            "UrllibTransport",
            "invocation",
            "load_spec",
        ]


class TestLoad:
    """A spec loads from a mapping, a JSON or YAML file, or a URL."""

    def test_json_file(self, tmp_path, widgets):
        path = tmp_path / "spec.json"
        path.write_text(json.dumps(widgets), encoding="utf-8")

        assert load_spec(path) == widgets

    def test_a_document_without_paths_is_refused(self, tmp_path):
        path = tmp_path / "spec.json"
        path.write_text('{"openapi": "3.1.0"}', encoding="utf-8")

        with pytest.raises(SpecError, match="no 'paths'"):
            load_spec(path)

    def test_neither_json_nor_yaml(self, tmp_path):
        path = tmp_path / "spec.txt"
        path.write_text("{: [", encoding="utf-8")

        with pytest.raises(SpecError, match="neither JSON nor YAML"):
            load_spec(path)

    def test_a_server_s_openapi_json(self, http_server, widgets):
        server = http_server()
        server.route("GET", "/openapi.json", (200, {"Content-Type": "application/json"}, json.dumps(widgets).encode()))

        assert load_spec(f"{server.url}/openapi.json") == widgets
        assert server.seen[0]["headers"]["accept"] == "application/json"

    def test_a_url_that_answers_an_error(self, http_server):
        server = http_server()

        with pytest.raises(SpecError, match="answered 404"):
            load_spec(f"{server.url}/openapi.json")

    def test_the_spec_alone_builds_the_cli_from_a_served_spec(self, http_server, spec):
        server = http_server()
        server.route("GET", "/openapi.json", (200, {}, json.dumps(spec).encode()))

        assert ("sources", "rules", "list") in SpecCli(
            load_spec(f"{server.url}/openapi.json"), name="svc"
        ).command_paths()
