#  Project:   scalo
#  File:      src/scalo/api/pagination.py
#  Purpose:   AIP-158 list pagination: sealed page tokens, skip, a per-list order_by allow-list and a server cap
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Paginated lists after AIP-158 (pagination) and AIP-132 (List).

A list declares the parameters it honours and answers a :class:`Page`::

    SourceList = Annotated[ListQuery, Depends(list_query(order_by=("name", "display_name"), tiebreak="name"))]

    @router.get("", response_model=Page[Source])
    def list_sources(query: SourceList, enabled: bool | None = None) -> Page[Source]:
        rows = sort_by_order(store.find(enabled=enabled), query.order_by)
        return paginate(rows, query, bound={"enabled": enabled})

A ``page_size`` of 0 or none gets the default, one above the cap is cut to it,
and a negative one is refused. A page token is sealed with Fernet, so a client
can neither read nor forge one, and it is bound to the request path,
``filter``, ``order_by`` and every ``bound`` value: a token sent with any of
them changed, tampered with, or older than :data:`PAGE_TOKEN_TTL_SECONDS`
answers 400 ``invalid_page_token``.
"""

import base64
import hashlib
import json
import threading
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import Depends, Query, Request
from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from scalo.api.problems import ProblemError
from scalo.logger import logger

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000
PAGE_TOKEN_TTL_SECONDS = 86_400
PAGE_TOKEN_KEY_SETTING = "api.page_token_key"  # noqa: S105 -- a setting name, not a secret

_INVALID = "The page_token is not one this API issued for this list and these parameters, or it has expired"

# One sealer per process, built on first use from the config cascade.
_sealer: Fernet | None = None
_sealer_lock = threading.Lock()


def _page_sealer() -> Fernet:
    global _sealer
    with _sealer_lock:
        if _sealer is None:
            from scalo.config import settings

            secret = str(settings.get(PAGE_TOKEN_KEY_SETTING) or "")
            if secret:
                if len(secret) < 32:
                    raise ValueError(f"{PAGE_TOKEN_KEY_SETTING} needs at least 32 characters")
                hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"scalo.api page token")
                _sealer = Fernet(base64.urlsafe_b64encode(hkdf.derive(secret.encode("utf-8"))))
            else:
                logger.warning(
                    "No page token key: tokens break across replicas and restarts",
                    setting=PAGE_TOKEN_KEY_SETTING,
                )
                _sealer = Fernet(Fernet.generate_key())
        return _sealer


@dataclass(frozen=True, slots=True)
class SortKey:
    """One field of an ordering.

    Attributes:
        field: The field name, dotted for a subfield.
        descending: Sort high to low.
    """

    field: str
    descending: bool = False

    def __str__(self) -> str:
        """The key as ``order_by`` writes it."""
        return f"{self.field} desc" if self.descending else self.field


@dataclass(frozen=True, slots=True)
class ListQuery:
    """One list request's paging, filtering and ordering.

    Attributes:
        page_size: Items to return, already defaulted and capped.
        page_token: The ``next_page_token`` of the previous page, if any.
        skip: Items to skip past the token's position.
        filter: The filter expression, in the API's own syntax, where the list takes one.
        order_by: The parsed ordering, with the list's tiebreak appended when the client did not name it.
        path: The request path, which a page token is bound to.
    """

    page_size: int
    page_token: str | None = None
    skip: int = 0
    filter: str | None = None
    order_by: tuple[SortKey, ...] = ()
    path: str = ""


def _parse_order_by(text: str, allowed: Collection[str], tiebreak: str | None) -> tuple[SortKey, ...]:
    """Parse ``"display_name desc, name"``, appending ``tiebreak`` when it is not named.

    Raises:
        ValueError: On a field outside ``allowed``, one listed twice, or a direction other than asc or desc.
    """
    keys: list[SortKey] = []
    for part in text.split(","):
        words = part.split()
        if not 1 <= len(words) <= 2 or (len(words) == 2 and words[1].lower() not in {"asc", "desc"}):
            raise ValueError(f"order_by {text!r}: each item is a field, then optionally asc or desc")
        if words[0] not in allowed:
            raise ValueError(f"order_by cannot sort on {words[0]!r}: use one of {sorted(allowed)}")
        if any(key.field == words[0] for key in keys):
            raise ValueError(f"order_by names {words[0]!r} twice")
        keys.append(SortKey(words[0], len(words) == 2 and words[1].lower() == "desc"))
    if tiebreak and all(key.field != tiebreak for key in keys):
        keys.append(SortKey(tiebreak))
    return tuple(keys)


def _unsupported(name: str) -> ProblemError:
    return ProblemError(400, f"This list does not take {name}", code="unsupported_parameter")


def list_query(
    *,
    default_page_size: int = DEFAULT_PAGE_SIZE,
    max_page_size: int = MAX_PAGE_SIZE,
    order_by: Collection[str] = (),
    tiebreak: str | None = None,
    filter: bool = False,
) -> Callable[..., ListQuery]:
    """Build the FastAPI dependency that reads a list's query parameters.

    The spec declares ``filter`` and ``order_by`` only on a list that takes
    them. A request that sends one anyway answers 400 ``unsupported_parameter``.

    Args:
        default_page_size: Page size when the caller sends none, or 0.
        max_page_size: The server cap a larger request is cut to.
        order_by: Fields a client may sort on. Empty takes no ``order_by``.
        tiebreak: A unique field appended to an ordering that does not name it, and the ordering when the client sends none.
        filter: Take the ``filter`` parameter.

    Returns:
        A dependency answering :class:`ListQuery`.

    Raises:
        ValueError: Unless ``1 <= default_page_size <= max_page_size``, or when
            ``order_by`` has no ``tiebreak``.
    """
    if not 1 <= default_page_size <= max_page_size:
        raise ValueError(f"need 1 <= default_page_size ({default_page_size}) <= max_page_size ({max_page_size})")
    if order_by and not tiebreak:
        raise ValueError("an order_by allow-list needs a tiebreak: the list's unique field")
    sorts = bool(order_by)
    default = (SortKey(tiebreak),) if tiebreak else ()
    order_help = f"Ordering over {', '.join(sorted(order_by))}, each optionally followed by desc"

    def dependency(
        request: Request,
        page_size: Annotated[
            int,
            Query(ge=0, description=f"Items per page: 0 means {default_page_size}, above {max_page_size} is cut to it"),
        ] = 0,
        page_token: Annotated[str | None, Query(description="The next_page_token of the previous page")] = None,
        skip: Annotated[int, Query(ge=0, description="Items to skip, after page_token")] = 0,
        filter_text: Annotated[
            str | None, Query(alias="filter", include_in_schema=filter, description="Filter expression")
        ] = None,
        order_text: Annotated[
            str | None, Query(alias="order_by", include_in_schema=sorts, description=order_help)
        ] = None,
    ) -> ListQuery:
        if filter_text is not None and not filter:
            raise _unsupported("filter")
        if order_text is not None and not sorts:
            raise _unsupported("order_by")
        try:
            order = _parse_order_by(order_text, order_by, tiebreak) if order_text else default
        except ValueError as exc:
            raise ProblemError(400, str(exc), code="invalid_order_by") from exc
        size = default_page_size if page_size == 0 else min(page_size, max_page_size)
        return ListQuery(size, page_token, skip, filter_text, order, request.url.path)

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


def _fingerprint(query: ListQuery, bound: Mapping[str, Any] | None) -> str:
    """Everything that shapes the list, which a token is bound to."""
    shape = [query.path, query.filter, [str(key) for key in query.order_by], to_jsonable_python(bound or {})]
    text = json.dumps(shape, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def encode_page_token(offset: int, query: ListQuery, *, bound: Mapping[str, Any] | None = None) -> str:
    """A sealed token resuming the list at ``offset`` under the same path, filter, ordering and ``bound``."""
    payload = json.dumps({"o": offset, "f": _fingerprint(query, bound)}, separators=(",", ":"))
    return _page_sealer().encrypt(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_page_token(query: ListQuery, *, bound: Mapping[str, Any] | None = None) -> int:
    """The offset ``query.page_token`` resumes at, 0 when there is no token.

    Raises:
        ProblemError: 400 ``invalid_page_token`` when the token is forged,
            expired, or was issued for a different path, filter, ordering or ``bound``.
    """
    token = query.page_token
    if not token:
        return 0
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(_page_sealer().decrypt(padded.encode("ascii"), ttl=PAGE_TOKEN_TTL_SECONDS))
    # UnicodeError and JSONDecodeError are ValueErrors.
    except (InvalidToken, ValueError) as exc:
        raise ProblemError(400, _INVALID, code="invalid_page_token") from exc
    offset = payload.get("o") if isinstance(payload, dict) else None
    if not isinstance(offset, int) or offset < 0 or payload.get("f") != _fingerprint(query, bound):
        raise ProblemError(400, _INVALID, code="invalid_page_token")
    return offset


def paginate[T](
    items: Sequence[T], query: ListQuery, *, bound: Mapping[str, Any] | None = None, with_total: bool = True
) -> Page[T]:
    """Cut one page out of a list the server already filtered and ordered.

    Args:
        items: Every matching item, in order.
        query: The list request.
        bound: The list's own parameters that shape ``items``, such as a search term.
        with_total: Report ``total_size``.

    Returns:
        The page, with a ``next_page_token`` unless it is the last.

    Raises:
        ProblemError: 400 ``invalid_page_token`` on a bad token.
    """
    start = decode_page_token(query, bound=bound) + query.skip
    end = start + query.page_size
    next_token = encode_page_token(end, query, bound=bound) if end < len(items) else None
    return Page[T](
        items=list(items[start:end]), next_page_token=next_token, total_size=len(items) if with_total else None
    )


def _field_value(item: Any, field: str) -> Any:
    value = item
    for part in field.split("."):
        value = value.get(part) if isinstance(value, Mapping) else getattr(value, part, None)
    return value


def sort_by_order[T](items: Iterable[T], order_by: Sequence[SortKey]) -> list[T]:
    """Sort mappings or objects by ``order_by``, missing values last in ascending order.

    Args:
        items: Mappings or objects.
        order_by: :attr:`ListQuery.order_by`.

    Returns:
        A new sorted list.
    """
    rows = list(items)
    for key in reversed(order_by):
        field = key.field
        rows.sort(key=lambda row, f=field: (_field_value(row, f) is None, _field_value(row, f)), reverse=key.descending)
    return rows
