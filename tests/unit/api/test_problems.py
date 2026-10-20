#  Project:   scalo
#  File:      tests/unit/api/test_problems.py
#  Purpose:   RFC 9457 problem+json responses and their declaration in the spec
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Every error answers ``application/problem+json``, exercised over real HTTP with TestClient."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from scalo.api import (
    PROBLEM_MEDIA_TYPE,
    FieldError,
    ProblemError,
    declare_problem_responses,
    install_problem_handlers,
)


class Body(BaseModel):
    name: str
    size: int


def _app(*, catch_unhandled: bool = True) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app, catch_unhandled=catch_unhandled)

    @app.get("/problem")
    def problem() -> dict:
        raise ProblemError(
            409,
            "The name is taken",
            code="conflict",
            errors=[FieldError(field="name", location="body", detail="taken")],
            headers={"Retry-After": "5"},
            holder="other",
        )

    @app.get("/http-text")
    def http_text() -> dict:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/http-dict")
    def http_dict() -> dict:
        raise HTTPException(
            status_code=403, detail={"code": "forbidden", "message": "Denied", "context": {"action": "a:b"}}
        )

    @app.post("/items")
    def create(body: Body, limit: int = 10) -> dict:
        return {}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("secret internals")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


class TestResponses:
    """What a client receives."""

    def test_problem_error(self, client):
        response = client.get("/problem")

        assert response.status_code == 409
        assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
        assert response.headers["retry-after"] == "5"
        assert response.json() == {
            "type": "about:blank",
            "title": "Conflict",
            "status": 409,
            "detail": "The name is taken",
            "code": "conflict",
            "errors": [{"field": "name", "location": "body", "detail": "taken"}],
            "holder": "other",
        }

    def test_http_exception_with_text(self, client):
        response = client.get("/http-text")

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json() == {
            "type": "about:blank",
            "title": "Unauthorized",
            "status": 401,
            "detail": "Authentication required",
        }

    def test_http_exception_with_a_code_and_message(self, client):
        body = client.get("/http-dict").json()

        assert (body["code"], body["detail"], body["context"]) == ("forbidden", "Denied", {"action": "a:b"})

    def test_an_unknown_route_answers_a_problem(self, client):
        response = client.get("/nowhere")

        assert response.status_code == 404
        assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE

    def test_validation_reports_each_field(self, client):
        response = client.post("/items?limit=many", json={"name": "a"})

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "validation_error"
        by_field = {(error["location"], error["field"]): error for error in body["errors"]}
        assert by_field[("body", "size")]["code"] == "missing"
        assert by_field[("body", "size")]["pointer"] == "#/size"
        assert by_field[("query", "limit")]["code"] == "int_parsing"
        assert "pointer" not in by_field[("query", "limit")]

    def test_an_unhandled_exception_never_echoes_its_message(self, client):
        response = client.get("/boom")

        assert response.status_code == 500
        assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
        assert "secret internals" not in response.text

    def test_without_catch_unhandled_the_exception_propagates(self):
        with pytest.raises(RuntimeError, match="secret internals"):
            TestClient(_app(catch_unhandled=False)).get("/boom")


class TestProblemError:
    def test_title_defaults_to_the_reason_phrase(self):
        assert ProblemError(412).problem.title == "Precondition Failed"
        assert ProblemError(599).problem.title == "Error"

    def test_an_extension_may_not_reuse_a_defined_member(self):
        with pytest.raises(ValueError, match="type"):
            ProblemError(400, type="https://example.com/bad")

    def test_instance_names_the_occurrence(self):
        assert ProblemError(404, instance="/requests/7").problem.instance == "/requests/7"


class TestSpec:
    """``declare_problem_responses`` makes the spec say what the server sends."""

    def test_errors_are_declared_as_problems(self):
        spec = _app().openapi()
        declare_problem_responses(spec)
        responses = spec["paths"]["/items"]["post"]["responses"]

        assert list(responses["422"]["content"]) == [PROBLEM_MEDIA_TYPE]
        assert responses["default"]["content"][PROBLEM_MEDIA_TYPE]["schema"]["$ref"].endswith("/Problem")
        assert {"Problem", "FieldError"} <= set(spec["components"]["schemas"])
        assert "HTTPValidationError" not in spec["components"]["schemas"]
        assert "ValidationError" not in spec["components"]["schemas"]

    def test_a_validation_schema_still_referenced_is_kept(self):
        spec = _app().openapi()
        spec["paths"]["/items"]["post"]["responses"]["400"] = {
            "description": "x",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}},
        }
        declare_problem_responses(spec)

        assert {"HTTPValidationError", "ValidationError"} <= set(spec["components"]["schemas"])

    def test_an_existing_default_response_is_kept(self):
        spec = _app().openapi()
        spec["paths"]["/items"]["post"]["responses"]["default"] = {"description": "mine"}
        declare_problem_responses(spec)

        assert spec["paths"]["/items"]["post"]["responses"]["default"] == {"description": "mine"}
