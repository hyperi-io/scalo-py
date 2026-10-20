# Project:   scalo
# File:      expression/rules/_shape.py
# Purpose:   Read a rule set mapping into typed specs, refusing a malformed one
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""The rule set as an operator writes it, read from a parsed YAML or JSON mapping.

Every key and type is checked here, so the compiler only sees well-formed specs. A key
the format does not have is refused rather than ignored, so a misspelt key cannot
silently drop a test.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeIs

from ._errors import RuleDiagnostic, error

__all__ = [
    "DEFAULT_RULE_SET_NAME",
    "MATCH_OPS",
    "ActionSpec",
    "MatchSpec",
    "RuleSetSpec",
    "RuleSpec",
    "read_rule_set",
]

DEFAULT_RULE_SET_NAME = "rules"
"""The metric label and log name a rule set takes when it names none."""

MATCH_OPS: frozenset[str] = frozenset(
    {"equals", "starts_with", "ends_with", "contains", "prefix_and_suffix", "length", "exists", "regex"}
)
"""The native tests a ``match`` names in ``op``."""

_SET_KEYS = ("name", "targets", "lookups", "rules")
_RULE_KEYS = ("id", "match", "when", "set")
_MATCH_KEYS = ("field", "op", "value", "prefix", "suffix", "min", "max", "negate", "all")
_ACTION_KEYS = ("value", "from", "lookup")


@dataclass(frozen=True, slots=True)
class MatchSpec:
    """A native test against one field, or ``all`` of several."""

    field: str | None = None
    op: str | None = None
    value: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    min: int | None = None
    max: int | None = None
    negate: bool = False
    all: tuple[MatchSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """How a matching row finds the value it sets."""

    value: str | None = None
    source: str | None = None
    lookup: str | None = None


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """One row. ``set`` lists its target entries sorted by field name."""

    id: str
    set: tuple[tuple[str, ActionSpec], ...]
    match: MatchSpec | None = None
    when: str | None = None


@dataclass(frozen=True, slots=True)
class RuleSetSpec:
    """An ordered rule set. Each table in ``lookups`` maps text to text."""

    name: str = DEFAULT_RULE_SET_NAME
    targets: tuple[str, ...] = ()
    lookups: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    rules: tuple[RuleSpec, ...] = ()


class _Reader:
    """Collects every shape fault in one pass."""

    def __init__(self) -> None:
        self.found: list[RuleDiagnostic] = []

    def fault(self, location: str, message: str, rule: str | None = None) -> None:
        self.found.append(error(location, message, rule))

    def mapping(self, raw: object, location: str, what: str, rule: str | None = None) -> Mapping[str, Any] | None:
        if isinstance(raw, Mapping):
            return raw
        self.fault(location, f"is not a mapping, and {what} is one", rule)
        return None

    def keys(self, raw: Mapping[str, Any], allowed: tuple[str, ...], at: str, rule: str | None = None) -> None:
        for key in raw:
            if key not in allowed:
                self.fault(_join(at, str(key)), f"is not a key here: give {', '.join(allowed)}", rule)

    def text(self, raw: Mapping[str, Any], key: str, at: str, rule: str | None = None) -> str | None:
        """An optional text value: absent and null both read as unset."""
        value = raw.get(key)
        if value is None or isinstance(value, str):
            return value
        self.fault(_join(at, key), f"is {_kind(value)}, and it takes text", rule)
        return None

    def count(self, raw: Mapping[str, Any], key: str, at: str, rule: str | None) -> int | None:
        value = raw.get(key)
        if value is None:
            return None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        self.fault(_join(at, key), f"is {_kind(value)}, and it takes a whole number from 0", rule)
        return None

    def read(self, raw: object) -> RuleSetSpec | None:
        top = self.mapping(raw, "", "a rule set")
        if top is None:
            return None
        self.keys(top, _SET_KEYS, "")
        name = top.get("name", DEFAULT_RULE_SET_NAME)
        if not isinstance(name, str):
            self.fault("name", f"is {_kind(name)}, and it takes text")
            name = DEFAULT_RULE_SET_NAME
        targets = self.targets(top.get("targets", []))
        lookups = self.lookups(top.get("lookups", {}))
        rules = self.rules(top.get("rules", []))
        return RuleSetSpec(name=name, targets=targets, lookups=lookups, rules=rules)

    def targets(self, raw: object) -> tuple[str, ...]:
        if not _is_list(raw):
            self.fault("targets", f"is {_kind(raw)}, and it takes a list of field paths")
            return ()
        names: list[str] = []
        for index, item in enumerate(raw):
            if isinstance(item, str):
                names.append(item)
            else:
                self.fault(f"targets[{index}]", f"is {_kind(item)}, and it takes a field path")
        return tuple(names)

    def lookups(self, raw: object) -> dict[str, dict[str, str]]:
        tables = self.mapping(raw, "lookups", "lookups")
        if tables is None:
            return {}
        read: dict[str, dict[str, str]] = {}
        for name, entries in tables.items():
            at = f"lookups.{name}"
            if not isinstance(name, str):
                self.fault("lookups", f"has the table name {name!r}, which is not text")
                continue
            table = self.mapping(entries, at, "a lookup table")
            if table is None:
                continue
            read[name] = {}
            for key, value in table.items():
                if isinstance(key, str) and isinstance(value, str):
                    read[name][key] = value
                else:
                    self.fault(at, f"maps {key!r} to {value!r}, and a table maps text to text")
        return read

    def rules(self, raw: object) -> tuple[RuleSpec, ...]:
        if not _is_list(raw):
            self.fault("rules", f"is {_kind(raw)}, and it takes a list of rows")
            return ()
        rows: list[RuleSpec] = []
        for index, item in enumerate(raw):
            row = self.rule(item, f"rules[{index}]")
            if row is not None:
                rows.append(row)
        return tuple(rows)

    def rule(self, raw: object, at: str) -> RuleSpec | None:
        row = self.mapping(raw, at, "a row")
        if row is None:
            return None
        rule_id = row.get("id")
        if not isinstance(rule_id, str):
            self.fault(f"{at}.id", "is missing, and every row has a text id" if rule_id is None else "is not text")
            rule_id = ""
        rule = rule_id or None
        self.keys(row, _RULE_KEYS, at, rule)
        match = None
        if row.get("match") is not None:
            match = self.match(row["match"], f"{at}.match", rule)
        when = self.text(row, "when", at, rule)
        targets: Mapping[str, Any] | None = None
        if row.get("set") is None:
            self.fault(f"{at}.set", "is missing, and every row sets one target", rule)
        else:
            targets = self.mapping(row["set"], f"{at}.set", "set", rule)
        entries: list[tuple[str, ActionSpec]] = []
        for target, action in (targets or {}).items():
            spec = self.action(action, f"{at}.set.{target}", rule)
            if spec is not None:
                entries.append((str(target), spec))
        return RuleSpec(id=rule_id, set=tuple(sorted(entries, key=lambda e: e[0])), match=match, when=when)

    def match(self, raw: object, at: str, rule: str | None) -> MatchSpec | None:
        spec = self.mapping(raw, at, "match", rule)
        if spec is None:
            return None
        self.keys(spec, _MATCH_KEYS, at, rule)
        op = self.text(spec, "op", at, rule)
        if op is not None and op not in MATCH_OPS:
            self.fault(f"{at}.op", f"{op!r} is not a test: give one of {', '.join(sorted(MATCH_OPS))}", rule)
            op = None
        negate = spec.get("negate", False)
        if not isinstance(negate, bool):
            self.fault(f"{at}.negate", f"is {_kind(negate)}, and it takes true or false", rule)
            negate = False
        parts: list[MatchSpec] = []
        raw_all = spec.get("all", [])
        if not _is_list(raw_all):
            self.fault(f"{at}.all", f"is {_kind(raw_all)}, and it takes a list of tests", rule)
            raw_all = []
        for index, part in enumerate(raw_all):
            read = self.match(part, f"{at}.all[{index}]", rule)
            if read is not None:
                parts.append(read)
        return MatchSpec(
            field=self.text(spec, "field", at, rule),
            op=op,
            value=self.text(spec, "value", at, rule),
            prefix=self.text(spec, "prefix", at, rule),
            suffix=self.text(spec, "suffix", at, rule),
            min=self.count(spec, "min", at, rule),
            max=self.count(spec, "max", at, rule),
            negate=negate,
            all=tuple(parts),
        )

    def action(self, raw: object, at: str, rule: str | None) -> ActionSpec | None:
        action = self.mapping(raw, at, "an action", rule)
        if action is None:
            return None
        self.keys(action, _ACTION_KEYS, at, rule)
        return ActionSpec(
            value=self.text(action, "value", at, rule),
            source=self.text(action, "from", at, rule),
            lookup=self.text(action, "lookup", at, rule),
        )


def _join(at: str, key: str) -> str:
    return f"{at}.{key}" if at else key


def _is_list(raw: object) -> TypeIs[Sequence[Any]]:
    return isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))


def _kind(value: object) -> str:
    """Name a JSON value's kind for a message."""
    match value:
        case None:
            return "null"
        case bool():
            return "a boolean"
        case int() | float():
            return "a number"
        case str():
            return "text"
        case Mapping():
            return "a mapping"
        case _ if _is_list(value):
            return "a list"
        case _:
            return f"a {type(value).__name__}"


def read_rule_set(raw: object) -> tuple[RuleSetSpec | None, list[RuleDiagnostic]]:
    """Read a rule set mapping into specs.

    Args:
        raw: The parsed rule set: a mapping with ``name``, ``targets``, ``lookups`` and
            ``rules``, each optional.

    Returns:
        ``(spec, [])`` for a well-formed set, else ``(None, faults)``.
    """
    reader = _Reader()
    spec = reader.read(raw)
    if reader.found:
        return None, reader.found
    return spec, []
