#  Project:   scalo
#  File:      src/scalo/api/preconditions.py
#  Purpose:   ETag, If-Match and If-None-Match for optimistic concurrency
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""ETags and the RFC 9110 conditional headers that guard every write (AIP-154).

One ``apply`` (PUT) both creates and updates: ``If-None-Match: *`` creates and
fails when the resource exists, ``If-Match: <etag>`` updates and fails when
someone else wrote first. A write that sends neither is refused with 428::

    @router.put("/{source}", response_model=Source)
    def apply_source(source: str, body: Source, pre: PreconditionHeaders, dry_run: DryRun,
                     response: Response) -> Source:
        pre.check(store.etag(source))          # None when the source does not exist
        ...
        response.headers["ETag"] = etag_of(body)
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import Depends, Header
from pydantic_core import to_jsonable_python

from .problems import ProblemError

ANY = "*"

# An entity-tag, strong or weak, per RFC 9110 section 8.8.3. The opaque part may hold a comma.
_ENTITY_TAG = re.compile(r'\s*(W/)?"([\x21\x23-\x7e\x80-\xff]*)"\s*')
_LIST_ITEM = re.compile(r'\s*(W/)?"([\x21\x23-\x7e\x80-\xff]*)"\s*(?:,|$)')
_OPAQUE = re.compile(r"^[\x21\x23-\x7e\x80-\xff]*$")


@dataclass(frozen=True, slots=True)
class EntityTag:
    """One parsed entity-tag.

    Attributes:
        opaque: The value between the quotes.
        weak: Whether it carried the ``W/`` prefix.
    """

    opaque: str
    weak: bool = False

    def __str__(self) -> str:
        """The entity-tag as a header writes it."""
        return f'{"W/" if self.weak else ""}"{self.opaque}"'


def format_etag(value: str, *, weak: bool = False) -> str:
    """Quote an opaque value, such as a git blob sha, as an entity-tag.

    A value that is already a quoted entity-tag is returned unchanged.

    Args:
        value: The opaque value, or an entity-tag.
        weak: Mark the tag weak.

    Returns:
        The entity-tag, such as ``"3f2a..."``.

    Raises:
        ValueError: When the value holds a double quote, a space or a control character.
    """
    if _ENTITY_TAG.fullmatch(value):
        return value.strip()
    if not _OPAQUE.match(value):
        raise ValueError(f"an entity-tag may not hold quotes, spaces or control characters: {value!r}")
    return str(EntityTag(value, weak=weak))


def etag_of(value: Any) -> str:
    """A strong entity-tag for a representation: the SHA-256 of its bytes.

    Bytes and text are hashed as they are. Anything else, a model or a mapping
    included, is hashed as canonical JSON, so key order does not change the tag.

    Args:
        value: The representation.

    Returns:
        The quoted entity-tag.
    """
    if isinstance(value, bytes | bytearray | memoryview):
        data = bytes(value)
    elif isinstance(value, str):
        data = value.encode("utf-8")
    else:
        canonical = json.dumps(to_jsonable_python(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        data = canonical.encode("utf-8")
    return str(EntityTag(hashlib.sha256(data).hexdigest()))


def parse_etags(header: str) -> Literal["*"] | tuple[EntityTag, ...]:
    """Parse an ``If-Match`` or ``If-None-Match`` value.

    Args:
        header: The header value.

    Returns:
        ``"*"``, or every entity-tag in the list.

    Raises:
        ProblemError: 400 ``invalid_precondition`` on a value that is neither.
    """
    if header.strip() == ANY:
        return ANY
    tags: list[EntityTag] = []
    position = 0
    while position < len(header) or not tags:
        match = _LIST_ITEM.match(header, position)
        if match is None:
            raise ProblemError(400, f"Not an entity-tag list: {header!r}", code="invalid_precondition")
        tags.append(EntityTag(match.group(2), weak=bool(match.group(1))))
        position = match.end()
    return tuple(tags)


def _current_tag(current_etag: str) -> EntityTag:
    parsed = parse_etags(format_etag(current_etag))
    if parsed == ANY or len(parsed) != 1:
        raise ValueError(f"the current ETag must be one entity-tag, not {current_etag!r}")
    return parsed[0]


def check_preconditions(
    current_etag: str | None,
    *,
    if_match: str | None,
    if_none_match: str | None,
    require: bool = True,
) -> None:
    """Evaluate a write's conditional headers against the resource's current ETag.

    If-Match is evaluated first with strong comparison, then If-None-Match with
    weak comparison, as RFC 9110 section 13.2.2 orders them.

    Args:
        current_etag: The resource's current entity-tag or opaque value, ``None``
            when it does not exist.
        if_match: The request's ``If-Match`` value.
        if_none_match: The request's ``If-None-Match`` value.
        require: Refuse a write that sends neither header.

    Raises:
        ProblemError: 412 ``etag_mismatch``, ``resource_missing`` or
            ``resource_exists`` when a condition fails, with the current ``etag``
            when there is one. 428 ``precondition_required`` when ``require``
            and neither header was sent.
    """
    current = None if current_etag is None else _current_tag(current_etag)
    current_text = None if current is None else str(current)

    if if_match is not None:
        wanted = parse_etags(if_match)
        if current is None:
            raise ProblemError(412, "If-Match names a resource that does not exist", code="resource_missing")
        strong_match = wanted == ANY or (
            not current.weak and any(not tag.weak and tag.opaque == current.opaque for tag in wanted)
        )
        if not strong_match:
            raise ProblemError(412, "If-Match does not match the current ETag", code="etag_mismatch", etag=current_text)

    if if_none_match is not None and current is not None:
        unwanted = parse_etags(if_none_match)
        if unwanted == ANY or any(tag.opaque == current.opaque for tag in unwanted):
            raise ProblemError(412, "The resource already exists", code="resource_exists", etag=current_text)

    if require and if_match is None and if_none_match is None:
        if current is None:
            raise ProblemError(428, "Send If-None-Match: * to create the resource", code="precondition_required")
        raise ProblemError(
            428,
            "Send If-Match with the resource's current ETag to change it",
            code="precondition_required",
            etag=current_text,
        )


@dataclass(frozen=True, slots=True)
class Preconditions:
    """A request's conditional headers, checked against the resource's current ETag.

    Attributes:
        if_match: The ``If-Match`` value, if sent.
        if_none_match: The ``If-None-Match`` value, if sent.
    """

    if_match: str | None = None
    if_none_match: str | None = None

    def check(self, current_etag: str | None, *, require: bool = True) -> None:
        """Run :func:`check_preconditions` with these headers."""
        check_preconditions(current_etag, if_match=self.if_match, if_none_match=self.if_none_match, require=require)


def _preconditions(
    if_match: Annotated[
        str | None,
        Header(alias="If-Match", description="The current ETag: the write fails with 412 if it has changed"),
    ] = None,
    if_none_match: Annotated[
        str | None,
        Header(alias="If-None-Match", description="`*` to create: the write fails with 412 if the resource exists"),
    ] = None,
) -> Preconditions:
    return Preconditions(if_match=if_match, if_none_match=if_none_match)


PreconditionHeaders = Annotated[Preconditions, Depends(_preconditions)]
