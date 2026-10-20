#  Project:   scalo
#  File:      tests/unit/api/test_conformance.py
#  Purpose:   The conformance check passes a conformant app and names every rule a sprawling one breaks
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""``check_conformance`` over real FastAPI apps: one that follows every convention, and one that breaks each rule."""

import copy
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
