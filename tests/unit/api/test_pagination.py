#  Project:   scalo
#  File:      tests/unit/api/test_pagination.py
#  Purpose:   AIP-158 pagination: defaults, the server cap, sealed bound page tokens, skip, order_by and the shared query parameters
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Lists page the same way everywhere, and the shared ``dry_run`` and ``view`` parameters read the same way."""

import json
import time
from dataclasses import replace
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from scalo.api import (
    PAGE_TOKEN_KEY_SETTING,
    PAGE_TOKEN_TTL_SECONDS,
    DryRun,
    GetView,
    ListParams,
    ListQuery,
    ListView,
    Page,
    ProblemError,
    SortKey,
    View,
    decode_page_token,
    encode_page_token,
    install_problem_handlers,
    list_query,
    paginate,
    pagination,
    sort_by_order,
)
from scalo.config import settings

ITEMS = list(range(7))


@pytest.fixture
def page_key():
    """Set ``api.page_token_key`` for one test, and drop the cached sealer either side."""

    def use(key: str | None) -> None:
        settings.set(PAGE_TOKEN_KEY_SETTING, key)
        pagination._sealer = None

    yield use
    use(None)


@pytest.mark.parametrize(("options", "message"), [
    pytest.param({"default_page_size": 0, "max_page_size": 5}, "default_page_size", id="default_below_one"),
    pytest.param({"default_page_size": 6, "max_page_size": 5}, "default_page_size", id="default_above_cap"),
    pytest.param({"order_by": ("name",)}, "tiebreak", id="order_by_without_tiebreak"),
])  # fmt: skip
def test_a_list_declared_wrong_fails_at_startup(options, message):
    with pytest.raises(ValueError, match=message):
        list_query(**options)


class TestPaginate:
    def test_pages_cover_every_item_once_and_the_last_has_no_token(self):
        query = ListQuery(page_size=3)
        seen: list[int] = []
        pages = 0
        while True:
            page = paginate(ITEMS, query)
            pages += 1
            seen.extend(page.items)
            assert page.total_size == len(ITEMS)
            if page.next_page_token is None:
                break
            query = ListQuery(page_size=3, page_token=page.next_page_token)

        assert seen == ITEMS
        assert pages == 3

    @pytest.mark.parametrize(("query", "items", "token"), [
        pytest.param(ListQuery(page_size=7), ITEMS, None, id="exact_final_page"),
        pytest.param(ListQuery(page_size=2, skip=3), [3, 4], "next", id="skip_from_the_start"),
        pytest.param(ListQuery(page_size=9, skip=9), [], None, id="skip_past_the_end"),
    ])  # fmt: skip
    def test_one_page(self, query, items, token):
        page = paginate(ITEMS, query)

        assert page.items == items
        assert (page.next_page_token is not None) == (token == "next")

    def test_skip_counts_from_the_token(self):
        token = paginate(ITEMS, ListQuery(page_size=2)).next_page_token

        assert paginate(ITEMS, ListQuery(page_size=2, page_token=token, skip=1)).items == [3, 4]

    def test_total_size_can_be_left_out(self):
        assert paginate(ITEMS, ListQuery(page_size=2), with_total=False).total_size is None

    def test_a_token_is_opaque(self):
        token = encode_page_token(2, ListQuery(page_size=2, filter="kind = syslog"))

        assert "syslog" not in token
        with pytest.raises(ValueError):
            json.loads(token)

    @pytest.mark.parametrize(("change", "bound"), [
        pytest.param({"filter": "b"}, {"search": "a"}, id="filter_changed"),
        pytest.param({"order_by": (SortKey("name", True),)}, {"search": "a"}, id="order_by_changed"),
        pytest.param({"path": "/other"}, {"search": "a"}, id="path_changed"),
        pytest.param({}, {"search": "b"}, id="bound_changed"),
        pytest.param({}, None, id="bound_dropped"),
    ])  # fmt: skip
    def test_a_token_is_bound_to_everything_that_shapes_the_list(self, change, bound):
        issued = ListQuery(page_size=2, filter="a", order_by=(SortKey("name"),), path="/items")
        token = encode_page_token(2, issued, bound={"search": "a"})

        assert decode_page_token(replace(issued, page_size=9, page_token=token), bound={"search": "a"}) == 2
        with pytest.raises(ProblemError) as caught:
            decode_page_token(replace(issued, page_token=token, **change), bound=bound)
        assert (caught.value.status, caught.value.problem.code) == (400, "invalid_page_token")

    @pytest.mark.parametrize("token", ["not-a-token!", "e30", "eyJvIjoyfQ", "gAAAAA" + "A" * 80, "é"])
    def test_a_token_this_api_did_not_issue_is_refused(self, token):
        with pytest.raises(ProblemError) as caught:
            decode_page_token(ListQuery(page_size=2, page_token=token))

        assert (caught.value.status, caught.value.problem.code) == (400, "invalid_page_token")

    def test_a_tampered_token_is_refused(self):
        token = encode_page_token(2, ListQuery(page_size=2))
        flipped = token[:-6] + ("A" if token[-6] != "A" else "B") + token[-5:]

        with pytest.raises(ProblemError, match="page_token"):
            decode_page_token(ListQuery(page_size=2, page_token=flipped))

    def test_an_expired_token_is_refused(self):
        payload = json.dumps({"o": 2, "f": pagination._fingerprint(ListQuery(page_size=2), None)}).encode()
        old = pagination._page_sealer().encrypt_at_time(payload, int(time.time()) - PAGE_TOKEN_TTL_SECONDS - 60)

        with pytest.raises(ProblemError, match="expired"):
            decode_page_token(ListQuery(page_size=2, page_token=old.decode()))

    def test_the_configured_key_seals_tokens_across_processes(self, page_key):
        page_key("k" * 32)
        token = encode_page_token(2, ListQuery(page_size=2))
        pagination._sealer = None

        assert decode_page_token(ListQuery(page_size=2, page_token=token)) == 2
        page_key("j" * 32)
        with pytest.raises(ProblemError):
            decode_page_token(ListQuery(page_size=2, page_token=token))

    def test_a_short_key_is_refused(self, page_key):
        page_key("short")

        with pytest.raises(ValueError, match="32 characters"):
            encode_page_token(2, ListQuery(page_size=2))


class Item(BaseModel):
    name: str
    size: int | None = None


SortedList = Annotated[
    ListQuery,
    Depends(list_query(default_page_size=3, max_page_size=5, order_by=("name", "size"), tiebreak="name", filter=True)),
]


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    install_problem_handlers(app)
    items = [Item(name=f"i{n}", size=n % 3 or None) for n in range(10)]

    @app.get("/items")
    def list_items(query: ListParams, view: ListView) -> Page[Item]:
        return paginate(items, query)

    @app.get("/sorted")
    def list_sorted(query: SortedList) -> Page[Item]:
        rows = [item for item in reversed(items) if not query.filter or item.name.startswith(query.filter)]
        return paginate(sort_by_order(rows, query.order_by), query)

    @app.get("/items/{name}")
    def get_item(name: str, view: GetView) -> dict:
        return {"view": view}

    @app.post("/items/{name}/rename")
    def rename(name: str, dry_run: DryRun) -> dict:
        return {"dry_run": dry_run}

    return TestClient(app)


class TestOverHttp:
    def test_a_list_pages_through_its_query_parameters(self, client):
        first = client.get("/items?page_size=4").json()
        second = client.get(f"/items?page_size=4&page_token={first['next_page_token']}").json()
        last = client.get(f"/items?page_size=4&page_token={second['next_page_token']}").json()

        assert [item["name"] for item in first["items"] + second["items"]] == [f"i{n}" for n in range(8)]
        assert (first["total_size"], last["next_page_token"]) == (10, None)

    @pytest.mark.parametrize(("page_size", "count"), [(None, 3), (0, 3), (4, 4), (500, 5)])
    def test_the_default_and_the_cap(self, client, page_size, count):
        query = "" if page_size is None else f"?page_size={page_size}"

        assert len(client.get(f"/sorted{query}").json()["items"]) == count

    @pytest.mark.parametrize(("order_by", "names"), [
        pytest.param("", ["i0", "i1", "i2"], id="none_sent_sorts_by_the_tiebreak"),
        pytest.param("name desc", ["i9", "i8", "i7"], id="desc"),
        pytest.param("size, name", ["i1", "i4", "i7"], id="tiebreak_appended"),
        pytest.param("size DESC", ["i0", "i3", "i6"], id="direction_any_case_missing_first"),
    ])  # fmt: skip
    def test_order_by_sorts(self, client, order_by, names):
        assert [item["name"] for item in client.get(f"/sorted?order_by={order_by}").json()["items"]] == names

    @pytest.mark.parametrize(("url", "status", "code"), [
        pytest.param("/sorted?order_by=colour", 400, "invalid_order_by", id="field_not_allowed"),
        pytest.param("/sorted?order_by=name sideways", 400, "invalid_order_by", id="bad_direction"),
        pytest.param("/sorted?order_by=name, name desc", 400, "invalid_order_by", id="field_twice"),
        pytest.param("/sorted?order_by=name,,size", 400, "invalid_order_by", id="empty_item"),
        pytest.param("/items?filter=a", 400, "unsupported_parameter", id="filter_not_taken"),
        pytest.param("/items?order_by=name", 400, "unsupported_parameter", id="order_by_not_taken"),
        pytest.param("/items?skip=-1", 422, "validation_error", id="negative_skip"),
        pytest.param("/items?page_size=-1", 422, "validation_error", id="negative_page_size"),
    ])  # fmt: skip
    def test_a_bad_list_request_is_a_problem(self, client, url, status, code):
        response = client.get(url)

        assert (response.status_code, response.json()["code"]) == (status, code)
        assert response.headers["content-type"] == "application/problem+json"

    @pytest.mark.parametrize("changed", ["filter=i2", "order_by=name desc", "page_size=2&filter=i&order_by=size"])
    def test_a_token_reused_with_other_parameters_is_refused(self, client, changed):
        token = client.get("/sorted?page_size=2&filter=i&order_by=name").json()["next_page_token"]
        response = client.get(f"/sorted?page_token={token}&{changed}")

        assert (response.status_code, response.json()["code"]) == (400, "invalid_page_token")

    def test_a_token_from_another_list_is_refused(self, client):
        token = client.get("/items?page_size=2").json()["next_page_token"]

        assert client.get(f"/sorted?page_size=2&page_token={token}").status_code == 400

    def test_views_default_basic_for_a_list_and_full_for_a_get(self, client):
        assert client.get("/items/a").json() == {"view": View.FULL}
        assert client.get("/items/a?view=basic").json() == {"view": View.BASIC}
        assert client.get("/items/a?view=everything").status_code == 422

    def test_dry_run_defaults_off(self, client):
        assert client.post("/items/a/rename").json() == {"dry_run": False}
        assert client.post("/items/a/rename?dry_run=true").json() == {"dry_run": True}

    @pytest.mark.parametrize(("path", "names"), [
        ("/items", {"page_size", "page_token", "skip", "view"}),
        ("/sorted", {"page_size", "page_token", "skip", "filter", "order_by"}),
    ])  # fmt: skip
    def test_the_spec_declares_only_the_parameters_a_list_takes(self, client, path, names):
        spec = client.app.openapi()

        assert {param["name"] for param in spec["paths"][path]["get"]["parameters"]} == names


@pytest.mark.parametrize(("order_by", "want"), [
    pytest.param((SortKey("size"), SortKey("name")), ["b", "c", "a"], id="missing_last"),
    pytest.param((SortKey("size", True), SortKey("name")), ["a", "c", "b"], id="desc_missing_first"),
    pytest.param((SortKey("meta.rank"),), ["c", "a", "b"], id="dotted_subfield"),
])  # fmt: skip
def test_sort_by_order(order_by, want):
    rows = [
        {"name": "a", "size": None, "meta": {"rank": 2}},
        {"name": "b", "size": 1, "meta": {"rank": 3}},
        {"name": "c", "size": 2, "meta": {"rank": 1}},
    ]

    assert [row["name"] for row in sort_by_order(rows, order_by)] == want
