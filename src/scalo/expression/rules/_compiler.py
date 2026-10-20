# Project:   scalo
# File:      expression/rules/_compiler.py
# Purpose:   Check a rule set spec and build the evaluator from it
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""One pass over the spec collects every finding, then builds the set when none is an error.

Findings keep the order and locations the shared rules corpus pins.
"""

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import cel as _cel

from ..cel import EVALUATION_ERRORS, compile_diagnosed
from ..profile import ProfileConfig, cascade_profile
from ._errors import RuleDiagnostic, error, quoted, warning
from ._fields import COMPOSITE, Found, parse_path
from ._shape import ActionSpec, MatchSpec, RuleSetSpec, RuleSpec

__all__ = [
    "DEFAULT_MAX_LOOKUP_ENTRIES",
    "MAX_TARGETS",
    "AllOf",
    "CelCondition",
    "CompileOptions",
    "CompiledRule",
    "CompiledSet",
    "Copy",
    "FieldSlot",
    "Leaf",
    "Literal",
    "TableLookup",
    "build",
]

MAX_TARGETS = 8
"""The most target fields one set assigns."""

DEFAULT_MAX_LOOKUP_ENTRIES = 100_000
"""Entries one lookup table holds unless the options say otherwise."""

_MAX_ID_LEN = 128
_ID_PUNCTUATION = frozenset("._:/@-")
_VALUE_OPS = frozenset({"equals", "starts_with", "ends_with", "contains", "regex"})


@dataclass(frozen=True, slots=True)
class CompileOptions:
    """What a compile allows.

    Attributes:
        profile: The CEL Fast profile ``when`` conditions compile under. Its
            ``allow_regex`` also decides whether the ``regex`` test is allowed.
        max_lookup_entries: Most entries one lookup table holds.
        metrics: A :class:`~scalo.metrics.MetricsManager`, or anything with its
            ``counter()``, to count ``rules_hits_total`` and ``rules_clamped_total``.
            ``None`` keeps the counts in process only.
    """

    profile: ProfileConfig = field(default_factory=ProfileConfig)
    max_lookup_entries: int = DEFAULT_MAX_LOOKUP_ENTRIES
    metrics: Any = None

    @classmethod
    def from_cascade(cls, metrics: Any = None) -> CompileOptions:
        """Compile under the profile the config cascade sets in ``expression``."""
        return cls(profile=cascade_profile(), metrics=metrics)


@dataclass(frozen=True, slots=True)
class FieldSlot:
    """A path a row reads, and the target it names when it names one."""

    segments: tuple[str, ...]
    target: int | None


@dataclass(frozen=True, slots=True)
class Leaf:
    """A native test on one field."""

    field: int
    test: Callable[[Found], bool]
    negate: bool


@dataclass(frozen=True, slots=True)
class AllOf:
    """Every part holds, then inverted when ``negate`` is set."""

    parts: tuple[Leaf | AllOf, ...]
    negate: bool


@dataclass(frozen=True, slots=True)
class CelCondition:
    """A compiled CEL Fast condition and the top-level names it reads."""

    program: _cel.Program
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Literal:
    """Set this text."""

    value: str


@dataclass(frozen=True, slots=True)
class Copy:
    """Set the text of a field."""

    field: int


@dataclass(frozen=True, slots=True)
class TableLookup:
    """Set a field's text mapped through a lookup table."""

    table: int
    field: int


type Condition = Leaf | AllOf | CelCondition | None
type Action = Literal | Copy | TableLookup


@dataclass(frozen=True, slots=True)
class CompiledRule:
    """One row, ready to evaluate. ``condition`` ``None`` always matches."""

    id: str
    target: int
    condition: Condition
    action: Action


@dataclass(frozen=True, slots=True)
class CompiledSet:
    """An immutable compiled set. ``rules`` are grouped by target, each in declared order."""

    name: str
    targets: tuple[str, ...]
    target_segments: tuple[tuple[str, ...], ...]
    ranges: tuple[range, ...]
    rules: tuple[CompiledRule, ...]
    fields: tuple[FieldSlot, ...]
    tables: tuple[Mapping[str, str], ...]
    warnings: tuple[RuleDiagnostic, ...]


class _Failed:
    """A condition that did not compile, unlike ``None``, which always matches."""


_FAILED = _Failed()

# Patterns run on cel's Rust regex engine, which refuses lookaround and anchors `$` at the very end, unlike `re`.
_REGEX_PROGRAM = _cel.compile("text.matches(pattern)")


def _regex_fault(pattern: str) -> str | None:
    """Why the regex engine refuses ``pattern``, or ``None`` when it accepts it."""
    if not pattern:
        return "is an empty pattern, which matches every position"
    try:
        _REGEX_PROGRAM.execute({"text": "", "pattern": pattern})
    except EVALUATION_ERRORS as e:
        detail = str(e).removeprefix("Function 'matches' error: ")
        detail = detail.removesuffix(" Check function arguments and their types.")
        return f"is not a pattern the regex engine accepts: {detail}"
    return None


def _regex_test(pattern: str) -> Callable[[Found], bool]:
    def test(found: Found) -> bool:
        if not isinstance(found, str):
            return False
        try:
            return _REGEX_PROGRAM.execute({"text": found, "pattern": pattern}) is True
        except EVALUATION_ERRORS:
            return False

    return test


def _exists(found: Found) -> bool:
    if isinstance(found, str):
        return found != ""
    return found is COMPOSITE


def _text_test(op: str, operand: str) -> Callable[[Found], bool]:
    match op:
        case "equals":
            return lambda found: isinstance(found, str) and found == operand
        case "starts_with":
            return lambda found: isinstance(found, str) and found.startswith(operand)
        case "ends_with":
            return lambda found: isinstance(found, str) and found.endswith(operand)
        case _:
            return lambda found: isinstance(found, str) and operand in found


def _id_fault(text: str) -> str | None:
    """Why ``text`` is not a rule id, set name or table name, or ``None`` when it is one."""
    if not text or len(text.encode("utf-8")) > _MAX_ID_LEN:
        return "is not 1 to 128 characters long"
    if not (text[0].isascii() and text[0].isalnum()):
        return "does not start with a letter or digit"
    if not all((ch.isascii() and ch.isalnum()) or ch in _ID_PUNCTUATION for ch in text):
        return "holds a character other than a letter, a digit or one of . _ : / @ -"
    return None


class _Builder:
    """Collects findings while it compiles, so one pass reports them all."""

    def __init__(self, options: CompileOptions) -> None:
        self.options = options
        self.found: list[RuleDiagnostic] = []
        self.fields: list[FieldSlot] = []
        self.field_index: dict[str, int] = {}
        self.target_index: dict[str, int] = {}
        self.table_index: dict[str, int] = {}

    def has_errors(self) -> bool:
        return any(d.is_error for d in self.found)

    def fault(self, location: str, message: str, rule: str | None = None) -> None:
        self.found.append(error(location, message, rule))

    def field(self, rule: str, location: str, text: str) -> int | None:
        """The interned index of ``text``, or ``None`` (with an error) when it is not a path."""
        known = self.field_index.get(text)
        if known is not None:
            return known
        segments = parse_path(text)
        if segments is None:
            self.fault(location, f"{quoted(text)} is not a dotted field path with no empty segment", rule)
            return None
        index = len(self.fields)
        self.fields.append(FieldSlot(segments, self.target_index.get(text)))
        self.field_index[text] = index
        return index

    def build(self, spec: RuleSetSpec) -> CompiledSet | None:
        if (fault := _id_fault(spec.name)) is not None:
            self.fault("name", f"{quoted(spec.name)} {fault}")
        targets = self.targets(spec)
        tables = self.tables(spec)
        compiled: list[CompiledRule] = []
        ids: set[str] = set()
        for index, rule in enumerate(spec.rules):
            if rule.id in ids:
                self.fault(
                    f"rules[{index}].id",
                    f"{quoted(rule.id)} is the id of an earlier row, and ids are unique",
                    rule.id,
                )
            ids.add(rule.id)
            row = self.rule(index, rule)
            if row is not None:
                compiled.append(row)
        if self.has_errors():
            return None
        self.shadow_warnings(spec)

        # Group by target, keeping declared order within each.
        compiled.sort(key=lambda row: row.target)
        ranges: list[range] = []
        start = 0
        for target in range(len(targets)):
            end = start
            while end < len(compiled) and compiled[end].target == target:
                end += 1
            ranges.append(range(start, end))
            start = end
        return CompiledSet(
            name=spec.name,
            targets=tuple(targets),
            target_segments=tuple(parse_path(t) or () for t in targets),
            ranges=tuple(ranges),
            rules=tuple(compiled),
            fields=tuple(self.fields),
            tables=tuple(tables),
            warnings=tuple(d for d in self.found if not d.is_error),
        )

    def targets(self, spec: RuleSetSpec) -> list[str]:
        if not spec.targets and spec.rules:
            self.fault(
                "targets",
                "names no field, so no row has a target. List the fields the set assigns, in evaluation order",
            )
        if len(spec.targets) > MAX_TARGETS:
            self.fault("targets", f"lists {len(spec.targets)} fields, and a set assigns at most {MAX_TARGETS}")
        paths: list[str] = []
        for index, text in enumerate(spec.targets):
            if parse_path(text) is None:
                self.fault(f"targets[{index}]", f"{quoted(text)} is not a dotted field path with no empty segment")
            elif text in self.target_index:
                self.fault(f"targets[{index}]", f"{quoted(text)} is listed twice")
            else:
                self.target_index[text] = len(paths)
                paths.append(text)
        return paths

    def tables(self, spec: RuleSetSpec) -> list[Mapping[str, str]]:
        tables: list[Mapping[str, str]] = []
        for name in sorted(spec.lookups):
            entries = spec.lookups[name]
            location = f"lookups.{name}"
            if (fault := _id_fault(name)) is not None:
                self.fault(location, f"the table name {quoted(name)} {fault}")
            if len(entries) > self.options.max_lookup_entries:
                self.fault(
                    location,
                    f"holds {len(entries)} entries, over the bound of {self.options.max_lookup_entries}",
                )
            if "" in entries:
                self.fault(location, "has an empty key, which no value ever reaches")
            empty = next((key for key in sorted(entries) if entries[key] == ""), None)
            if empty is not None:
                self.fault(location, f"maps {quoted(empty)} to empty text, which reads as no value")
            self.table_index[name] = len(tables)
            tables.append(dict(entries))
        return tables

    def rule(self, index: int, rule: RuleSpec) -> CompiledRule | None:
        rule_id = rule.id
        at = f"rules[{index}]"
        if (fault := _id_fault(rule_id)) is not None:
            self.fault(f"{at}.id", f"{quoted(rule_id)} {fault}", rule_id)
        if len(rule.set) != 1:
            self.fault(f"{at}.set", f"names {len(rule.set)} fields, and a row sets exactly one", rule_id)
            return None
        target_name, action_spec = rule.set[0]
        target = self.target_index.get(target_name)
        if target is None:
            self.fault(f"{at}.set.{target_name}", f"{quoted(target_name)} is not one of the set's targets", rule_id)
        action = self.action(rule_id, f"{at}.set.{target_name}", action_spec)
        condition: Condition | _Failed
        if rule.match is not None and rule.when is not None:
            self.fault(at, "has both `match` and `when`, and a row takes one", rule_id)
            condition = _FAILED
        elif rule.match is not None:
            condition = self.matcher(rule_id, f"{at}.match", rule.match)
        elif rule.when is not None:
            condition = self.when(rule_id, f"{at}.when", rule.when)
        else:
            condition = None
        if target is None or action is None or isinstance(condition, _Failed):
            return None
        return CompiledRule(id=rule_id, target=target, condition=condition, action=action)

    def action(self, rule: str, at: str, spec: ActionSpec) -> Action | None:
        value, source, table = spec.value, spec.source, spec.lookup
        if value is not None and source is None and table is None:
            if not value:
                self.fault(f"{at}.value", "is empty text, which reads as no value", rule)
                return None
            return Literal(value)
        if value is None and source is not None and table is None:
            field = self.field(rule, f"{at}.from", source)
            return None if field is None else Copy(field)
        if value is None and source is not None and table is not None:
            field = self.field(rule, f"{at}.from", source)
            table_index = self.table_index.get(table)
            if table_index is None:
                self.fault(f"{at}.lookup", f"{quoted(table)} names no table in `lookups`", rule)
            if field is None or table_index is None:
                return None
            return TableLookup(table=table_index, field=field)
        if value is None and source is None and table is not None:
            self.fault(at, "`lookup` needs `from`, the field whose text it maps", rule)
        elif value is None and source is None:
            self.fault(at, "sets nothing: give `value`, `from`, or `lookup` with `from`", rule)
        else:
            self.fault(at, "has `value` beside `from` or `lookup`, so give one", rule)
        return None

    def when(self, rule: str, at: str, text: str) -> CelCondition | _Failed:
        program, found = compile_diagnosed(text, self.options.profile)
        if program is None:
            for diagnostic in found:
                self.found.append(error(at, diagnostic.message, rule, diagnostic.span))
            return _FAILED
        return CelCondition(program=program, names=tuple(program.variables()))

    def matcher(self, rule: str, at: str, spec: MatchSpec) -> Leaf | AllOf | _Failed:
        if spec.all:
            own = (
                ("field", spec.field),
                ("op", spec.op),
                ("value", spec.value),
                ("prefix", spec.prefix),
                ("suffix", spec.suffix),
                ("min", spec.min),
                ("max", spec.max),
            )
            for key, given in own:
                if given is not None:
                    self.fault(f"{at}.{key}", "does not apply beside `all`", rule)
            parts = [self.matcher(rule, f"{at}.all[{i}]", part) for i, part in enumerate(spec.all)]
            built = [part for part in parts if not isinstance(part, _Failed)]
            if len(built) != len(parts):
                return _FAILED
            return AllOf(parts=tuple(built), negate=spec.negate)
        if spec.field is None or spec.op is None:
            self.fault(at, "needs `field` and `op`, or `all`", rule)
            return _FAILED
        field = self.field(rule, f"{at}.field", spec.field)
        test = self.test(rule, at, spec.op, spec)
        if field is None or test is None:
            return _FAILED
        return Leaf(field=field, test=test, negate=spec.negate)

    def test(self, rule: str, at: str, op: str, spec: MatchSpec) -> Callable[[Found], bool] | None:
        if op in _VALUE_OPS:
            wants: tuple[str, ...] = ("value",)
        elif op == "prefix_and_suffix":
            wants = ("prefix", "suffix")
        elif op == "length":
            wants = ("min", "max")
        else:
            wants = ()
        given = (
            ("value", spec.value),
            ("prefix", spec.prefix),
            ("suffix", spec.suffix),
            ("min", spec.min),
            ("max", spec.max),
        )
        stray = False
        for key, value in given:
            if value is not None and key not in wants:
                self.fault(f"{at}.{key}", f"does not apply to `{op}`", rule)
                stray = True
        if wants == ("value",) and spec.value is None:
            self.fault(f"{at}.value", f"`{op}` needs `value`", rule)
            return None
        test: Callable[[Found], bool] | None
        match op:
            case "prefix_and_suffix":
                test = self.prefix_and_suffix(rule, at, spec.prefix, spec.suffix)
            case "length":
                test = self.length(rule, at, spec.min, spec.max)
            case "exists":
                test = _exists
            case "regex":
                test = self.regex(rule, at, spec.value)
            case _:
                test = _text_test(op, spec.value or "")
        return None if stray else test

    def prefix_and_suffix(
        self, rule: str, at: str, prefix: str | None, suffix: str | None
    ) -> Callable[[Found], bool] | None:
        if prefix is None or suffix is None:
            self.fault(at, "`prefix_and_suffix` needs both `prefix` and `suffix`", rule)
            return None
        return lambda found: isinstance(found, str) and found.startswith(prefix) and found.endswith(suffix)

    def length(self, rule: str, at: str, low: int | None, high: int | None) -> Callable[[Found], bool] | None:
        if low is None and high is None:
            self.fault(at, "`length` needs `min`, `max` or both", rule)
            return None
        if low is not None and high is not None and low > high:
            self.fault(f"{at}.min", f"{low} is over max {high}", rule)
            return None
        least = low or 0
        most = sys.maxsize if high is None else high
        return lambda found: isinstance(found, str) and least <= len(found) <= most

    def regex(self, rule: str, at: str, pattern: str | None) -> Callable[[Found], bool] | None:
        if pattern is None:
            return None
        if not self.options.profile.allow_regex:
            self.fault(
                f"{at}.op",
                "`regex` is off in the CEL Fast profile, as regex has unbounded cost per record. "
                "Use starts_with, ends_with or contains, or set allow_regex: true in expression config",
                rule,
            )
            return None
        if (fault := _regex_fault(pattern)) is not None:
            self.fault(f"{at}.value", fault, rule)
            return None
        return _regex_test(pattern)

    def shadow_warnings(self, spec: RuleSetSpec) -> None:
        """Warn on each row an earlier row of the same target always fires before."""
        by_target: dict[str, list[int]] = {}
        for index, rule in enumerate(spec.rules):
            if rule.set:
                by_target.setdefault(rule.set[0][0], []).append(index)
        for target in sorted(by_target):
            rows = by_target[target]
            for k, j in enumerate(rows):
                later = spec.rules[j]
                earlier = next((spec.rules[i] for i in rows[:k] if _shadows(spec.rules[i], later)), None)
                if earlier is not None:
                    self.found.append(
                        warning(
                            f"rules[{j}]",
                            f"never fires: row {quoted(earlier.id)} sets a literal value and matches every "
                            "record this one does, so it always fires first",
                            later.id,
                        )
                    )


def _shadows(earlier: RuleSpec, later: RuleSpec) -> bool:
    """True when ``earlier`` fires on every record ``later`` matches.

    Only a literal ``value`` always resolves, as ``from`` and ``lookup`` can miss and fall
    through.
    """
    if not earlier.set or earlier.set[0][1].value is None:
        return False
    if earlier.match is None and earlier.when is None:
        return True
    if earlier.match is None:
        return later.match is None and later.when is not None and later.when.strip() == (earlier.when or "").strip()
    if earlier.when is None:
        if later.when is not None or later.match is None:
            return False
        if later.match == earlier.match:
            return True
        field = _exists_field(earlier.match)
        return field is not None and _needs_text(later.match, field)
    return False


def _exists_field(spec: MatchSpec) -> str | None:
    """The field of a plain, un-negated ``exists`` test."""
    if not spec.all and not spec.negate and spec.op == "exists":
        return spec.field
    return None


def _needs_text(spec: MatchSpec, field: str) -> bool:
    """True when ``spec`` can only hold where ``field`` holds non-empty text or a value."""
    if spec.negate:
        return False
    if spec.all:
        return any(_needs_text(part, field) for part in spec.all)
    if spec.field != field:
        return False
    match spec.op:
        case "exists":
            return True
        case "equals" | "starts_with" | "ends_with" | "contains":
            return bool(spec.value)
        case "prefix_and_suffix":
            return bool(spec.prefix) or bool(spec.suffix)
        case "length":
            return spec.min is not None and spec.min >= 1
        case _:
            return False


def build(spec: RuleSetSpec, options: CompileOptions) -> tuple[CompiledSet | None, list[RuleDiagnostic]]:
    """Compile ``spec`` under ``options``.

    Returns:
        ``(compiled, findings)``. ``compiled`` is ``None`` when any finding is an error.
    """
    builder = _Builder(options)
    compiled = builder.build(spec)
    if builder.has_errors():
        return None, builder.found
    return compiled, builder.found
