#  Project:   scalo
#  File:      src/scalo/api/params.py
#  Purpose:   The dry_run and view query parameters every API shares
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Query parameters with one name and one meaning across every API.

``dry_run`` (AIP-163) goes on every mutation: the handler validates and reports
the change it would make, the ETag it would write included, and commits
nothing. ``view`` (AIP-157) chooses how much of a resource comes back::

    def apply_source(source: str, body: Source, dry_run: DryRun) -> ApplyResult: ...
    def list_sources(query: ListParams, view: ListView) -> Page[Source]: ...
"""

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Query


def _dry_run(
    dry_run: Annotated[bool, Query(description="Validate and report the change without committing it")] = False,
) -> bool:
    return dry_run


DryRun = Annotated[bool, Depends(_dry_run)]


class View(StrEnum):
    """How much of a resource a read returns."""

    BASIC = "basic"
    FULL = "full"


_VIEW_DESCRIPTION = "basic: the fields a listing needs. full: every field."


def _basic_view(view: Annotated[View, Query(description=_VIEW_DESCRIPTION)] = View.BASIC) -> View:
    return view


def _full_view(view: Annotated[View, Query(description=_VIEW_DESCRIPTION)] = View.FULL) -> View:
    return view


# AIP-157 defaults a List to BASIC. A Get defaults to FULL here so it returns the whole resource.
ListView = Annotated[View, Depends(_basic_view)]
GetView = Annotated[View, Depends(_full_view)]
