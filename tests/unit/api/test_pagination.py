#  Project:   scalo
#  File:      tests/unit/api/test_pagination.py
#  Purpose:   AIP-158 pagination: defaults, the server cap, bound page tokens, and the shared query parameters
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Lists page the same way everywhere, and the shared ``dry_run`` and ``view`` parameters read the same way."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from scalo.api import (
    DryRun,
    GetView,
    ListParams,
    ListQuery,
    ListView,
    Page,
    ProblemError,
    View,
    decode_page_token,
    encode_page_token,
    install_problem_handlers,
    list_query,
    paginate,
)

ITEMS = list(range(7))


class TestListQuery:
    def test_zero_or_none_gets_the_default_and_more_than_the_cap_is_cut(self):
        dependency = list_query(default_page_size=3, max_page_size=5)

        assert dependency().page_size == 3
        assert dependency(page_size=0).page_size == 3
        assert dependency(page_size=4).page_size == 4
        assert dependency(page_size=500).page_size == 5

    @pytest.mark.parametrize(("default", "cap"), [(0, 5), (6, 5)])
    def test_a_default_outside_the_cap_fails_at_startup(self, default, cap):
        with pytest.raises(ValueError):
            list_query(default_page_size=default, max_page_size=cap)


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

    def test_an_exact_final_page_has_no_token(self):
        assert paginate(ITEMS, ListQuery(page_size=7)).next_page_token is None

    def test_total_size_can_be_left_out(self):
        assert paginate(ITEMS, ListQuery(page_size=2), with_total=False).total_size is None

    def test_a_token_past_the_end_gives_an_empty_page(self):
        query = ListQuery(page_size=2)
        far = ListQuery(page_size=2, page_token=encode_page_token(99, query))

        assert paginate(ITEMS, far).items == []

    def test_a_token_is_bound_to_the_filter_and_ordering(self):
        token = encode_page_token(2, ListQuery(page_size=2, filter="a", order_by="name"))

        assert decode_page_token(ListQuery(page_size=9, page_token=token, filter="a", order_by="name")) == 2
        with pytest.raises(ProblemError, match="different filter"):
            decode_page_token(ListQuery(page_size=2, page_token=token, filter="b", order_by="name"))

    @pytest.mark.parametrize("token", ["not-base64!", "e30", "eyJvIjotMX0", "eyJvIjp0cnVlfQ", "W10"])
    def test_a_token_this_api_did_not_issue_is_refused(self, token):
        with pytest.raises(ProblemError) as caught:
            decode_page_token(ListQuery(page_size=2, page_token=token))

        assert (caught.value.status, caught.value.problem.code) == (400, "invalid_page_token")


class Item(BaseModel):
    name: str


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    install_problem_handlers(app)
    items = [Item(name=f"i{n}") for n in range(5)]

    @app.get("/items", response_model=Page[Item])
    def list_items(query: ListParams, view: ListView) -> Page[Item]:
        return paginate(items, query)

    @app.get("/items/{name}")
    def get_item(name: str, view: GetView) -> dict:
        return {"view": view}

    @app.post("/items/{name}/rename")
    def rename(name: str, dry_run: DryRun) -> dict:
        return {"dry_run": dry_run}

    return TestClient(app)


class TestOverHttp:
    def test_a_list_pages_through_its_query_parameters(self, client):
        first = client.get("/items?page_size=2").json()
        second = client.get(f"/items?page_size=2&page_token={first['next_page_token']}").json()

        assert [item["name"] for item in first["items"]] == ["i0", "i1"]
        assert [item["name"] for item in second["items"]] == ["i2", "i3"]
        assert first["total_size"] == 5

    def test_a_negative_page_size_is_refused(self, client):
        assert client.get("/items?page_size=-1").status_code == 422

    def test_a_changed_filter_between_pages_is_refused(self, client):
        token = client.get("/items?page_size=2&filter=a").json()["next_page_token"]

        assert client.get(f"/items?page_size=2&filter=b&page_token={token}").status_code == 400

    def test_views_default_basic_for_a_list_and_full_for_a_get(self, client):
        assert client.get("/items/a").json() == {"view": View.FULL}
        assert client.get("/items/a?view=basic").json() == {"view": View.BASIC}
        assert client.get("/items/a?view=everything").status_code == 422

    def test_dry_run_defaults_off(self, client):
        assert client.post("/items/a/rename").json() == {"dry_run": False}
        assert client.post("/items/a/rename?dry_run=true").json() == {"dry_run": True}

    def test_the_spec_carries_the_shared_parameter_names(self, client):
        spec = client.app.openapi()
        names = {param["name"] for param in spec["paths"]["/items"]["get"]["parameters"]}

        assert names == {"page_size", "page_token", "filter", "order_by", "view"}
        assert [p["name"] for p in spec["paths"]["/items/{name}/rename"]["post"]["parameters"]] == ["name", "dry_run"]
