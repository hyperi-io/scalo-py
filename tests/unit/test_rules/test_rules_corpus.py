# Project:   scalo
# File:      tests/unit/test_rules/test_rules_corpus.py
# Purpose:   The shared rules corpus, run against scalo-py's validator and evaluator
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""``tests/fixtures/rules_corpus.json`` is vendored from scalo-rs, which runs the same cases.

Every finding must match on severity, location, rule and span, and every outcome on the
value and the row that set it, so the two implementations accept, refuse and route the
same rule sets the same way.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scalo.expression import ProfileConfig
from scalo.rules import Clamp, CompileOptions, Outcome, RuleSet

CORPUS = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "rules_corpus.json").read_text("utf-8"))


def _options(allow_regex: bool) -> CompileOptions:
    return CompileOptions(profile=ProfileConfig(allow_regex=allow_regex))


def _span(span: Any) -> list[int] | None:
    return None if span is None else [span.start, span.end]


@pytest.mark.parametrize("case", CORPUS["compile"], ids=lambda case: case["name"])
def test_every_compile_case_finds_exactly_its_findings(case: dict[str, Any]) -> None:
    options = _options(case.get("allow_regex", False))
    found = RuleSet.check(case["config"], options)

    got = [(str(d.severity), d.location, d.rule, _span(d.span)) for d in found]
    want = [(f["severity"], f["location"], f["rule"], f["span"]) for f in case["findings"]]
    assert got == want, [str(d) for d in found]
    for diagnostic, finding in zip(found, case["findings"], strict=True):
        assert finding["contains"] in diagnostic.message, (diagnostic.message, finding["contains"])

    has_error = any(f["severity"] == "error" for f in case["findings"])
    if has_error:
        with pytest.raises(Exception, match="the rule set is invalid"):
            RuleSet.compile(case["config"], options)
    else:
        compiled = RuleSet.compile(case["config"], options)
        assert [str(d) for d in compiled.warnings] == [str(d) for d in found]


def _assignments(outcome: Outcome) -> dict[str, dict[str, str | None]]:
    return {field: {"value": a.value, "rule": a.rule} for field, a in outcome}


@pytest.mark.parametrize("case", CORPUS["evaluate"], ids=lambda case: case["name"])
def test_every_evaluate_case_gives_its_outcome(case: dict[str, Any]) -> None:
    rules = RuleSet.compile(case["config"], _options(False))
    spec = case.get("clamp")
    clamp = None if spec is None else Clamp(spec["target"], frozenset(spec["allowed"]), spec["default"])
    for index, record_case in enumerate(case["cases"]):
        record = record_case["record"]
        # A JSON round trip gives the shape a record parsed off the wire has.
        for source, value in (("value", copy.deepcopy(record)), ("json", json.loads(json.dumps(record)))):
            outcome = rules.evaluate(value, clamp)
            label = f"{case['name']} case {index} from {source}"
            assert _assignments(outcome) == record_case["expect"], label
            clamp_name = None if outcome.clamp is None else str(outcome.clamp.outcome)
            assert clamp_name == record_case.get("clamp"), label
