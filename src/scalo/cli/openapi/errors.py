#  Project:   scalo
#  File:      src/scalo/cli/openapi/errors.py
#  Purpose:   Exit codes and error reports for the generated CLI, read from problem+json
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Exit codes and the error report a failed command prints.

The codes are the HyperI CLI family's, mapped from the HTTP status of the
problem+json answer (RFC 9457) an API returns:

====  ==========  ===========================================================
Code  Name        When
====  ==========  ===========================================================
0     OK          success
1     GENERAL     a 5xx, a 429, an unreachable API, any other failure
2     USAGE       bad flags or input, or a 400, 422 or 428 from the API
3     NOT_FOUND   404 or 410
4     PERMISSION  401 or 403
5     CONFLICT    409 or 412
====  ==========  ===========================================================

The report goes to stderr: lines for a person, or a JSON object when the output
format is ``json``. Either form echoes the input that failed and suggests what
to do, where the CLI can tell.
"""

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from http import HTTPStatus
from typing import Any

from .transport import Response, TransportError


class ExitCode(IntEnum):
    """The process exit codes."""

    OK = 0
    GENERAL = 1
    USAGE = 2
    NOT_FOUND = 3
    PERMISSION = 4
    CONFLICT = 5


_STATUS_CODES: dict[int, ExitCode] = {
    400: ExitCode.USAGE,
    401: ExitCode.PERMISSION,
    403: ExitCode.PERMISSION,
    404: ExitCode.NOT_FOUND,
    409: ExitCode.CONFLICT,
    410: ExitCode.NOT_FOUND,
    412: ExitCode.CONFLICT,
    422: ExitCode.USAGE,
    428: ExitCode.USAGE,
}


def exit_code_for_status(status: int) -> ExitCode:
    """The exit code an HTTP error status maps to."""
    return _STATUS_CODES.get(status, ExitCode.GENERAL)


class CliError(Exception):
    """A failure the CLI reports as a line, not a traceback.

    Args:
        message: What went wrong.
        error_type: Stable machine-readable name.
        exit_code: The process exit code.
        input: The input that failed, echoed in the report.
        suggestion: What to do instead.
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "error",
        exit_code: ExitCode = ExitCode.GENERAL,
        input: Mapping[str, Any] | None = None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.exit_code = exit_code
        self.input = dict(input or {})
        self.suggestion = suggestion


class CliUsageError(CliError):
    """Bad flags or input, found before any request was sent."""

    def __init__(self, message: str, *, input: Mapping[str, Any] | None = None, suggestion: str | None = None) -> None:
        super().__init__(message, error_type="usage", exit_code=ExitCode.USAGE, input=input, suggestion=suggestion)


class CliConfigError(CliError):
    """No endpoint, or an unreadable profile or credential."""

    def __init__(self, message: str, *, suggestion: str | None = None) -> None:
        super().__init__(message, error_type="config", exit_code=ExitCode.USAGE, suggestion=suggestion)


class ApiError(Exception):
    """The API answered with a status outside 2xx.

    Args:
        response: The answer.
        input: The call's path and query values, echoed in the report.
        suggestion: What to do instead.
    """

    def __init__(
        self, response: Response, *, input: Mapping[str, Any] | None = None, suggestion: str | None = None
    ) -> None:
        self.response = response
        self.input = dict(input or {})
        self.suggestion = suggestion
        super().__init__(f"HTTP {response.status}")


@dataclass(frozen=True, slots=True)
class ErrorReport:
    """What a failed command prints.

    Attributes:
        error_type: Stable machine-readable name, the problem's ``code`` when it has one.
        message: What went wrong.
        exit_code: The process exit code.
        status: The HTTP status, when the API answered.
        errors: Field-level detail, ``(field, detail)`` pairs.
        retryable: Whether the same call could succeed later.
        input: The input that failed, empty when there is none to echo.
        suggestion: What to do instead, ``None`` when the CLI cannot tell.
    """

    error_type: str
    message: str
    exit_code: ExitCode
    status: int | None = None
    errors: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    retryable: bool = False
    input: Mapping[str, Any] = field(default_factory=dict)
    suggestion: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """The report as the JSON object ``--output json`` prints."""
        body: dict[str, Any] = {
            "error_type": self.error_type,
            "message": self.message,
            "input": dict(self.input),
            "suggestion": self.suggestion,
            "retryable": self.retryable,
        }
        if self.status is not None:
            body["status"] = self.status
        if self.errors:
            body["errors"] = [{"field": name, "detail": detail} for name, detail in self.errors]
        return body

    def text(self) -> str:
        """The report as the lines a terminal shows."""
        label = self.error_type if self.status is None else f"{self.status} {self.error_type}"
        lines = [f"Error ({label}): {self.message}"]
        lines.extend(f"  {name or '(request)'}: {detail}" for name, detail in self.errors)
        if self.suggestion:
            lines.append(f"  suggestion: {self.suggestion}")
        return "\n".join(lines)

    def render(self, as_json: bool) -> str:
        """The report in the chosen form."""
        return json.dumps(self.as_dict()) if as_json else self.text()


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def _field_errors(raw: Any) -> tuple[tuple[str, str], ...]:
    """Field errors from problem+json ``errors``, or FastAPI's default 422 ``detail`` list."""
    found: list[tuple[str, str]] = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, Mapping):
            continue
        if "loc" in item:
            location = [str(part) for part in item.get("loc") or ()]
            name = ".".join(
                location[1:] if location[:1] and location[0] in ("body", "query", "path", "header") else location
            )
            found.append((name, str(item.get("msg", ""))))
        else:
            found.append((str(item.get("field", "")), str(item.get("detail", item.get("message", "")))))
    return tuple(found)


def report_for_response(response: Response) -> ErrorReport:
    """Read an error answer, problem+json first, into a report.

    Args:
        response: A non-2xx answer.

    Returns:
        The report, using whatever detail the body carries.
    """
    status = response.status
    error_type = _phrase(status).lower().replace(" ", "_")
    message = response.reason or _phrase(status)
    errors: tuple[tuple[str, str], ...] = ()
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, Mapping):
        detail = body.get("detail")
        if isinstance(detail, Mapping):
            # An HTTPException carrying a dict: its keys are the problem's.
            nested = detail
            body = {**body, **nested}
            detail = nested.get("message", nested.get("detail"))
        if isinstance(detail, list):
            errors, detail = _field_errors(detail), None
        if isinstance(body.get("code"), str) and body["code"]:
            error_type = body["code"]
        text = detail or body.get("message") or body.get("title")
        if isinstance(text, str) and text:
            message = text
        errors = errors or _field_errors(body.get("errors"))
    elif isinstance(body, str) and body:
        message = body
    return ErrorReport(
        error_type=error_type,
        message=message,
        exit_code=exit_code_for_status(status),
        status=status,
        errors=errors,
        retryable=status == 429 or status >= 500,
    )


def report_for(exc: BaseException) -> ErrorReport | None:
    """The report for an error the CLI knows how to describe, ``None`` for any other.

    Args:
        exc: The raised error.

    Returns:
        The report, or ``None`` for an error that should surface as a traceback.
    """
    if isinstance(exc, ApiError):
        return dataclasses.replace(report_for_response(exc.response), input=exc.input, suggestion=exc.suggestion)
    if isinstance(exc, CliError):
        return ErrorReport(
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
            input=exc.input,
            suggestion=exc.suggestion,
        )
    if isinstance(exc, TransportError):
        return ErrorReport(
            error_type="connection",
            message=str(exc),
            exit_code=ExitCode.GENERAL,
            retryable=True,
            suggestion="check the endpoint URL and that the API is reachable, then retry",
        )
    return None
