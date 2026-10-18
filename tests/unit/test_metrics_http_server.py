"""HttpServerMetricsMiddleware against real FastAPI and Starlette apps and the Prometheus backend."""

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from scalo.metrics import MetricsManager, create_metrics
from scalo.metrics.http_server import UNMATCHED_ROUTE, UNRESOLVED_ROUTE, HttpServerMetricsMiddleware

SERIES = "http_server_request_duration_seconds_count{"


async def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _instrumented(app: Starlette, app_name: str, root_path: str = "") -> tuple[httpx.AsyncClient, MetricsManager]:
    metrics = create_metrics(app_name, backend="prometheus")
    app.add_middleware(HttpServerMetricsMiddleware, metrics=metrics)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False, root_path=root_path)
    return httpx.AsyncClient(base_url="http://test", transport=transport), metrics


def _accounts_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix)

    @router.get("/accounts/{username}")
    def account(username: str) -> dict:
        return {"username": username}

    @router.get("/items/{item_id:int}")
    def item(item_id: int) -> dict:
        return {"item": item_id}

    return router


def _app(app_name: str) -> tuple[httpx.AsyncClient, MetricsManager]:
    metrics = create_metrics(app_name, backend="prometheus")
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict:
        return {"item": item_id}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("handler failed")

    @app.get("/livez")
    def livez() -> dict:
        return {"status": "ok"}

    app.add_middleware(HttpServerMetricsMiddleware, metrics=metrics)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(base_url="http://test", transport=transport), metrics


def _count(metrics: MetricsManager, *, endpoint: str, method: str, status_code: str) -> float:
    """The histogram's _count sample for one label set, 0.0 when absent."""
    exposition = metrics.get_metrics().decode()
    series = f'http_server_request_duration_seconds_count{{endpoint="{endpoint}",method="{method}",status_code="{status_code}"}}'
    for line in exposition.splitlines():
        if line.startswith(series + " "):
            return float(line.split()[-1])
    return 0.0


async def test_requests_are_counted_under_the_route_template_not_the_path():
    client, metrics = _app(app_name="http-server-template")

    async with client:
        await client.get("/items/1")
        await client.get("/items/2")

    assert _count(metrics=metrics, endpoint="/items/{item_id}", method="GET", status_code="200") == 2.0


async def test_a_handler_that_raises_is_recorded_as_a_500():
    client, metrics = _app(app_name="http-server-500")

    async with client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert _count(metrics=metrics, endpoint="/boom", method="GET", status_code="500") == 1.0


async def test_an_unrouted_path_folds_into_one_series():
    client, metrics = _app(app_name="http-server-404")

    async with client:
        await client.get("/no/such/path")
        await client.get("/another/missing/path")

    assert _count(metrics=metrics, endpoint=UNMATCHED_ROUTE, method="GET", status_code="404") == 2.0


async def test_probe_paths_are_not_recorded():
    client, metrics = _app(app_name="http-server-probe")

    async with client:
        await client.get("/livez")

    assert SERIES not in metrics.get_metrics().decode()


@pytest.mark.parametrize(("sent", "recorded", "status_code"), [("get", "GET", "200"), ("PURGE", "_OTHER", "405")])
async def test_methods_are_normalised(sent: str, recorded: str, status_code: str):
    client, metrics = _app(app_name=f"http-server-method-{recorded.lower()}")

    async with client:
        await client.request(method=sent, url="/items/1")

    assert _count(metrics=metrics, endpoint="/items/{item_id}", method=recorded, status_code=status_code) == 1.0


async def test_an_included_router_is_labelled_with_its_full_prefixed_template():
    app = FastAPI()
    app.include_router(_accounts_router(prefix="/auth"), prefix="/api/v1")
    client, metrics = _instrumented(app=app, app_name="http-server-included")

    async with client:
        response = await client.get("/api/v1/auth/accounts/alice")

    assert response.status_code == 200
    assert _count(metrics=metrics, endpoint="/api/v1/auth/accounts/{username}", method="GET", status_code="200") == 1.0
    assert "alice" not in metrics.get_metrics().decode()


async def test_routers_sharing_an_inner_path_get_a_series_each():
    app = FastAPI()
    app.include_router(_accounts_router(), prefix="/users")
    app.include_router(_accounts_router(), prefix="/admins")
    client, metrics = _instrumented(app=app, app_name="http-server-shared-inner")

    async with client:
        await client.get("/users/accounts/alice")
        await client.get("/admins/accounts/bob")

    assert _count(metrics=metrics, endpoint="/users/accounts/{username}", method="GET", status_code="200") == 1.0
    assert _count(metrics=metrics, endpoint="/admins/accounts/{username}", method="GET", status_code="200") == 1.0


async def test_one_router_included_twice_is_labelled_per_prefix():
    app = FastAPI()
    router = _accounts_router()
    app.include_router(router, prefix="/v1")
    app.include_router(router, prefix="/v2")
    client, metrics = _instrumented(app=app, app_name="http-server-included-twice")

    async with client:
        await client.get("/v1/accounts/alice")
        await client.get("/v2/accounts/alice")

    assert _count(metrics=metrics, endpoint="/v1/accounts/{username}", method="GET", status_code="200") == 1.0
    assert _count(metrics=metrics, endpoint="/v2/accounts/{username}", method="GET", status_code="200") == 1.0


async def test_nested_routers_carry_every_prefix():
    outer = APIRouter(prefix="/outer")
    outer.include_router(_accounts_router(prefix="/inner"), prefix="/middle")
    app = FastAPI()
    app.include_router(outer, prefix="/api")
    client, metrics = _instrumented(app=app, app_name="http-server-nested")

    async with client:
        await client.get("/api/outer/middle/inner/accounts/alice")

    assert (
        _count(metrics=metrics, endpoint="/api/outer/middle/inner/accounts/{username}", method="GET", status_code="200")
        == 1.0
    )


async def test_a_mounted_sub_app_carries_the_mount_path():
    sub_app = FastAPI()
    sub_app.include_router(_accounts_router(), prefix="/r")
    app = FastAPI()
    app.mount("/sub", sub_app)
    client, metrics = _instrumented(app=app, app_name="http-server-mount")

    async with client:
        await client.get("/sub/r/accounts/alice")

    assert _count(metrics=metrics, endpoint="/sub/r/accounts/{username}", method="GET", status_code="200") == 1.0


async def test_a_value_that_also_appears_in_the_prefix_keeps_the_full_template():
    """The label depends on the route, never on whether a value happens to match prefix text."""
    app = FastAPI()
    app.include_router(_accounts_router(), prefix="/api/v1")
    client, metrics = _instrumented(app=app, app_name="http-server-value-in-prefix")

    async with client:
        await client.get("/api/v1/items/1")
        await client.get("/api/v1/accounts/v1")

    assert _count(metrics=metrics, endpoint="/api/v1/items/{item_id:int}", method="GET", status_code="200") == 1.0
    assert _count(metrics=metrics, endpoint="/api/v1/accounts/{username}", method="GET", status_code="200") == 1.0


async def test_an_empty_route_path_takes_the_prefix_it_is_included_under():
    router = APIRouter()

    @router.get("")
    def listing() -> dict:
        return {"items": []}

    app = FastAPI()
    app.include_router(router, prefix="/items")
    client, metrics = _instrumented(app=app, app_name="http-server-empty-path")

    async with client:
        await client.get("/items")

    assert _count(metrics=metrics, endpoint="/items", method="GET", status_code="200") == 1.0


async def test_a_method_the_route_does_not_take_keeps_the_full_template():
    app = FastAPI()
    app.include_router(_accounts_router(), prefix="/api")
    client, metrics = _instrumented(app=app, app_name="http-server-included-405")

    async with client:
        response = await client.post("/api/accounts/alice")

    assert response.status_code == 405
    assert _count(metrics=metrics, endpoint="/api/accounts/{username}", method="POST", status_code="405") == 1.0


async def test_the_server_root_path_stays_out_of_the_template():
    app = FastAPI()
    app.include_router(_accounts_router(), prefix="/api")
    client, metrics = _instrumented(app=app, app_name="http-server-root-path", root_path="/proxy")

    async with client:
        await client.get("/proxy/api/accounts/alice")

    assert _count(metrics=metrics, endpoint="/api/accounts/{username}", method="GET", status_code="200") == 1.0


async def test_an_unrouted_path_under_a_prefix_stays_unmatched():
    app = FastAPI()
    app.include_router(_accounts_router(), prefix="/api")
    client, metrics = _instrumented(app=app, app_name="http-server-included-404")

    async with client:
        await client.get("/api/no/such/path")

    assert _count(metrics=metrics, endpoint=UNMATCHED_ROUTE, method="GET", status_code="404") == 1.0


async def test_a_parameterised_router_prefix_never_puts_its_value_in_the_label():
    app = FastAPI()
    app.include_router(_accounts_router(), prefix="/tenants/{tenant}")
    client, metrics = _instrumented(app=app, app_name="http-server-param-prefix")

    async with client:
        await client.get("/tenants/acme/accounts/alice")

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint=UNRESOLVED_ROUTE, method="GET", status_code="200") == 1.0
    assert "acme" not in exposition
    assert "alice" not in exposition


async def test_a_parameterised_mount_is_labelled_with_its_template():
    sub_app = FastAPI()
    sub_app.include_router(_accounts_router())
    app = FastAPI()
    app.mount("/orgs/{org}", sub_app)
    client, metrics = _instrumented(app=app, app_name="http-server-param-mount")

    async with client:
        await client.get("/orgs/acme/accounts/alice")

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint="/orgs/{org}/accounts/{username}", method="GET", status_code="200") == 1.0
    assert "acme" not in exposition
    assert "alice" not in exposition


def _shadowed_mount_app() -> FastAPI:
    """A mount parameter the route's own parameter of the same name overwrites on the scope."""
    sub_app = FastAPI()

    @sub_app.get("/accounts/{org}")
    def account(org: str) -> dict:
        return {"org": org}

    app = FastAPI()
    app.mount("/orgs/{org}", sub_app)
    return app


async def test_a_mount_parameter_shadowed_by_the_route_keeps_the_mount_template():
    client, metrics = _instrumented(app=_shadowed_mount_app(), app_name="http-server-shadowed-mount")

    async with client:
        await client.get("/orgs/acme/accounts/alice")

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint="/orgs/{org}/accounts/{org}", method="GET", status_code="200") == 1.0
    assert "acme" not in exposition


async def test_distinct_mount_values_share_one_series():
    """A scan of mount values must not mint a series per value."""
    client, metrics = _instrumented(app=_shadowed_mount_app(), app_name="http-server-mount-cardinality")

    async with client:
        for number in range(50):
            await client.get(f"/orgs/org{number}/accounts/alice")

    series = [line for line in metrics.get_metrics().decode().splitlines() if line.startswith(SERIES)]
    assert series == [
        'http_server_request_duration_seconds_count{endpoint="/orgs/{org}/accounts/{org}",method="GET",status_code="200"} 50.0'
    ]


async def test_nested_parameterised_mounts_keep_every_template():
    app = Starlette(routes=[Mount("/a/{x}", routes=[Mount("/b/{x}", routes=[Route("/c/{x}", _ok)])])])
    client, metrics = _instrumented(app=app, app_name="http-server-nested-mounts")

    async with client:
        response = await client.get("/a/alpha/b/bravo/c/charlie")

    exposition = metrics.get_metrics().decode()
    assert response.status_code == 200
    assert _count(metrics=metrics, endpoint="/a/{x}/b/{x}/c/{x}", method="GET", status_code="200") == 1.0
    assert "alpha" not in exposition
    assert "bravo" not in exposition


async def test_a_starlette_mount_shadowed_by_its_route_keeps_the_mount_template():
    app = Starlette(routes=[Mount("/m/{org}", routes=[Route("/t/{org}", _ok)])])
    client, metrics = _instrumented(app=app, app_name="http-server-starlette-mount")

    async with client:
        await client.get("/m/acme/t/alice")

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint="/m/{org}/t/{org}", method="GET", status_code="200") == 1.0
    assert "acme" not in exposition


async def test_a_request_that_ends_at_a_mount_is_labelled_with_the_mount_template():
    app = Starlette(routes=[Mount("/m/{org}", routes=[Route("/t", _ok)])])
    client, metrics = _instrumented(app=app, app_name="http-server-ends-at-mount")

    async with client:
        await client.get("/m/acme/missing")

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint="/m/{org}", method="GET", status_code="404") == 1.0
    assert "acme" not in exposition


async def test_a_mount_inside_an_included_router_is_unresolved():
    """The mount sits inside FastAPI's included-router wrapper, where its template cannot be read."""
    sub_app = FastAPI()

    @sub_app.get("/items/{org}")
    def item(org: str) -> dict:
        return {"org": org}

    router = APIRouter()
    router.mount("/orgs/{org}", sub_app)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client, metrics = _instrumented(app=app, app_name="http-server-included-mount")

    async with client:
        await client.get("/api/orgs/acme/items/alice")

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint=UNRESOLVED_ROUTE, method="GET", status_code="200") == 1.0
    assert "acme" not in exposition


@pytest.mark.parametrize(("case", "path"), [("same", "/m/acme/i/acme/r"), ("different", "/m/acme/i/beta/r")])
async def test_a_router_prefix_parameter_named_like_a_mount_parameter_is_unresolved(case: str, path: str):
    """The prefix value overwrites the mount's on the scope, so neither may reach the label."""
    router = APIRouter()

    @router.get("/r")
    def leaf() -> dict:
        return {}

    sub_app = FastAPI()
    sub_app.include_router(router, prefix="/i/{x}")
    app = FastAPI()
    app.mount("/m/{x}", sub_app)
    client, metrics = _instrumented(app=app, app_name=f"http-server-prefix-shadow-{case}")

    async with client:
        await client.get(path)

    exposition = metrics.get_metrics().decode()
    assert _count(metrics=metrics, endpoint=UNRESOLVED_ROUTE, method="GET", status_code="200") == 1.0
    assert "acme" not in exposition
    assert "beta" not in exposition


@pytest.mark.parametrize(
    ("convertor", "values"),
    [
        ("float", ["1", "2", "3", "4", "5"]),
        ("int", ["1", "2", "3", "4", "5"]),
        ("float", ["1.5", "2.5", "3.5", "4.5", "5.5"]),
    ],
)
async def test_typed_router_prefix_values_under_a_typed_mount_share_one_series(convertor: str, values: list[str]):
    """A value's text never round-trips reliably, so prefix text beside a mount value is never labelled."""
    router = APIRouter()

    @router.get("/r")
    def leaf() -> dict:
        return {}

    sub_app = FastAPI()
    sub_app.include_router(router, prefix=f"/i/{{x:{convertor}}}")
    app = FastAPI()
    app.mount(f"/m/{{x:{convertor}}}", sub_app)
    client, metrics = _instrumented(app=app, app_name=f"http-server-typed-shadow-{convertor}-{len(values[0])}")

    async with client:
        for value in values:
            await client.get(f"/m/{value}/i/{value}/r")

    series = [line for line in metrics.get_metrics().decode().splitlines() if line.startswith(SERIES)]
    assert series == [
        'http_server_request_duration_seconds_count{endpoint="__unresolved__",method="GET",status_code="200"} 5.0'
    ]


class _BrokenMount:
    """Looks like a Starlette mount, but its pattern is a plain string."""

    path = "/m"
    path_format = "/m/{path}"
    path_regex = "^/m/(?P<path>.*)$"
    param_convertors: dict = {}
    routes: list = []


class _BrokenRouter:
    routes = (_BrokenMount(),)


async def test_a_route_tree_the_label_cannot_read_is_still_recorded():
    """Deriving the label must never cost the sample, or raise out of the middleware."""

    async def app(scope, receive, send) -> None:
        scope.update(route=_BrokenMount(), router=_BrokenRouter(), app_root_path="", root_path="/m")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    metrics = create_metrics("http-server-broken-tree", backend="prometheus")
    instrumented = HttpServerMetricsMiddleware(app, metrics=metrics)
    transport = httpx.ASGITransport(app=instrumented)

    async with httpx.AsyncClient(base_url="http://test", transport=transport) as client:
        response = await client.get("/m/anything")

    assert response.status_code == 200
    assert _count(metrics=metrics, endpoint=UNRESOLVED_ROUTE, method="GET", status_code="200") == 1.0
