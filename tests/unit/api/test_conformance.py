#  Project:   scalo
#  File:      tests/unit/api/test_conformance.py
#  Purpose:   The conformance check passes a conformant app and names every rule a sprawling one breaks
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``check_conformance`` over real FastAPI apps: one that follows every convention, and one that breaks each rule."""

import copy
import threading
import warnings

import pytest
from fastapi import APIRouter, Depends, FastAPI, Response
from pydantic import BaseModel

from scalo.api import (
    EXTENSION,
    DryRun,
    Hierarchy,
    ListParams,
    Page,
    PreconditionHeaders,
    assert_conformant,
    check_conformance,
    install,
    paginate,
    permission,
    scalo_extra,
)

HIERARCHY = Hierarchy(base_path="/api/v1", singletons={"deployment"})


@permission("source:read")
def can_read() -> None:
    return None


@permission("source:write")
def can_write() -> None:
    return None


class Source(BaseModel):
    name: str


def conformant_app() -> FastAPI:
    """Every route follows every convention."""
    router = APIRouter(prefix="/sources")

    @router.get("", dependencies=[Depends(can_read)])
    def list_sources(query: ListParams) -> Page[Source]:
        """List sources."""
        return paginate([], query)

    @router.get("/{source}", dependencies=[Depends(can_read)])
    def get_source(source: str) -> Source:
        """Get a source."""
        return Source(name=source)

    @router.put("/{source}", dependencies=[Depends(can_write)])
    def apply_source(source: str, body: Source, pre: PreconditionHeaders, dry_run: DryRun) -> Source:
        """Create or replace a source."""
        return body

    @router.delete("/{source}", status_code=204, dependencies=[Depends(can_write)])
    def delete_source(source: str, pre: PreconditionHeaders, dry_run: DryRun) -> Response:
        """Delete a source."""
        return Response(status_code=204)

    @router.post("/{source}/deploy", dependencies=[Depends(can_write)])
    def deploy_source(source: str, dry_run: DryRun) -> Source:
        """Deploy a source."""
        return Source(name=source)

    @router.get("/{source}/preview", openapi_extra=scalo_extra(verb="preview"), dependencies=[Depends(can_read)])
    def preview_source(source: str) -> Source:
        """Preview a source."""
        return Source(name=source)

    status = APIRouter(prefix="/deployment")

    @status.get("", openapi_extra=scalo_extra(public=True))
    def get_deployment() -> Source:
        """Get the deployment."""
        return Source(name="d")

    protocol = APIRouter(prefix="/scim/v2")

    @protocol.get("/Users")
    def scim_users() -> dict:
        return {}

    app = FastAPI(generate_unique_id_function=HIERARCHY.unique_id)
    app.include_router(router, prefix="/api/v1")
    app.include_router(status, prefix="/api/v1")
    app.include_router(protocol)
    install(app, HIERARCHY)
    return app


EXEMPT = ["/scim/*"]


def sprawling_app() -> FastAPI:
    """Each route breaks the rule its name says."""
    router = APIRouter(prefix="/api/v1")

    @router.get("/widget", dependencies=[Depends(can_read)])
    def hierarchy() -> list[str]:
        """Not plural, and no pagination."""
        return []

    @router.get("/a-items/{a}/b-items/{b}/c-items/{c}/d-items/{d}", dependencies=[Depends(can_read)])
    def depth(a: str, b: str, c: str, d: str) -> Source:
        """Four levels deep."""
        return Source(name=a)

    @router.get("/things/{thing}", dependencies=[Depends(can_read)])
    def response_model(thing: str):
        """No response model."""
        return {}

    @router.get("/nodes/{node}", dependencies=[Depends(can_read)])
    def summary(node: str) -> Source:
        return Source(name=node)

    @router.get("/files/{file}")
    def unguarded(file: str) -> Source:
        """No permission."""
        return Source(name=file)

    @router.put("/boxes/{box}", dependencies=[Depends(can_write)])
    def unconditional(box: str, body: Source) -> Source:
        """No dry_run, no If-Match."""
        return body

    @router.get("/labels/{label}", operation_id="labels_get_by_hand", dependencies=[Depends(can_read)])
    def by_hand(label: str) -> Source:
        """A hand-set operation id."""
        return Source(name=label)

    app = FastAPI(generate_unique_id_function=HIERARCHY.unique_id)
    app.include_router(router)
    install(app, HIERARCHY)
    return app


def _rules(report) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for violation in report.violations:
        found.setdefault(violation.path, set()).add(violation.rule)
    return found


class TestConformantApp:
    def test_passes(self):
        report = assert_conformant(conformant_app(), HIERARCHY, exempt=EXEMPT)

        assert report.ok
        assert report.checked == 7
        assert report.exempt == 1

    def test_the_protocol_route_fails_once_it_is_no_longer_exempt(self):
        report = check_conformance(conformant_app(), HIERARCHY)

        assert {violation.path for violation in report.violations} == {"/scim/v2/Users"}
        assert {violation.rule for violation in report.violations} == {"hierarchy", "permission", "summary"}


@pytest.fixture(scope="module")
def rules() -> dict[str, set[str]]:
    """The rules each sprawling route breaks."""
    return _rules(check_conformance(sprawling_app(), HIERARCHY))


class TestEachRuleFires:
    @pytest.mark.parametrize(
        ("path", "rule"),
        [
            ("/api/v1/widget", "hierarchy"),
            ("/api/v1/widget", "pagination"),
            ("/api/v1/a-items/{a}/b-items/{b}/c-items/{c}/d-items/{d}", "depth"),
            ("/api/v1/things/{thing}", "response-model"),
            ("/api/v1/nodes/{node}", "summary"),
            ("/api/v1/files/{file}", "permission"),
            ("/api/v1/boxes/{box}", "dry-run"),
            ("/api/v1/boxes/{box}", "if-match"),
            ("/api/v1/labels/{label}", "operation-id"),
        ],
    )
    def test_rule(self, rules, path, rule):
        assert rule in rules.get(path, set()), rules

    def test_a_conformant_route_in_the_same_app_raises_nothing_else(self, rules):
        assert rules["/api/v1/nodes/{node}"] == {"summary"}
        assert rules["/api/v1/files/{file}"] == {"permission"}

    def test_a_duplicate_operation_id(self):
        app = FastAPI(generate_unique_id_function=HIERARCHY.unique_id)

        @app.get("/api/v1/sources/{source}", dependencies=[Depends(can_read)])
        def first(source: str) -> Source:
            """One."""
            return Source(name=source)

        @app.get("/api/v1/sources/{name}", dependencies=[Depends(can_read)])
        def second(name: str) -> Source:
            """Two."""
            return Source(name=name)

        install(app, HIERARCHY)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            report = check_conformance(app, HIERARCHY)

        assert {violation.rule for violation in report.violations} == {"duplicate-operation-id"}

    def test_a_spec_without_the_extension(self):
        app = conformant_app()
        spec = copy.deepcopy(app.openapi())
        del spec["paths"]["/api/v1/sources"]["get"][EXTENSION]
        spec["paths"]["/api/v1/sources/{source}"]["get"][EXTENSION]["verb"] = "fetch"

        report = check_conformance(app, HIERARCHY, exempt=EXEMPT, spec=spec)

        assert {(v.path, v.rule) for v in report.violations} == {
            ("/api/v1/sources", "extension"),
            ("/api/v1/sources/{source}", "extension"),
        }
        assert any("['verb']" in v.message for v in report.violations)

    def test_an_app_without_unique_ids_fails_operation_id(self):
        app = FastAPI()

        @app.get("/api/v1/sources/{source}", dependencies=[Depends(can_read)])
        def get_source(source: str) -> Source:
            """Get."""
            return Source(name=source)

        report = check_conformance(app, HIERARCHY)

        assert {v.rule for v in report.violations} == {"operation-id", "extension"}


class TestSchemaReferences:
    """A response schema is found by its JSON pointer, not by the last segment of it."""

    @pytest.mark.parametrize("name", ["Page/Source", "Page~Source"])
    def test_a_page_under_a_name_the_pointer_escapes(self, name):
        app = conformant_app()
        spec = copy.deepcopy(app.openapi())
        content = spec["paths"]["/api/v1/sources"]["get"]["responses"]["200"]["content"]["application/json"]
        schemas = spec["components"]["schemas"]
        schemas[name] = schemas.pop(content["schema"]["$ref"].rsplit("/", 1)[-1])
        content["schema"] = {"$ref": "#/components/schemas/" + name.replace("~", "~0").replace("/", "~1")}

        report = check_conformance(app, HIERARCHY, exempt=EXEMPT, spec=spec)

        assert report.ok, report.format()


def _list_spec() -> tuple[FastAPI, dict, dict]:
    """The conformant app, a copy of its spec to rearrange, and the list route's path item in that copy."""
    app = conformant_app()
    spec = copy.deepcopy(app.openapi())
    return app, spec, spec["paths"]["/api/v1/sources"]


def _pagination(app: FastAPI, spec: dict) -> list[str]:
    report = check_conformance(app, HIERARCHY, exempt=EXEMPT, spec=spec)
    return [violation.message for violation in report.violations if violation.rule == "pagination"]


class TestParametersWhereTheSpecPutsThem:
    """A parameter counts on the path item and through a ``$ref``, as OpenAPI allows."""

    def test_page_token_on_the_path_item(self):
        app, spec, item = _list_spec()
        parameters = item["get"]["parameters"]
        page_token = next(parameter for parameter in parameters if parameter["name"] == "page_token")
        parameters.remove(page_token)
        item["parameters"] = [page_token]

        assert _pagination(app, spec) == []

    def test_page_size_by_reference(self):
        app, spec, item = _list_spec()
        parameters = item["get"]["parameters"]
        index = next(i for i, parameter in enumerate(parameters) if parameter["name"] == "page_size")
        spec["components"].setdefault("parameters", {})["PageSize"] = parameters[index]
        parameters[index] = {"$ref": "#/components/parameters/PageSize"}

        assert _pagination(app, spec) == []

    def test_a_list_without_page_token_anywhere_still_fails(self):
        app, spec, item = _list_spec()
        item["get"]["parameters"] = [p for p in item["get"]["parameters"] if p["name"] != "page_token"]

        assert _pagination(app, spec) == ["a list without the page_token query parameter: use ListParams"]


class TestSuccessResponsesWhereTheSpecPutsThem:
    """The Page is read from any JSON media type and through a referenced response."""

    def test_a_json_suffixed_media_type(self):
        app, spec, item = _list_spec()
        content = item["get"]["responses"]["200"]["content"]
        content["application/vnd.svc.page+json"] = content.pop("application/json")

        assert _pagination(app, spec) == []

    def test_a_referenced_response(self):
        app, spec, item = _list_spec()
        responses = item["get"]["responses"]
        spec["components"].setdefault("responses", {})["SourcePage"] = responses["200"]
        responses["200"] = {"$ref": "#/components/responses/SourcePage"}

        assert _pagination(app, spec) == []

    def test_a_success_body_that_is_not_json_still_fails(self):
        app, spec, item = _list_spec()
        content = item["get"]["responses"]["200"]["content"]
        content["text/csv"] = content.pop("application/json")

        assert _pagination(app, spec) == ["a list whose response carries no next_page_token: answer a Page"]

    def test_status_keys_a_yaml_spec_reads_as_integers(self):
        app, spec, item = _list_spec()
        responses = item["get"]["responses"]
        responses[200] = responses.pop("200")

        assert _pagination(app, spec) == []

    def test_a_page_whose_all_of_names_itself_is_checked_in_time(self):
        app, spec, item = _list_spec()
        content = item["get"]["responses"]["200"]["content"]["application/json"]
        loop = "#/components/schemas/Loop"
        spec["components"]["schemas"]["Loop"] = {"allOf": [{"$ref": loop}, {"$ref": loop}, content["schema"]]}
        content["schema"] = {"$ref": loop}
        found: list[list[str]] = []
        finished = threading.Event()

        def check() -> None:
            found.append(_pagination(app, spec))
            finished.set()

        threading.Thread(target=check, daemon=True).start()

        assert finished.wait(5), "a self-referencing allOf did not finish checking in 5 s"
        assert found == [[]]


class TestAllowList:
    """Adopting the conventions router by router."""

    def test_todays_violations_become_the_allow_list(self):
        report = check_conformance(sprawling_app(), HIERARCHY)

        again = check_conformance(sprawling_app(), HIERARCHY, allow=report.allow_list())

        assert again.ok
        assert len(again.allowed) == len(report.violations)

    def test_a_pattern_allows_a_whole_router(self):
        report = check_conformance(sprawling_app(), HIERARCHY, allow=["* * /api/v1/*"])

        assert report.ok

    def test_an_entry_that_matches_nothing_fails(self):
        report = check_conformance(conformant_app(), HIERARCHY, exempt=EXEMPT, allow=["summary GET /api/v1/gone"])

        assert not report.ok
        assert report.unused_allowances == ("summary GET /api/v1/gone",)
        with pytest.raises(AssertionError, match="match nothing"):
            assert_conformant(conformant_app(), HIERARCHY, exempt=EXEMPT, allow=["summary GET /api/v1/gone"])

    def test_strict_false_tolerates_an_unused_entry(self):
        assert_conformant(conformant_app(), HIERARCHY, exempt=EXEMPT, allow=["x"], strict=False)

    def test_the_failure_names_each_violation_and_its_key(self):
        with pytest.raises(AssertionError) as caught:
            assert_conformant(sprawling_app(), HIERARCHY)

        text = str(caught.value)
        assert "if-match PUT /api/v1/boxes/{box}: a write without the If-Match header" in text
        assert text.startswith("API conformance -- violations: ")
