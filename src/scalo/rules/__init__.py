# Project:   scalo
# File:      rules/__init__.py
# Purpose:   Ordered first-match rules that set target fields on a record
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""An ordered rule set: for each target field in turn, the first matching row sets it.

A row tests the record with a native test (``equals``, ``starts_with``, ``ends_with``,
``contains``, ``prefix_and_suffix``, ``length``, ``exists``, ``regex``, each with
``negate``, combined with ``all``) or a CEL Fast condition, and finds its value as a
literal, a copy of a field, or a field mapped through a bounded lookup table. A row
whose copy or lookup finds nothing does not match, so the next row is tried.

Targets are evaluated in the order the set lists them, so a row for a later target can
test an earlier target's new value. A :class:`Clamp` then holds one target to a per-call
allowed set, replacing anything outside it with a default and counting the replacement.

Install::

    pip install scalo[expression]

Usage::

    from scalo.rules import Clamp, RuleSet

    rules = RuleSet.compile({
        "name": "ingest",
        "targets": ["_source", "_org_id"],
        "rules": [
            {"id": "web", "match": {"field": "host", "op": "starts_with", "value": "web-"},
             "set": {"_source": {"value": "web"}}},
            {"id": "web-org", "match": {"field": "_source", "op": "equals", "value": "web"},
             "set": {"_org_id": {"value": "acme"}}},
        ],
    })
    outcome = rules.evaluate({"host": "web-01"}, Clamp("_org_id", {"acme", "default"}, "default"))
    assert outcome.value("_org_id") == "acme"

Compile errors and warnings are :class:`RuleDiagnostic` values naming the config
location, the rule id, and for a CEL condition the byte span the scanner or parser
found. See docs/api/rules.md.
"""

# Loaded before any submodule imports cel, so a missing extra raises the ImportError that names it.
import scalo.expression.cel

from ._compiler import DEFAULT_MAX_LOOKUP_ENTRIES, MAX_TARGETS, CompileOptions
from ._errors import RuleDiagnostic, RulesError, RulesLoadError, Severity
from ._ruleset import (
    RECORD_LABEL,
    Assignment,
    Batch,
    Clamp,
    ClampOutcome,
    ClampResult,
    Outcome,
    RuleSet,
    RuleUsage,
)
from ._shape import DEFAULT_RULE_SET_NAME, MATCH_OPS

__all__ = [
    "DEFAULT_MAX_LOOKUP_ENTRIES",
    "DEFAULT_RULE_SET_NAME",
    "MATCH_OPS",
    "MAX_TARGETS",
    "RECORD_LABEL",
    "Assignment",
    "Batch",
    "Clamp",
    "ClampOutcome",
    "ClampResult",
    "CompileOptions",
    "Outcome",
    "RuleDiagnostic",
    "RuleSet",
    "RuleUsage",
    "RulesError",
    "RulesLoadError",
    "Severity",
]
