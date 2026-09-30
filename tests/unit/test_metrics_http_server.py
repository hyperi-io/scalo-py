"""HttpServerMetricsMiddleware against a real FastAPI app and the Prometheus backend."""

import httpx
import pytest
from fastapi import FastAPI

from scalo.metrics import create_metrics
from scalo.metrics.http_server import UNMATCHED_ROUTE, HttpServerMetricsMiddleware


def _app(app_name: str) -> tuple[httpx.AsyncClient, object]:
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


def _count(metrics: object, *, endpoint: str, method: str, status_code: str) -> float:
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

    assert "http_server_request_duration_seconds_count{" not in metrics.get_metrics().decode()


@pytest.mark.parametrize(("sent", "recorded", "status_code"), [("get", "GET", "200"), ("PURGE", "_OTHER", "405")])
async def test_methods_are_normalised(sent: str, recorded: str, status_code: str):
    client, metrics = _app(app_name=f"http-server-method-{recorded.lower()}")

    async with client:
        await client.request(method=sent, url="/items/1")

    assert _count(metrics=metrics, endpoint="/items/{item_id}", method=recorded, status_code=status_code) == 1.0
