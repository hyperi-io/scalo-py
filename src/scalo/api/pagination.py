#  Project:   scalo
#  File:      src/scalo/api/pagination.py
#  Purpose:   AIP-158 list pagination: page_size, page_token, filter, order_by and a server cap
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Paginated lists after AIP-158 (pagination) and AIP-132 (List).

Every list takes the same four query parameters and answers a :class:`Page`::

    @router.get("", response_model=Page[Source])
    def list_sources(query: ListParams) -> Page[Source]:
        return paginate(store.find(query.filter, query.order_by), query)

A ``page_size`` of 0 or none gets the default, one above the cap is cut to it,
and a negative one is refused. The page token is opaque to clients and bound
to the ``filter`` and ``order_by`` it was issued for, so changing either
between pages is refused with 400. It is not a security boundary: decoding one
shows only an offset.
"""

import base64
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel

from .problems import ProblemError

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class ListQuery:
    """One list request's paging, filtering and ordering.

    Attributes:
        page_size: Items to return, already defaulted and capped.
        page_token: The ``next_page_token`` of the previous page, if any.
        filter: The filter expression, in the API's own filter syntax.
        order_by: The ordering, such as ``name desc``.
    """

    page_size: int
    page_token: str | None = None
    filter: str | None = None
    order_by: str | None = None


def list_query(
    *, default_page_size: int = DEFAULT_PAGE_SIZE, max_page_size: int = MAX_PAGE_SIZE
) -> Callable[..., ListQuery]:
    """Build the FastAPI dependency that reads a list's query parameters.

    Args:
        default_page_size: Page size when the caller sends none, or 0.
        max_page_size: The server cap a larger request is cut to.

    Returns:
        A dependency answering :class:`ListQuery`.

    Raises:
        ValueError: Unless ``1 <= default_page_size <= max_page_size``.
    """
    if not 1 <= default_page_size <= max_page_size:
        raise ValueError(f"need 1 <= default_page_size ({default_page_size}) <= max_page_size ({max_page_size})")

    def dependency(
        page_size: Annotated[
            int,
            Query(ge=0, description=f"Items per page: 0 means {default_page_size}, above {max_page_size} is cut to it"),
        ] = 0,
        page_token: Annotated[str | None, Query(description="The next_page_token of the previous page")] = None,
        filter: Annotated[str | None, Query(description="Filter expression")] = None,
        order_by: Annotated[str | None, Query(description="Ordering, such as `name desc`")] = None,
    ) -> ListQuery:
        size = default_page_size if page_size == 0 else min(page_size, max_page_size)
        return ListQuery(page_size=size, page_token=page_token, filter=filter, order_by=order_by)

    return dependency


ListParams = Annotated[ListQuery, Depends(list_query())]


class Page[T](BaseModel):
    """One page of a list.

    Attributes:
        items: The page's items.
        next_page_token: Token for the next page, ``None`` on the last one.
        total_size: Items across every page, when the server counts them.
    """

    items: list[T]
    next_page_token: str | None = None
    total_size: int | None = None


def _fingerprint(query: ListQuery) -> str:
    """The filter and ordering a token is bound to."""
    text = json.dumps([query.filter, query.order_by])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def encode_page_token(offset: int, query: ListQuery) -> str:
    """An opaque token resuming the list at ``offset`` under the same filter and ordering."""
    payload = json.dumps({"o": offset, "f": _fingerprint(query)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_page_token(query: ListQuery) -> int:
    """The offset ``query.page_token`` resumes at, 0 when there is no token.

    Raises:
        ProblemError: 400 ``invalid_page_token`` when the token is malformed, or
            was issued for a different filter or ordering.
    """
    token = query.page_token
    if not token:
        return 0
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    # binascii.Error, UnicodeError and JSONDecodeError are all ValueErrors.
    except ValueError as exc:
        raise ProblemError(400, "The page_token is not one this API issued", code="invalid_page_token") from exc
    offset = payload.get("o") if isinstance(payload, dict) else None
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ProblemError(400, "The page_token is not one this API issued", code="invalid_page_token")
    if payload.get("f") != _fingerprint(query):
        raise ProblemError(
            400, "The page_token was issued for a different filter or order_by", code="invalid_page_token"
        )
    return offset


def paginate[T](items: Sequence[T], query: ListQuery, *, with_total: bool = True) -> Page[T]:
    """Cut one page out of a list the server already filtered and ordered.

    Args:
        items: Every matching item, in order.
        query: The list request.
        with_total: Report ``total_size``.

    Returns:
        The page, with a ``next_page_token`` unless it is the last.

    Raises:
        ProblemError: 400 ``invalid_page_token`` on a bad token.
    """
    start = decode_page_token(query)
    end = start + query.page_size
    next_token = encode_page_token(end, query) if end < len(items) else None
    return Page[T](
        items=list(items[start:end]),
        next_page_token=next_token,
        total_size=len(items) if with_total else None,
    )
