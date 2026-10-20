#  Project:   scalo
#  File:      src/scalo/api/problems.py
#  Purpose:   RFC 9457 problem+json errors with field-level detail
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""RFC 9457 Problem Details for every error an API returns.

A handler raises :class:`ProblemError`, or the HTTPException it already raises,
and the client gets ``application/problem+json``::

    {"type": "about:blank", "title": "Precondition Failed", "status": 412,
     "detail": "If-Match does not match the current ETag", "code": "etag_mismatch",
     "etag": "<the current entity-tag>"}

A request that fails validation answers 422 with one entry per field in
``errors``, as AIP-193 asks for field-level detail.
"""

import json
from collections.abc import Iterable, Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.constants import REF_TEMPLATE
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from scalo.logger import logger

PROBLEM_MEDIA_TYPE = "application/problem+json"

# Members RFC 9457 defines, which an extension member may not reuse.
_RESERVED = frozenset({"type", "title", "status", "detail", "instance"})

# Where FastAPI's request validation reports a problem, as the first element of each error's loc.
_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})

# Detail text for a 500, which never carries the exception's own message.
_UNHANDLED_DETAIL = "An unexpected error occurred"

_DEFAULT_ERROR_SCHEMAS = ("HTTPValidationError", "ValidationError")


class FieldError(BaseModel):
    """One invalid field in a request.

    Attributes:
        field: Dotted path to the field below its location, ``""`` for the whole location.
        location: ``body``, ``query``, ``path``, ``header`` or ``cookie``.
        detail: What is wrong with it.
        code: Machine-readable reason, such as ``missing`` or ``int_parsing``.
        pointer: JSON Pointer into the request body, for a body field only.
    """

    field: str
    location: str | None = None
    detail: str
    code: str | None = None
    pointer: str | None = None


class Problem(BaseModel):
    """An RFC 9457 problem details object, open to extension members.

    Attributes:
        type: URI naming the problem type. ``about:blank`` means the status says it all.
        title: Short summary of the problem type.
        status: The HTTP status code.
        detail: What went wrong in this occurrence.
        instance: URI naming this occurrence.
        code: Machine-readable code a client branches on.
        errors: One entry per invalid field.
    """

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str | None = None
    errors: list[FieldError] = Field(default_factory=list)


class ProblemError(Exception):
    """An error a handler raises to answer with one problem+json response.

    Args:
        status: The HTTP status code.
        detail: What went wrong in this occurrence.
        code: Machine-readable code a client branches on.
        title: Short summary. Defaults to the status code's reason phrase.
        problem_type: URI naming the problem type.
        instance: URI naming this occurrence.
        errors: Invalid fields.
        headers: Response headers, such as ``Retry-After``.
        **extensions: Extra members, such as the current ``etag``.

    Raises:
        ValueError: When an extension reuses a member RFC 9457 defines.
    """

    def __init__(
        self,
        status: int,
        detail: str | None = None,
        *,
        code: str | None = None,
        title: str | None = None,
        problem_type: str = "about:blank",
        instance: str | None = None,
        errors: Iterable[FieldError] = (),
        headers: Mapping[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        clash = sorted(_RESERVED.intersection(extensions))
        if clash:
            raise ValueError(f"extension members may not reuse {clash}")
        super().__init__(detail or _phrase(status))
        self.status = status
        self.headers = dict(headers or {})
        self.problem = Problem(
            type=problem_type,
            title=title or _phrase(status),
            status=status,
            detail=detail,
            instance=instance,
            code=code,
            errors=list(errors),
            **extensions,
        )


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(problem: Problem, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """A ``application/problem+json`` response carrying ``problem``."""
    body = problem.model_dump(mode="json", exclude_none=True)
    if not body.get("errors"):
        body.pop("errors", None)
    return JSONResponse(body, status_code=problem.status, headers=dict(headers or {}), media_type=PROBLEM_MEDIA_TYPE)


def _from_http_exception(exc: StarletteHTTPException) -> Problem:
    """The problem an HTTPException describes, reading ``code`` and ``message`` from a dict detail."""
    detail: Any = exc.detail
    if not isinstance(detail, dict):
        return Problem(title=_phrase(exc.status_code), status=exc.status_code, detail=str(detail))
    text = detail.get("detail", detail.get("message"))
    code = detail.get("code")
    extensions = {
        key: value
        for key, value in detail.items()
        if key not in _RESERVED and key not in {"code", "message", "errors"} and isinstance(key, str)
    }
    return Problem(
        title=_phrase(exc.status_code),
        status=exc.status_code,
        detail=text if isinstance(text, str) else None,
        code=code if isinstance(code, str) else None,
        **extensions,
    )


def _pointer(parts: list[str]) -> str:
    escaped = [part.replace("~", "~0").replace("/", "~1") for part in parts]
    return "#/" + "/".join(escaped) if escaped else "#"


def field_errors(errors: Iterable[Mapping[str, Any]]) -> list[FieldError]:
    """FastAPI validation errors as problem field errors.

    Args:
        errors: ``RequestValidationError.errors()``.

    Returns:
        One entry per error, located by where FastAPI found it.
    """
    found: list[FieldError] = []
    for error in errors:
        loc = [str(part) for part in error.get("loc", ())]
        location = loc[0] if loc and loc[0] in _LOCATIONS else None
        parts = loc[1:] if location else loc
        found.append(
            FieldError(
                field=".".join(parts),
                location=location,
                detail=str(error.get("msg", "invalid")),
                code=error.get("type"),
                pointer=_pointer(parts) if location == "body" else None,
            )
        )
    return found


def install_problem_handlers(app: FastAPI, *, catch_unhandled: bool = True) -> None:
    """Answer every error the app raises with ``application/problem+json``.

    Covers :class:`ProblemError`, every ``HTTPException`` (a dict detail's
    ``code`` and ``message`` become ``code`` and ``detail``, its other keys
    extension members), and request validation (422 with field errors).

    Args:
        app: The application.
        catch_unhandled: Also answer an unhandled exception with a 500 problem,
            logged with its route template and never echoing its message.
    """

    async def problem_error(_request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, ProblemError):
            raise exc
        return problem_response(exc.problem, exc.headers)

    async def http_error(_request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, StarletteHTTPException):
            raise exc
        return problem_response(_from_http_exception(exc), exc.headers)

    async def validation_error(_request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, RequestValidationError):
            raise exc
        errors = field_errors(exc.errors())
        problem = Problem(
            title=_phrase(422),
            status=422,
            detail=f"The request has {len(errors)} invalid field(s)",
            code="validation_error",
            errors=errors,
        )
        return problem_response(problem)

    app.add_exception_handler(ProblemError, problem_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)

    if catch_unhandled:

        async def unhandled(request: Request, exc: Exception) -> JSONResponse:
            route = getattr(request.scope.get("route"), "path_format", None) or "__unmatched__"
            logger.opt(exception=exc).error("Unhandled exception", method=request.method, route=route)
            return problem_response(Problem(title=_phrase(500), status=500, detail=_UNHANDLED_DETAIL))

        app.add_exception_handler(Exception, unhandled)


def _problem_content() -> dict[str, Any]:
    return {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": REF_TEMPLATE.format(model=Problem.__name__)}}}


def declare_problem_responses(spec: dict[str, Any]) -> None:
    """Declare problem+json as every operation's error response in ``spec``.

    Adds the ``Problem`` schema, points FastAPI's default 422 at it, adds a
    ``default`` response where an operation has none, and drops FastAPI's
    validation-error schemas once nothing references them.

    Args:
        spec: The generated OpenAPI document, updated in place.
    """
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    definition = Problem.model_json_schema(ref_template=REF_TEMPLATE)
    for nested_name, nested in definition.pop("$defs", {}).items():
        schemas.setdefault(nested_name, nested)
    schemas.setdefault(Problem.__name__, definition)

    default_ref = REF_TEMPLATE.format(model=_DEFAULT_ERROR_SCHEMAS[0])
    for item in spec.get("paths", {}).values():
        for operation in item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            responses = operation["responses"]
            invalid = responses.get("422")
            if isinstance(invalid, dict) and default_ref in json.dumps(invalid.get("content", {})):
                invalid["content"] = _problem_content()
            responses.setdefault(
                "default", {"description": "Problem details (RFC 9457)", "content": _problem_content()}
            )

    for name in _DEFAULT_ERROR_SCHEMAS:
        others = {key: value for key, value in schemas.items() if key != name}
        if REF_TEMPLATE.format(model=name) not in json.dumps({**spec, "components": {"schemas": others}}):
            schemas.pop(name, None)
    spec["components"]["schemas"] = dict(sorted(schemas.items()))
