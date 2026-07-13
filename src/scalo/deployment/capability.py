# Project:   scalo
# File:      deployment/capability.py
# Purpose:   Capability-catalog types for reflectable config (scalo-py#3)
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Capability-catalog types (Python side of the reflectable-config contract).

A derived JSON Schema (via pydantic ``model_json_schema``) describes the typed
``Config`` shape, but it cannot describe runtime DATA -- service names and the
knobs each reads ad-hoc. The capability catalog fills that gap: scalo defines
the catalog TYPES; each app fills the CONTENT.

This shape is the Python mirror of the Rust ``scalo::deployment::Capability``
family and MUST serialise to the SAME JSON shape so dfe-engine reflects on
Rust- and Python-produced contracts through one code path. The cross-language
SSoT is ``docs/reflectable-config-shape.md`` in scalo-rs. Tracks scalo-py#3 /
scalo-rs#6.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer


class FieldType(StrEnum):
    """The type of a :class:`FieldSpec` (serialised lower-snake-case)."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    SECRET = "secret"  # noqa: S105 - a FieldType name, not a credential
    ENUM = "enum"
    DURATION = "duration"
    LIST = "list"
    MAP = "map"
    OBJECT = "object"


class FieldSpec(BaseModel):
    """A single config field within a :class:`Capability`.

    Serialises to the Rust ``FieldSpec`` shape: ``name``/``type``/``required``
    always present; ``default``/``secret``/``enum_values``/``example`` omitted
    when empty/absent (``secret`` omitted when false).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: FieldType = FieldType.STRING
    required: bool = False
    default: Any | None = None
    description: str = ""
    secret: bool = False
    enum_values: list[str] = Field(default_factory=list)
    example: Any | None = None

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "type": self.type.value,
            "required": self.required,
        }
        if self.default is not None:
            out["default"] = self.default
        out["description"] = self.description
        if self.secret:
            out["secret"] = self.secret
        if self.enum_values:
            out["enum_values"] = self.enum_values
        if self.example is not None:
            out["example"] = self.example
        return out

    # ---- Convenience constructors (mirror the Rust builders) ---------------

    @classmethod
    def string(cls, name: str, **kw: Any) -> FieldSpec:
        return cls(name=name, type=FieldType.STRING, **kw)

    @classmethod
    def integer(cls, name: str, **kw: Any) -> FieldSpec:
        return cls(name=name, type=FieldType.INT, **kw)

    @classmethod
    def boolean(cls, name: str, **kw: Any) -> FieldSpec:
        return cls(name=name, type=FieldType.BOOL, **kw)

    @classmethod
    def secret_field(cls, name: str, **kw: Any) -> FieldSpec:
        return cls(name=name, type=FieldType.SECRET, secret=True, **kw)

    @classmethod
    def enumeration(cls, name: str, values: list[str], **kw: Any) -> FieldSpec:
        return cls(name=name, type=FieldType.ENUM, enum_values=list(values), **kw)


class Capability(BaseModel):
    """One node in the capability catalog.

    Serialises to the Rust ``Capability`` shape: ``kind``/``name``/
    ``description`` always present; ``maturity``/``fields``/``children`` omitted
    when empty.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    description: str = ""
    maturity: str | None = None
    fields: list[FieldSpec] = Field(default_factory=list)
    children: list[Capability] = Field(default_factory=list)

    @model_serializer
    def _serialize(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
        }
        if self.maturity is not None:
            out["maturity"] = self.maturity
        if self.fields:
            out["fields"] = [f.model_dump() for f in self.fields]
        if self.children:
            out["children"] = [c.model_dump() for c in self.children]
        return out

    # ---- Convenience constructors ------------------------------------------

    @classmethod
    def source(cls, name: str, **kw: Any) -> Capability:
        return cls(kind="source", name=name, **kw)

    @classmethod
    def service(cls, name: str, **kw: Any) -> Capability:
        return cls(kind="service", name=name, **kw)

    @classmethod
    def transport(cls, name: str, **kw: Any) -> Capability:
        return cls(kind="transport", name=name, **kw)


Capability.model_rebuild()


__all__ = ["Capability", "FieldSpec", "FieldType"]
