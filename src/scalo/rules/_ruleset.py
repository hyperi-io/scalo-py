# Project:   scalo
# File:      rules/_ruleset.py
# Purpose:   A compiled rule set: evaluate records, clamp a target, count hits
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""One pass per record: each target in order, its rows in declared order.

The first row that matches and resolves a value sets the target. A row whose ``from`` or
``lookup`` finds nothing does not match, so the next row is tried. A row for a later
target reads an earlier target's new value. The clamp runs last.
"""

import threading
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import yaml

from scalo._yaml import safe_load
from scalo.expression.cel import EVALUATION_ERRORS

from ._compiler import (
    AllOf,
    CelCondition,
    CompiledSet,
    CompileOptions,
    Condition,
    Copy,
    Leaf,
    Literal,
    TableLookup,
    build,
)
from ._errors import RuleDiagnostic, RulesError, RulesLoadError
from ._fields import Found, present_text, read_path
from ._shape import read_rule_set

__all__ = [
    "RECORD_LABEL",
    "Assignment",
    "Batch",
    "Clamp",
    "ClampOutcome",
    "ClampResult",
    "Outcome",
    "RuleSet",
    "RuleUsage",
]

RECORD_LABEL = "(record)"
"""The ``rule`` label of a clamp on a value the record carried. Never a valid rule id."""

_ABSENT = object()


@dataclass(frozen=True, slots=True)
class Assignment:
    """The value a target ends with, and the row that set it.

    Attributes:
        value: The value to write into the target field.
        rule: The id of the row that set it, ``None`` when the clamp's default replaced it.
    """

    value: str
    rule: str | None


class ClampOutcome(StrEnum):
    """What the clamp did to its target."""

    KEPT = "kept"
    REPLACED = "replaced"
    DEFAULTED = "defaulted"


@dataclass(frozen=True, slots=True)
class ClampResult:
    """What the clamp did, and to what.

    Attributes:
        outcome: Kept, replaced or defaulted.
        was: The value refused, for ``REPLACED``.
        rule: The id of the row that set the refused value, ``None`` when the record
            carried it.
    """

    outcome: ClampOutcome
    was: str | None = None
    rule: str | None = None


@dataclass(frozen=True, slots=True)
class Clamp:
    """Hold one target to an allowed set, per call.

    The caller keeps ``default`` inside ``allowed``, as the clamp does not check it.

    Attributes:
        target: The target field held.
        allowed: The values it may end with.
        default: What it takes otherwise.
    """

    target: str
    allowed: Collection[str]
    default: str


@dataclass(frozen=True, slots=True)
class RuleUsage:
    """One row's counts since the set compiled.

    Attributes:
        rule: The row's id.
        target: The target field it sets.
        hits: Records it set the target on.
        clamped: Of those, records whose value the clamp replaced.
    """

    rule: str
    target: str
    hits: int
    clamped: int


class Outcome:
    """The values one record's targets end with, in target order.

    Attributes:
        clamp: What the clamp did, ``None`` when the call had no clamp.
    """

    __slots__ = ("_assigned", "_clamped", "_fired", "_targets", "clamp")

    def __init__(
        self,
        targets: tuple[str, ...],
        assigned: list[Assignment | None],
        fired: list[int | None],
        clamp: ClampResult | None,
        clamped: int | None,
    ) -> None:
        self._targets = targets
        self._assigned = assigned
        self._fired = fired
        self._clamped = clamped
        self.clamp = clamp

    def get(self, target: str) -> Assignment | None:
        """Return the assignment to ``target``.

        ``None`` when no row set it and the clamp left the record's own value, or when the
        set has no such target.
        """
        try:
            return self._assigned[self._targets.index(target)]
        except ValueError:
            return None

    def value(self, target: str) -> str | None:
        """Return the value assigned to ``target``, ``None`` when none was."""
        assigned = self.get(target)
        return None if assigned is None else assigned.value

    def __iter__(self) -> Iterator[tuple[str, Assignment]]:
        """Each assigned target field with its assignment, in evaluation order."""
        for target, assigned in zip(self._targets, self._assigned, strict=True):
            if assigned is not None:
                yield target, assigned

    def __len__(self) -> int:
        return sum(assigned is not None for assigned in self._assigned)

    def __repr__(self) -> str:
        return f"Outcome({dict(self)!r}, clamp={self.clamp!r})"


class _Usage:
    """In-process counts per row, and the ``rules_*_total`` series when metrics are on."""

    __slots__ = ("clamp_series", "clamped", "hit_series", "hits", "lock")

    def __init__(self, name: str, ids: list[str], metrics: Any) -> None:
        self.hits = [0] * len(ids)
        # One per row, then one for values the record carried.
        self.clamped = [0] * (len(ids) + 1)
        self.lock = threading.Lock()
        self.hit_series: list[Any] = []
        self.clamp_series: list[Any] = []
        if metrics is not None:
            hits = metrics.counter("rules_hits_total", "Records a rule set its target on", labels=["rule_set", "rule"])
            clamped = metrics.counter(
                "rules_clamped_total", "Rule values the clamp replaced", labels=["rule_set", "rule"]
            )
            self.hit_series = [hits.labels(rule_set=name, rule=rule) for rule in ids]
            self.clamp_series = [clamped.labels(rule_set=name, rule=rule) for rule in [*ids, RECORD_LABEL]]

    def record(self, outcome: Outcome) -> None:
        """Count one outcome."""
        rows, slot = _counts(outcome, len(self.hits))
        with self.lock:
            for index in rows:
                self.hits[index] += 1
            if slot is not None:
                self.clamped[slot] += 1
        if self.hit_series:
            for index in rows:
                self.hit_series[index].inc()
            if slot is not None:
                self.clamp_series[slot].inc()

    def add(self, hits: list[int], clamped: list[int]) -> None:
        """Add per-row hit counts and per-slot clamp counts."""
        with self.lock:
            for index, count in enumerate(hits):
                self.hits[index] += count
            for index, count in enumerate(clamped):
                self.clamped[index] += count
        if self.hit_series:
            for index, count in enumerate(hits):
                if count:
                    self.hit_series[index].inc(count)
            for index, count in enumerate(clamped):
                if count:
                    self.clamp_series[index].inc(count)


def _counts(outcome: Outcome, rules: int) -> tuple[list[int], int | None]:
    """The rows one outcome counts a hit on, and the clamp slot it counts, if any.

    A replaced value counts a hit on the row that produced it, as that row did fire.
    """
    rows = [index for index in outcome._fired if index is not None]
    slot = outcome._clamped
    if slot is not None and slot < rules:
        rows.append(slot)
    return rows, slot


class Batch:
    """Counts a batch of evaluations locally and adds them to the set once.

    The counts reach the set at :meth:`flush` or when the ``with`` block ends, so threads
    evaluating in parallel share no counter per record.
    """

    __slots__ = ("_clamped", "_hits", "_set")

    def __init__(self, rules: RuleSet) -> None:
        self._set = rules
        self._hits = [0] * len(rules)
        self._clamped = [0] * (len(rules) + 1)

    def evaluate(self, record: Mapping[str, Any], clamp: Clamp | None = None) -> Outcome:
        """Return :meth:`RuleSet.evaluate`'s outcome, counted into this batch."""
        outcome = self._set._run(record, clamp)
        rows, slot = _counts(outcome, len(self._hits))
        for index in rows:
            self._hits[index] += 1
        if slot is not None:
            self._clamped[slot] += 1
        return outcome

    def flush(self) -> None:
        """Add the counts so far to the set's counters and start again from zero."""
        self._set._usage.add(self._hits, self._clamped)
        self._hits = [0] * len(self._hits)
        self._clamped = [0] * len(self._clamped)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.flush()


class RuleSet:
    """A compiled, immutable rule set: per target, the first matching row sets it.

    Build one with :meth:`compile`, check a config with :meth:`check`, and evaluate
    records with :meth:`evaluate`. A set is safe to share between threads.
    """

    __slots__ = ("_set", "_usage")

    def __init__(self, compiled: CompiledSet, options: CompileOptions) -> None:
        self._set = compiled
        self._usage = _Usage(compiled.name, [rule.id for rule in compiled.rules], options.metrics)

    @classmethod
    def compile(cls, config: Mapping[str, Any], options: CompileOptions | None = None) -> RuleSet:
        """Compile a rule set from its parsed config.

        Args:
            config: The rule set as parsed YAML or JSON: ``name``, ``targets``,
                ``lookups`` and ``rules``.
            options: What the compile allows. ``None`` compiles under the profile the
                config cascade sets in ``expression``.

        Returns:
            The compiled set. :attr:`warnings` holds any rows that never fire.

        Raises:
            RulesError: The config has an error. ``diagnostics`` lists every finding.
        """
        options = options if options is not None else CompileOptions.from_cascade()
        spec, faults = read_rule_set(config)
        if spec is None:
            raise RulesError(faults)
        compiled, found = build(spec, options)
        if compiled is None:
            raise RulesError(found)
        return cls(compiled, options)

    @classmethod
    def check(cls, config: Mapping[str, Any], options: CompileOptions | None = None) -> list[RuleDiagnostic]:
        """Return every finding in ``config``, without building a set.

        Warnings are looked for once there is no error. A malformed config reports its
        shape faults and nothing else.

        Args:
            config: The rule set as parsed YAML or JSON.
            options: What the compile allows. ``None`` uses the cascade's profile.

        Returns:
            Every finding, empty when the set compiles clean.
        """
        options = options if options is not None else CompileOptions.from_cascade()
        spec, faults = read_rule_set(config)
        if spec is None:
            return faults
        return build(spec, options)[1]

    @classmethod
    def from_file_section(cls, path: str | Path, key: str, options: CompileOptions | None = None) -> RuleSet:
        """Compile the rule set at dotted ``key`` of the YAML file at ``path``.

        Args:
            path: The YAML file.
            key: Dotted path to the section, e.g. ``routing.rules``.
            options: What the compile allows. ``None`` uses the cascade's profile.

        Returns:
            The compiled set.

        Raises:
            RulesLoadError: The file cannot be read or parsed, or holds nothing at ``key``.
            RulesError: The section does not compile.
        """
        origin = f"{path} at {key}"
        try:
            document = safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            raise RulesLoadError(origin, str(e)) from e
        section: Any = document
        for part in key.split("."):
            if not isinstance(section, Mapping) or part not in section:
                raise RulesLoadError(origin, "the file has no such section")
            section = section[part]
        return cls.compile(section, options)

    @property
    def name(self) -> str:
        """The ``rule_set`` metric label."""
        return self._set.name

    @property
    def targets(self) -> tuple[str, ...]:
        """The target fields, in evaluation order."""
        return self._set.targets

    @property
    def warnings(self) -> tuple[RuleDiagnostic, ...]:
        """Rows the set compiled with that never fire as written."""
        return self._set.warnings

    def __len__(self) -> int:
        return len(self._set.rules)

    def __repr__(self) -> str:
        return f"RuleSet(name={self.name!r}, targets={list(self.targets)!r}, rules={len(self)})"

    def evaluate(self, record: Mapping[str, Any], clamp: Clamp | None = None) -> Outcome:
        """Set each target from the first row that matches ``record``, then apply ``clamp``.

        Args:
            record: The parsed JSON object. Paths reach into objects, not arrays.
            clamp: Hold one target to an allowed set. ``None`` applies no clamp.

        Returns:
            The values the targets end with.
        """
        outcome = self._run(record, clamp)
        self._usage.record(outcome)
        return outcome

    def batch(self) -> Batch:
        """Return a batch that counts locally and adds to the set once, at flush or exit."""
        return Batch(self)

    def usage(self) -> list[RuleUsage]:
        """Return each row's hits and clamps since the set compiled, in evaluation order."""
        compiled = self._set
        with self._usage.lock:
            return [
                RuleUsage(
                    rule=rule.id,
                    target=compiled.targets[rule.target],
                    hits=self._usage.hits[index],
                    clamped=self._usage.clamped[index],
                )
                for index, rule in enumerate(compiled.rules)
            ]

    def record_clamped(self) -> int:
        """Return how many record-carried values the clamp replaced, which no row set."""
        with self._usage.lock:
            return self._usage.clamped[-1]

    def _run(self, record: Mapping[str, Any], clamp: Clamp | None) -> Outcome:
        compiled = self._set
        assigned: list[Assignment | None] = [None] * len(compiled.targets)
        fired: list[int | None] = [None] * len(compiled.targets)
        for target, rows in enumerate(compiled.ranges):
            for index in rows:
                rule = compiled.rules[index]
                if not self._holds(rule.condition, record, assigned, target):
                    continue
                value = self._resolve(rule.action, record, assigned, target)
                if value is not None:
                    assigned[target] = Assignment(value, rule.id)
                    fired[target] = index
                    break
        result: ClampResult | None = None
        clamped: int | None = None
        if clamp is not None:
            result, clamped = self._clamp(record, clamp, assigned, fired)
        return Outcome(compiled.targets, assigned, fired, result, clamped)

    def _clamp(
        self,
        record: Mapping[str, Any],
        clamp: Clamp,
        assigned: list[Assignment | None],
        fired: list[int | None],
    ) -> tuple[ClampResult | None, int | None]:
        """Apply the clamp, returning its result and the counter slot it adds to."""
        compiled = self._set
        try:
            target = compiled.targets.index(clamp.target)
        except ValueError:
            return None, None
        current = assigned[target]
        rule_index = fired[target]
        if current is not None:
            value: str | None = current.value
            rule = current.rule
        else:
            value = present_text(read_path(record, compiled.target_segments[target]))
            rule = None
        if value is not None and value in clamp.allowed:
            return ClampResult(ClampOutcome.KEPT), None
        assigned[target] = Assignment(clamp.default, None)
        fired[target] = None
        if value is None:
            return ClampResult(ClampOutcome.DEFAULTED), None
        slot = rule_index if rule_index is not None else len(compiled.rules)
        return ClampResult(ClampOutcome.REPLACED, was=value, rule=rule), slot

    def _read(self, field: int, record: Mapping[str, Any], assigned: list[Assignment | None], target: int) -> Found:
        """The value at a field: an earlier target's new value, else the record's."""
        slot = self._set.fields[field]
        if slot.target is not None and slot.target < target:
            earlier = assigned[slot.target]
            if earlier is not None:
                return earlier.value
        return read_path(record, slot.segments)

    def _holds(
        self,
        condition: Condition,
        record: Mapping[str, Any],
        assigned: list[Assignment | None],
        target: int,
    ) -> bool:
        if condition is None:
            return True
        if isinstance(condition, Leaf):
            return condition.test(self._read(condition.field, record, assigned, target)) != condition.negate
        if isinstance(condition, AllOf):
            holds = all(self._holds(part, record, assigned, target) for part in condition.parts)
            return holds != condition.negate
        return self._cel_holds(condition, record, assigned, target)

    def _cel_holds(
        self,
        condition: CelCondition,
        record: Mapping[str, Any],
        assigned: list[Assignment | None],
        target: int,
    ) -> bool:
        """Feed the condition each name it reads: an earlier target's new value, else the record's."""
        targets = self._set.targets
        context: dict[str, Any] = {}
        for name in condition.names:
            if name in targets[:target]:
                earlier = assigned[targets.index(name)]
                if earlier is not None:
                    context[name] = earlier.value
                    continue
            if isinstance(record, Mapping):
                value = record.get(name, _ABSENT)
                if value is not _ABSENT:
                    context[name] = value
        try:
            return condition.program.execute(context) is True
        except EVALUATION_ERRORS:
            return False

    def _resolve(
        self,
        action: Literal | Copy | TableLookup,
        record: Mapping[str, Any],
        assigned: list[Assignment | None],
        target: int,
    ) -> str | None:
        if isinstance(action, Literal):
            return action.value
        found = present_text(self._read(action.field, record, assigned, target))
        if isinstance(action, Copy) or found is None:
            return found
        return self._set.tables[action.table].get(found)
