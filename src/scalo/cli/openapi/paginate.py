#  Project:   scalo
#  File:      src/scalo/cli/openapi/paginate.py
#  Purpose:   Follow page_token pagination for list commands, with --max-items and --starting-token
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Walk a token-paged list, after the AWS CLI's paginator.

A list that answers :mod:`scalo.api`'s page (``page_token`` in, ``items`` and
``next_page_token`` out) is followed to its last page and printed as one page
holding every item. ``--max-items`` caps the items. When it cuts a list short,
the output's ``next_page_token`` resumes from where it stopped, mid-page
included, through ``--starting-token``.

That resume token wraps the API's own token with how many of its page's items
were already printed, so it stays opaque. A raw ``next_page_token`` from the API
works as a starting token too.

Following stops early, with a warning and a resume token, at an empty page that
still names a next page and at the page cap, so a server that keeps handing out
tokens cannot keep the CLI running for ever.
"""

import base64
import binascii
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import CliUsageError

_RESUME_PREFIX = "r1."

type Fetch = Callable[[str | None], Any]


@dataclass(frozen=True, slots=True)
class StartingToken:
    """Where a list resumes.

    Attributes:
        page_token: The API's page token, ``None`` for the first page.
        skip: Items of that page already returned.
    """

    page_token: str | None
    skip: int = 0


def encode_resume(page_token: str | None, skip: int) -> str:
    """The token ``--starting-token`` resumes from: a page and the items of it already returned."""
    payload = json.dumps({"t": page_token, "s": skip}, separators=(",", ":"))
    return _RESUME_PREFIX + base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_starting(token: str | None) -> StartingToken:
    """Read ``--starting-token``: a resume token this CLI printed, else the API's own page token.

    Raises:
        CliUsageError: On a resume token that does not decode.
    """
    if not token:
        return StartingToken(None)
    if not token.startswith(_RESUME_PREFIX):
        return StartingToken(token)
    encoded = token[len(_RESUME_PREFIX) :]
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (binascii.Error, ValueError) as exc:
        raise CliUsageError(f"--starting-token {token!r} is not a token this CLI printed") from exc
    page_token, skip = (payload.get("t"), payload.get("s")) if isinstance(payload, dict) else (None, None)
    if not (page_token is None or isinstance(page_token, str)) or not isinstance(skip, int) or skip < 0:
        raise CliUsageError(f"--starting-token {token!r} is not a token this CLI printed")
    return StartingToken(page_token, skip)


def is_page(body: Any) -> bool:
    """Whether an answer is a page: a list of ``items`` beside a ``next_page_token`` key."""
    return isinstance(body, Mapping) and isinstance(body.get("items"), list) and "next_page_token" in body


def _result(first: Mapping[str, Any], items: list[Any], resume: str | None) -> dict[str, Any]:
    merged: dict[str, Any] = {"items": items}
    if first.get("total_size") is not None:
        merged["total_size"] = first["total_size"]
    if resume:
        merged["next_page_token"] = resume
    return merged


def single_page(fetch: Fetch, *, starting_token: str | None) -> Any:
    """One page, from ``--starting-token`` when given, as the API answered it."""
    start = decode_starting(starting_token)
    page = fetch(start.page_token)
    if start.skip and is_page(page):
        return {**page, "items": page["items"][start.skip :]}
    return page


def collect(
    fetch: Fetch,
    *,
    max_items: int | None,
    starting_token: str | None,
    warn: Callable[[str], None],
    max_pages: int | None = None,
) -> Any:
    """Every item of a paged list, or the first ``max_items`` of them.

    Args:
        fetch: Calls the list with one page token, ``None`` for the first page.
        max_items: Most items to return, ``None`` for all.
        starting_token: Where to start, from an earlier ``next_page_token``.
        warn: Reports why following stopped short: a token handed back again, an
            empty page that names a next one, or the page cap.
        max_pages: Most pages to fetch, ``None`` for no cap.

    Returns:
        One page holding the items, with a resume ``next_page_token`` when it
        stopped short of the end. An answer that is not a page is returned as is.
    """
    start = decode_starting(starting_token)
    token, skip = start.page_token, start.skip
    items: list[Any] = []
    first: Mapping[str, Any] | None = None
    seen: set[str] = set()
    pages = 0
    while True:
        page = fetch(token)
        pages += 1
        if not is_page(page):
            return page
        first = first or page
        page_items = page["items"][skip:]
        already, skip = skip, 0
        next_token = page.get("next_page_token") or None
        if max_items is not None and len(items) + len(page_items) >= max_items:
            room = max_items - len(items)
            items.extend(page_items[:room])
            if room < len(page_items):
                return _result(first, items, encode_resume(token, already + room))
            return _result(first, items, encode_resume(next_token, 0) if next_token else None)
        items.extend(page_items)
        if next_token is None:
            return _result(first, items, None)
        if next_token == token or next_token in seen:
            warn(f"pagination stopped: the API returned page token {next_token!r} again")
            return _result(first, items, None)
        if not page["items"]:
            warn("pagination stopped at an empty page that names a next one: --starting-token goes on from it")
            return _result(first, items, encode_resume(next_token, 0))
        if max_pages is not None and pages >= max_pages:
            warn(f"pagination stopped after {pages} pages: --starting-token goes on from the next_page_token printed")
            return _result(first, items, encode_resume(next_token, 0))
        seen.add(next_token)
        token = next_token
