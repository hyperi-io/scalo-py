#  Project:   scalo
#  File:      tests/unit/api/test_openapi.py
#  Purpose:   x-scalo written onto every operation, the permission hook, and install()
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``annotate_openapi`` writes ``x-scalo`` from the path, the route's declarations and its permission dependencies."""

import copy

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.utils import get_openapi

from scalo.api import (
    ACTION_ATTRIBUTE,
    EXTENSION,
    CliHints,
    Hierarchy,
    McpHints,
    annotate_openapi,
    install,
    permission,
    scalo_extra,
)

HIERARCHY = Hierarchy(base_path="/api/v1", tool_prefix="svc_")


def require(action: str):
    """A consumer's RBAC dependency factory, marked with the action it checks."""

    @permission(action)
    def check() -> None:
        return None

    return check


def _app() -> FastAPI:
    router = APIRouter(prefix="/sources", dependencies=[Depends(require("source:read"))])

    @router.get("")
    def list_sources() -> list[str]:
        """List sources."""
        return []

    @router.delete("/{source}", openapi_extra=scalo_extra(mcp=McpHints()))
    def delete_source(source: str, _auth: None = Depends(require("source:write"))) -> None:
        """Delete a source."""

    def guarded_body(_auth: None = Depends(require("source:test"))) -> None:
        return None

    @router.post("/{source}/validate", dependencies=[Depends(guarded_body)])
    def validate_source(source: str) -> dict:
        """Validate a source."""
        return {}

    @router.post(
        "/{source}/test",
        openapi_extra=scalo_extra(read_only=True, cli=CliHints(aliases=("try",), positional=("source",))),
    )
    def test_source(source: str) -> dict:
        """Test a source."""
        return {}

    public = APIRouter(prefix="/status")

    @public.get("/{name}", openapi_extra=scalo_extra(public=True))
    def get_status(name: str) -> dict:
        """Get a status."""
        return {}

    @public.post("/{name}/rotate", openapi_extra=scalo_extra(action="status:rotate"))
    def rotate(name: str) -> dict:
        """Rotate a status."""
        return {}

    app = FastAPI(generate_unique_id_function=HIERARCHY.unique_id)
    app.include_router(router, prefix="/api/v1")
    app.include_router(public, prefix="/api/v1")
    return app


@pytest.fixture
def spec() -> dict:
    app = _app()
    install(app, HIERARCHY)
    return app.openapi()


def _ext(spec: dict, method: str, path: str) -> dict:
    return spec["paths"][path][method][EXTENSION]


class TestExtension:
    """What each operation's ``x-scalo`` carries."""

    def test_a_list_names_its_place_in_the_hierarchy(self, spec):
        assert _ext(spec, "get", "/api/v1/sources") == {
            "group": "sources",
            "resource": "sources",
            "hierarchy": ["sources"],
            "verb": "list",
            "read_only": True,
            "cli": {"hidden": False, "aliases": [], "positional": []},
            "action": "source:read",
        }

    def test_every_permission_dependency_is_collected(self, spec):
        ext = _ext(spec, "delete", "/api/v1/sources/{source}")

        assert ext["action"] == ["source:read", "source:write"]
        assert ext["read_only"] is False

    def test_a_permission_nested_in_another_dependency_is_found(self, spec):
        assert _ext(spec, "post", "/api/v1/sources/{source}/validate")["action"] == ["source:read", "source:test"]

    def test_an_opted_in_tool_gets_its_derived_hints(self, spec):
        assert _ext(spec, "delete", "/api/v1/sources/{source}")["mcp"] == {
            "tool": "svc_sources_delete",
            "read_only": False,
            "destructive": True,
            "task": False,
        }

    def test_an_operation_that_did_not_opt_in_has_no_tool(self, spec):
        assert "mcp" not in _ext(spec, "get", "/api/v1/sources")

    def test_declared_read_only_and_cli_hints_win(self, spec):
        ext = _ext(spec, "post", "/api/v1/sources/{source}/test")

        assert ext["verb"] == "test"
        assert ext["read_only"] is True
        assert ext["cli"] == {"hidden": False, "aliases": ["try"], "positional": ["source"]}

    def test_public_and_declared_action(self, spec):
        assert _ext(spec, "get", "/api/v1/status/{name}")["public"] is True
        assert "action" not in _ext(spec, "get", "/api/v1/status/{name}")
        assert _ext(spec, "post", "/api/v1/status/{name}/rotate")["action"] == "status:rotate"

    def test_operation_ids_are_the_hierarchy(self, spec):
        assert spec["paths"]["/api/v1/sources/{source}/test"]["post"]["operationId"] == "sources.test"


class TestAnnotate:
    """``annotate_openapi`` on a spec a consumer generates itself."""

    def test_annotating_twice_changes_nothing(self):
        app = _app()
        spec = get_openapi(title="t", version="1", routes=app.routes)
        once = copy.deepcopy(annotate_openapi(spec, app.routes, HIERARCHY))

        assert annotate_openapi(spec, app.routes, HIERARCHY) == once

    def test_the_route_declaration_is_never_mutated(self):
        app = _app()
        spec = get_openapi(title="t", version="1", routes=app.routes)
        annotate_openapi(spec, app.routes, HIERARCHY)
        spec["paths"]["/api/v1/sources/{source}/test"]["post"][EXTENSION]["cli"]["aliases"].append("x")
        spec["paths"]["/api/v1/sources/{source}"]["delete"][EXTENSION]["mcp"]["tool"] = "x"

        again = annotate_openapi(get_openapi(title="t", version="1", routes=app.routes), app.routes, HIERARCHY)

        assert again["paths"]["/api/v1/sources/{source}/test"]["post"][EXTENSION]["cli"]["aliases"] == ["try"]
        assert again["paths"]["/api/v1/sources/{source}"]["delete"][EXTENSION]["mcp"]["tool"] == "svc_sources_delete"


class TestInstall:
    """``install`` wires an app once, and refuses one it cannot name."""

    def test_an_app_named_some_other_way_is_refused(self):
        with pytest.raises(ValueError, match="generate_unique_id_function"):
            install(FastAPI(), HIERARCHY)

    def test_a_custom_openapi_assigned_first_is_wrapped(self):
        app = _app()

        def custom() -> dict:
            spec = get_openapi(title="custom", version="9", routes=app.routes)
            spec["info"]["x-custom"] = True
            return spec

        app.openapi = custom  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]
        install(app, HIERARCHY)
        spec = app.openapi()

        assert spec["info"]["x-custom"] is True
        assert EXTENSION in spec["paths"]["/api/v1/sources"]["get"]
        assert app.openapi() is spec

    def test_without_problem_handlers_the_spec_keeps_fastapi_errors(self):
        app = _app()
        install(app, HIERARCHY, problem_handlers=False)

        assert "Problem" not in app.openapi()["components"]["schemas"]


class TestDeclarations:
    """The helpers routes declare through."""

    def test_scalo_extra_holds_only_what_was_declared(self):
        assert scalo_extra() == {EXTENSION: {}}
        assert scalo_extra(verb="preview", read_only=False) == {EXTENSION: {"verb": "preview", "read_only": False}}

    def test_public_and_an_action_contradict(self):
        with pytest.raises(ValueError, match="public"):
            scalo_extra(public=True, action="x:y")

    def test_permission_tags_and_returns_the_dependency(self):
        def check() -> None:
            return None

        assert permission("a:b")(check) is check
        assert getattr(check, ACTION_ATTRIBUTE) == "a:b"

    def test_permission_needs_an_action(self):
        with pytest.raises(ValueError):
            permission("")

    def test_mcp_hints_leave_derived_defaults_out(self):
        assert McpHints().as_dict() == {"task": False}
        assert McpHints(tool="t", read_only=True, task=True).as_dict() == {"task": True, "tool": "t", "read_only": True}
