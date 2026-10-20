# Project:   scalo
# File:      expression/rules/_fields.py
# Purpose:   How a rule set reads the fields of a record
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""A record is a parsed JSON object. A dotted path reaches into objects, not arrays.

A read gives the field's text, or one of three markers for a field with none: missing,
null, or an object or array.
"""

from collections.abc import Mapping, Sequence
from typing import Final

__all__ = ["COMPOSITE", "MISSING", "NULL", "Found", "parse_path", "present_text", "read_path"]


class _Marker:
    """A field that holds no text."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name


MISSING: Final = _Marker("MISSING")
NULL: Final = _Marker("NULL")
COMPOSITE: Final = _Marker("COMPOSITE")

type Found = str | _Marker
"""What a record holds at a path: its text, or a marker."""


def parse_path(text: str) -> tuple[str, ...] | None:
    """Split a dotted path, or return ``None`` when it is empty or has an empty segment."""
    segments = tuple(text.split("."))
    if not text or "" in segments:
        return None
    return segments


def _text(value: object) -> Found:
    """The text a JSON value reads as: a string as written, a number or boolean as JSON text."""
    if value is None:
        return NULL
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return COMPOSITE


def read_path(record: object, segments: tuple[str, ...]) -> Found:
    """Return what ``record`` holds at the path ``segments``."""
    node = record
    for segment in segments:
        if not isinstance(node, Mapping):
            return MISSING
        node = node.get(segment, MISSING)
        if node is MISSING:
            return MISSING
    if isinstance(node, Mapping) or (isinstance(node, Sequence) and not isinstance(node, str)):
        return COMPOSITE
    return _text(node)


def present_text(found: Found) -> str | None:
    """The text, when it is non-empty: what ``exists`` accepts and an action copies."""
    if isinstance(found, str) and found:
        return found
    return None
