#  Project:   scalo
#  File:      src/scalo/api/operations.py
#  Purpose:   AIP-151 long-running operations: the Operation model and the 202 answer that points at it
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Long-running operations after AIP-151, with an RFC 9457 problem as the error.

A request that starts slow work answers 202 with the operation and a
``Location`` to poll. The app stores operations and runs the work::

    @router.post("/{source}/deploy", status_code=202, responses=ACCEPTED_RESPONSES)
    def deploy(source: str, response: Response) -> Operation[DeployProgress, DeployResult]:
        operation = Operation[DeployProgress, DeployResult](name=f"operations/{tasks.start(source)}")
        return accept(response, operation, location=f"/api/v1/{operation.name}")
"""

from typing import Any, Self

from fastapi import Response
from pydantic import BaseModel, model_validator

from scalo.api.problems import Problem

ACCEPTED_RESPONSES: dict[int | str, dict[str, Any]] = {
    202: {
        "description": "Accepted: poll the operation at Location until done",
        "headers": {"Location": {"description": "The operation to poll", "schema": {"type": "string"}}},
    }
}


class Operation[M, R](BaseModel):
    """A long-running operation: pending has neither ``error`` nor ``response``, done has exactly one.

    Attributes:
        name: The operation's resource name, such as ``operations/7f3a``.
        done: Whether it has finished.
        metadata: Progress while it runs.
        error: Why it failed.
        response: What it produced.
    """

    name: str
    done: bool = False
    metadata: M | None = None
    error: Problem | None = None
    response: R | None = None

    @model_validator(mode="after")
    def _one_outcome(self) -> Self:
        outcomes = (self.error is not None) + (self.response is not None)
        if outcomes != int(self.done):
            raise ValueError("a done operation has exactly one of error and response, a pending one neither")
        return self


def accept[O: Operation](response: Response, operation: O, *, location: str) -> O:
    """Answer 202 with ``operation`` and a ``Location`` to poll it at."""
    response.status_code = 202
    response.headers["Location"] = location
    return operation
