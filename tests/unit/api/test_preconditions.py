#  Project:   scalo
#  File:      tests/unit/api/test_preconditions.py
#  Purpose:   ETag, If-Match and If-None-Match: 412 on a lost write, 428 on an unguarded one
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Optimistic concurrency for apply: the RFC 9110 conditions, then the same flow over HTTP."""

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel

from scalo.api import (
    DryRun,
    EntityTag,
    PreconditionHeaders,
    ProblemError,
    check_preconditions,
    etag_of,
    format_etag,
    install_problem_handlers,
    parse_etags,
)

CURRENT = '"abc"'


def _refused(current, **headers) -> ProblemError:
    with pytest.raises(ProblemError) as caught:
        check_preconditions(current, if_match=headers.get("if_match"), if_none_match=headers.get("if_none_match"))
    return caught.value


class TestEtags:
    def test_etag_of_is_stable_across_key_order(self):
        assert etag_of({"a": 1, "b": [1, 2]}) == etag_of({"b": [1, 2], "a": 1})
        assert etag_of({"a": 1}) != etag_of({"a": 2})

    def test_etag_of_text_and_bytes_hash_the_same_bytes(self):
        text = "h" + chr(0xE9) + "llo"
        assert etag_of(text) == etag_of(text.encode("utf-8"))
        assert etag_of(b"x").startswith('"')
        assert etag_of(b"x").endswith('"')

    def test_etag_of_a_model(self):
        class Doc(BaseModel):
            name: str

        assert etag_of(Doc(name="a")) == etag_of({"name": "a"})

    def test_format_etag_quotes_a_bare_value_and_keeps_a_tag(self):
        assert format_etag("3f2a") == '"3f2a"'
        assert format_etag("3f2a", weak=True) == 'W/"3f2a"'
        assert format_etag('W/"x"') == 'W/"x"'

    @pytest.mark.parametrize("value", ['a"b', "a b", "a\x01"])
    def test_format_etag_refuses_what_a_header_cannot_carry(self, value):
        with pytest.raises(ValueError):
            format_etag(value)

    def test_parse_etags(self):
        assert parse_etags(" * ") == "*"
        assert parse_etags('"a", W/"b" ,"c,d"') == (EntityTag("a"), EntityTag("b", weak=True), EntityTag("c,d"))
        assert str(EntityTag("b", weak=True)) == 'W/"b"'

    @pytest.mark.parametrize("header", ["", "abc", '"a" "b"', '"a",, "b"'])
    def test_parse_etags_refuses_a_malformed_list(self, header):
        with pytest.raises(ProblemError) as caught:
            parse_etags(header)

        assert caught.value.status == 400
        assert caught.value.problem.code == "invalid_precondition"


class TestConditions:
    """RFC 9110 section 13: If-Match strong, If-None-Match weak, and nothing sent is refused."""

    def test_if_none_match_any_creates(self):
        check_preconditions(None, if_match=None, if_none_match="*")

    def test_if_none_match_any_refuses_an_existing_resource(self):
        refused = _refused(CURRENT, if_none_match="*")

        assert (refused.status, refused.problem.code) == (412, "resource_exists")
        assert refused.problem.model_extra == {"etag": CURRENT}

    def test_if_match_updates_when_it_matches(self):
        check_preconditions(CURRENT, if_match='"zzz", "abc"', if_none_match=None)
        check_preconditions("abc", if_match=CURRENT, if_none_match=None)
        check_preconditions(CURRENT, if_match="*", if_none_match=None)

    def test_if_match_refuses_a_lost_write(self):
        refused = _refused(CURRENT, if_match='"old"')

        assert (refused.status, refused.problem.code) == (412, "etag_mismatch")
        assert refused.problem.model_extra == {"etag": CURRENT}

    def test_a_weak_tag_never_satisfies_if_match(self):
        assert _refused(CURRENT, if_match='W/"abc"').problem.code == "etag_mismatch"
        assert _refused('W/"abc"', if_match='"abc"').problem.code == "etag_mismatch"

    def test_if_match_on_a_missing_resource(self):
        assert _refused(None, if_match="*").problem.code == "resource_missing"

    def test_if_none_match_list_compares_weakly(self):
        assert _refused(CURRENT, if_none_match='W/"abc"').problem.code == "resource_exists"
        check_preconditions(CURRENT, if_match=None, if_none_match='"other"')

    @pytest.mark.parametrize(("current", "hint"), [(None, "If-None-Match: *"), (CURRENT, "If-Match")])
    def test_sending_neither_header_is_refused(self, current, hint):
        refused = _refused(current)

        assert (refused.status, refused.problem.code) == (428, "precondition_required")
        assert hint in (refused.problem.detail or "")

    def test_require_false_lets_an_unguarded_write_through(self):
        check_preconditions(CURRENT, if_match=None, if_none_match=None, require=False)

    def test_a_current_etag_that_is_a_list_is_a_programming_error(self):
        with pytest.raises(ValueError):
            check_preconditions('"a", "b"', if_match="*", if_none_match=None)


class Doc(BaseModel):
    name: str
    size: int = 0


@pytest.fixture
def client() -> TestClient:
    """An apply route over an in-memory store: create, update, lost write, dry run."""
    store: dict[str, Doc] = {}
    app = FastAPI()
    install_problem_handlers(app)

    @app.put("/docs/{doc}")
    def apply_doc(doc: str, body: Doc, pre: PreconditionHeaders, dry_run: DryRun, response: Response) -> Doc:
        current = store.get(doc)
        pre.check(None if current is None else etag_of(current))
        response.headers["ETag"] = etag_of(body)
        if not dry_run:
            store[doc] = body
        return body

    return TestClient(app)


class TestApplyOverHttp:
    def test_create_then_update_then_lose_a_write(self, client):
        created = client.put("/docs/a", json={"name": "a"}, headers={"If-None-Match": "*"})
        assert created.status_code == 200
        first = created.headers["etag"]

        updated = client.put("/docs/a", json={"name": "a", "size": 1}, headers={"If-Match": first})
        assert updated.status_code == 200

        lost = client.put("/docs/a", json={"name": "a", "size": 2}, headers={"If-Match": first})
        assert lost.status_code == 412
        assert lost.json()["etag"] == updated.headers["etag"]

    def test_create_twice_is_refused(self, client):
        client.put("/docs/a", json={"name": "a"}, headers={"If-None-Match": "*"})

        assert client.put("/docs/a", json={"name": "a"}, headers={"If-None-Match": "*"}).status_code == 412

    def test_an_unguarded_write_is_refused(self, client):
        assert client.put("/docs/a", json={"name": "a"}).status_code == 428

    def test_a_dry_run_commits_nothing_but_reports_the_etag(self, client):
        preview = client.put("/docs/a?dry_run=true", json={"name": "a"}, headers={"If-None-Match": "*"})
        assert preview.status_code == 200

        committed = client.put("/docs/a", json={"name": "a"}, headers={"If-None-Match": "*"})
        assert committed.status_code == 200
        assert committed.headers["etag"] == preview.headers["etag"]
