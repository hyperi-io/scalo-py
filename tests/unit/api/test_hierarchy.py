#  Project:   scalo
#  File:      tests/unit/api/test_hierarchy.py
#  Purpose:   Operation ids and hierarchy problems derived from route paths
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The hierarchy reads one name per route method out of its path, and reports every rule the path breaks."""

import warnings

import pytest
from fastapi import APIRouter, FastAPI

from scalo.api import Hierarchy, scalo_extra

HIERARCHY = Hierarchy(base_path="/api/v1", singletons={"deployment", "identity", "usage", "compat"})


@pytest.mark.parametrize(
    ("method", "path", "operation_id"),
    [
        ("GET", "/api/v1/sources", "sources.list"),
        ("POST", "/api/v1/sources", "sources.create"),
        ("GET", "/api/v1/sources/{source}", "sources.get"),
        ("PUT", "/api/v1/sources/{source}", "sources.apply"),
        ("PATCH", "/api/v1/sources/{source}", "sources.update"),
        ("DELETE", "/api/v1/sources/{source}", "sources.delete"),
        ("GET", "/api/v1/sources/{source}/rules", "sources.rules.list"),
        ("PUT", "/api/v1/sources/{source}/rules/{rule}", "sources.rules.apply"),
        ("POST", "/api/v1/sources/{source}/deploy", "sources.deploy"),
        ("POST", "/api/v1/sources/{source}/rules/order", "sources.rules.order"),
        ("POST", "/api/v1/sources/{source}/rules/{rule}/move", "sources.rules.move"),
        ("POST", "/api/v1/orgs/{org}/members", "orgs.members.create"),
        ("GET", "/api/v1/deployment", "deployment.get"),
        ("PUT", "/api/v1/deployment", "deployment.apply"),
        ("POST", "/api/v1/deployment/sync", "deployment.sync"),
        ("GET", "/api/v1/deployment/apps/{app}/instances", "deployment.apps.instances.list"),
        ("GET", "/api/v1/identity/accounts", "identity.accounts.list"),
        ("GET", "/api/v1/orgs/{org}/usage", "orgs.usage.get"),
        ("GET", "/api/v1/sources/{source}/compat", "sources.compat.get"),
        ("GET", "/api/v1/compat-profiles", "compat-profiles.list"),
    ],
)
def test_the_path_names_the_operation(method, path, operation_id):
    name = HIERARCHY.parse(path, method)

    assert name.operation_id == operation_id
    assert name.problems == ()


def test_name_parts_follow_the_hierarchy():
    name = HIERARCHY.parse("/api/v1/sources/{source}/rules/{rule}", "get")

    assert name.hierarchy == ("sources", "rules")
    assert (name.group, name.resource, name.verb, name.depth) == ("sources", "rules", "get", 2)
    assert name.method == "GET"


class TestDeclaredVerb:
    """``scalo_extra(verb=...)`` says what the path cannot."""

    def test_a_declared_verb_equal_to_the_trailing_literal_makes_it_an_action(self):
        name = HIERARCHY.parse("/api/v1/sources/{source}/preview", "GET", verb="preview")

        assert name.operation_id == "sources.preview"
        assert name.problems == ()

    def test_without_the_declaration_the_same_get_reads_as_a_collection(self):
        name = HIERARCHY.parse("/api/v1/sources/{source}/preview", "GET")

        assert name.operation_id == "sources.preview.list"
        assert any("not plural" in problem for problem in name.problems)

    def test_a_declared_verb_that_differs_replaces_the_derived_one(self):
        name = HIERARCHY.parse("/api/v1/sources", "POST", verb="import")

        assert name.operation_id == "sources.import"

    def test_a_declared_verb_is_kebab_cased(self):
        assert HIERARCHY.parse("/api/v1/sources", "POST", verb="bulk_import").verb == "bulk-import"


class TestProblems:
    """Every rule a path breaks is reported, and the path still gets an id."""

    @pytest.mark.parametrize(
        ("method", "path", "fragment"),
        [
            ("GET", "/api/v1/backing_services", "not kebab-case"),
            ("GET", "/api/v1/backingServices", "not kebab-case"),
            ("GET", "/api/v1/topic", "'topic' is not plural"),
            ("GET", "/api/v1/{org}", "does not follow a collection"),
            ("GET", "/api/v1/sources/{a}/{b}", "does not follow a collection"),
            ("GET", "/api/v1/deployment/{id}", "does not follow a collection"),
            ("GET", "/healthz", "outside the base path"),
            ("PUT", "/api/v1/sources", "names no standard method"),
            ("POST", "/api/v1/sources/{source}", "needs an action segment"),
            ("PUT", "/api/v1/sources/order", "an action is a GET or a POST"),
            ("GET", "/api/v1/sources/search/{x}", "with no id between them"),
            ("GET", "/api/v1/files/{name}.json", "mixes text and a parameter"),
            ("GET", "/api/v1", "names no resource"),
        ],
    )
    def test_problem_is_reported(self, method, path, fragment):
        name = HIERARCHY.parse(path, method)

        assert any(fragment in problem for problem in name.problems), name.problems
        assert name.operation_id

    def test_a_non_kebab_segment_still_yields_a_kebab_id(self):
        assert HIERARCHY.parse("/api/v1/backing_services/{id}", "GET").operation_id == "backing-services.get"

    def test_depth_is_measured_not_reported_as_a_problem(self):
        name = Hierarchy(max_depth=2).parse("/a-items/{a}/b-items/{b}/c-items", "GET")

        assert name.depth == 3
        assert name.problems == ()

    def test_a_root_outside_the_declared_roots(self):
        hierarchy = Hierarchy(roots={"sources"})

        assert hierarchy.parse("/sources", "GET").problems == ()
        assert "root 'orgs' is not a declared root" in hierarchy.parse("/orgs", "GET").problems


class TestPlurals:
    """Collections are plural nouns."""

    @pytest.mark.parametrize("name", ["sources", "compat-profiles", "aliases", "data", "people"])
    def test_plural(self, name):
        assert HIERARCHY.is_plural(name)

    @pytest.mark.parametrize("name", ["source", "status", "access", "analysis", "deploy", "health"])
    def test_not_plural(self, name):
        assert not HIERARCHY.is_plural(name)

    def test_configured_plurals_extend_the_defaults(self):
        hierarchy = Hierarchy(plurals={"sheep"})

        assert hierarchy.is_plural("sheep")
        assert hierarchy.is_plural("data")


class TestConfiguration:
    """A bad hierarchy fails at construction, not at the first request."""

    def test_base_path_is_normalised(self):
        assert Hierarchy(base_path="api/v1/").base_path == "/api/v1"
        assert Hierarchy(base_path="/").base_path == ""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_depth": 0},
            {"tool_prefix": "Dfe-"},
            {"singletons": {"Deployment"}},
            {"roots": {"my_root"}},
            {"plurals": {"Sheep"}},
        ],
    )
    def test_invalid_configuration_raises(self, kwargs):
        with pytest.raises(ValueError):
            Hierarchy(**kwargs)

    def test_tool_name_joins_the_id_with_underscores(self):
        hierarchy = Hierarchy(tool_prefix="svc_")
        name = hierarchy.parse("/compat-profiles/{profile}", "DELETE")

        assert hierarchy.tool_name(name) == "svc_compat_profiles_delete"


class TestUniqueIdFunction:
    """FastAPI names every operation through ``Hierarchy.unique_id``."""

    def _app(self) -> FastAPI:
        rules = APIRouter(prefix="/rules")

        @rules.get("")
        def list_rules() -> list[str]:
            return []

        @rules.post("/order")
        def order_rules() -> list[str]:
            return []

        sources = APIRouter(prefix="/sources")

        @sources.get("/{source}/preview", openapi_extra=scalo_extra(verb="preview"))
        def preview(source: str) -> dict:
            return {}

        @sources.api_route("/{source}", methods=["GET", "HEAD"])
        def get_source(source: str) -> dict:
            return {}

        sources.include_router(rules, prefix="/{source}")
        app = FastAPI(generate_unique_id_function=HIERARCHY.unique_id)
        app.include_router(sources, prefix="/api/v1")
        return app

    def test_included_routers_are_named_from_their_full_path(self):
        with warnings.catch_warnings():
            # GET and HEAD share one operation id, which FastAPI warns about.
            warnings.simplefilter("ignore", UserWarning)
            spec = self._app().openapi()

        ids = {
            (method, path): operation["operationId"]
            for path, item in spec["paths"].items()
            for method, operation in item.items()
        }
        assert ids[("get", "/api/v1/sources/{source}/rules")] == "sources.rules.list"
        assert ids[("post", "/api/v1/sources/{source}/rules/order")] == "sources.rules.order"
        assert ids[("get", "/api/v1/sources/{source}/preview")] == "sources.preview"
        assert ids[("get", "/api/v1/sources/{source}")] == "sources.get"
        assert ids[("head", "/api/v1/sources/{source}")] == "sources.get"

    def test_unique_id_never_raises_on_an_unparseable_route(self):
        class Bare:
            pass

        assert HIERARCHY.unique_id(Bare()) == "root.get"
