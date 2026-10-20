# Project:   scalo
# File:      tests/unit/test_expression/test_rules.py
# Purpose:   Compile, evaluate, clamp and count tests for the rules module
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for scalo.expression.rules beyond the shared corpus."""

import dataclasses
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from scalo.expression import ProfileConfig
from scalo.expression.rules import (
    RECORD_LABEL,
    Clamp,
    ClampOutcome,
    CompileOptions,
    RulesError,
    RuleSet,
    RulesLoadError,
    Severity,
)

OPTIONS = CompileOptions()
REGEX = CompileOptions(profile=ProfileConfig(allow_regex=True))


def two_targets(*rules: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"name": "t", "targets": ["_source", "_org_id"], "rules": list(rules), **extra}


def row(rule_id: str, target: str, action: dict[str, str], **condition: Any) -> dict[str, Any]:
    return {"id": rule_id, "set": {target: action}, **condition}


def compile_set(config: dict[str, Any], options: CompileOptions = OPTIONS) -> RuleSet:
    return RuleSet.compile(config, options)


def errors(config: dict[str, Any], options: CompileOptions = OPTIONS) -> list[str]:
    return [d.location for d in RuleSet.check(config, options) if d.is_error]


# -- Evaluate --------------------------------------------------------


class TestFirstMatch:
    def test_the_first_matching_row_in_declared_order_wins(self):
        rules = compile_set(
            two_targets(
                row("first", "_source", {"value": "a"}, match={"field": "host", "op": "starts_with", "value": "web"}),
                row("second", "_source", {"value": "b"}, match={"field": "host", "op": "starts_with", "value": "web-"}),
            )
        )
        assigned = rules.evaluate({"host": "web-1"}).get("_source")
        assert assigned is not None
        assert (assigned.value, assigned.rule) == ("a", "first")

    def test_no_matching_row_leaves_the_target_unassigned(self):
        rules = compile_set(
            two_targets(
                row("web", "_source", {"value": "web"}, match={"field": "host", "op": "equals", "value": "web"})
            )
        )
        outcome = rules.evaluate({"host": "db"})
        assert len(outcome) == 0
        assert outcome.clamp is None

    def test_outcome_iteration_follows_target_order(self):
        rules = compile_set(two_targets(row("o", "_org_id", {"value": "o"}), row("s", "_source", {"value": "s"})))
        assert [field for field, _ in rules.evaluate({})] == ["_source", "_org_id"]
        assert rules.targets == ("_source", "_org_id")
        assert rules.evaluate({}).get("nope") is None


class TestTargetOrder:
    def test_a_later_target_reads_an_earlier_targets_new_value(self):
        rules = compile_set(
            two_targets(
                row(
                    "org-for-web",
                    "_org_id",
                    {"value": "web-org"},
                    match={"field": "_source", "op": "equals", "value": "web"},
                ),
                row("web", "_source", {"value": "web"}, match={"field": "host", "op": "starts_with", "value": "web-"}),
            )
        )
        assert rules.evaluate({"host": "web-1", "_source": "sender-said"}).value("_org_id") == "web-org"
        # With no `_source` row matching, the org row reads the record's own value.
        assert rules.evaluate({"host": "db-1", "_source": "web"}).value("_org_id") == "web-org"

    def test_an_earlier_target_reads_the_records_value_of_a_later_one(self):
        rules = compile_set(
            two_targets(
                row("src", "_source", {"from": "_org_id"}, match={"field": "_org_id", "op": "exists"}),
                row("org", "_org_id", {"value": "new"}),
            )
        )
        assert rules.evaluate({"_org_id": "old"}).value("_source") == "old"

    def test_a_cel_condition_reads_an_earlier_targets_new_value(self):
        rules = compile_set(
            two_targets(
                row("web", "_source", {"value": "web"}),
                row("cel", "_org_id", {"value": "o"}, when='_source == "web" && size(host) > 2'),
            )
        )
        assert rules.evaluate({"host": "abc"}).value("_org_id") == "o"
        assert rules.evaluate({"host": "ab"}).value("_org_id") is None
        # A condition naming a missing field is false, not an error.
        assert rules.evaluate({}).value("_org_id") is None

    def test_a_cel_condition_reads_null_and_nested_fields(self):
        rules = compile_set(
            two_targets(
                row("null", "_source", {"value": "n"}, when="x == null"),
                row("nested", "_org_id", {"value": "t"}, when='has(tags.event) && tags.event.kind == "a"'),
            )
        )
        outcome = rules.evaluate({"x": None, "tags": {"event": {"kind": "a"}}})
        assert outcome.value("_source") == "n"
        assert outcome.value("_org_id") == "t"
        assert rules.evaluate({"tags": {}}).value("_org_id") is None


class TestActions:
    def test_a_from_row_that_finds_nothing_falls_through_to_the_next(self):
        rules = compile_set(
            two_targets(
                row("tags", "_org_id", {"from": "tags.event.org_id"}),
                row("flat", "_org_id", {"from": "org_id"}),
                row("fallback", "_org_id", {"value": "default"}),
            )
        )
        cases = [
            ({"tags": {"event": {"org_id": "t1"}}, "org_id": "f1"}, "t1", "tags"),
            ({"tags": {"event": {"org_id": ""}}, "org_id": "f1"}, "f1", "flat"),
            ({"tags": {"event": {"org_id": None}}, "org_id": "f1"}, "f1", "flat"),
            ({"tags": {"event": {"org_id": {"x": 1}}}, "org_id": 7}, "7", "flat"),
            ({"other": 1}, "default", "fallback"),
        ]
        for record, value, rule in cases:
            assigned = rules.evaluate(record).get("_org_id")
            assert assigned is not None
            assert (assigned.value, assigned.rule) == (value, rule), record

    def test_an_unknown_lookup_key_misses_and_falls_through(self):
        rules = compile_set(
            two_targets(
                row("alias", "_source", {"lookup": "aliases", "from": "tags.event.category"}),
                row("main", "_source", {"value": "main"}),
                lookups={"aliases": {"logs_syslog": "syslog", "logs_beats_winlog": "windows"}},
            )
        )
        assert rules.evaluate({"tags": {"event": {"category": "logs_syslog"}}}).value("_source") == "syslog"
        unknown = rules.evaluate({"tags": {"event": {"category": "logs_unheard_of"}}}).get("_source")
        assert unknown is not None
        assert unknown.rule == "main"
        assert rules.evaluate({}).value("_source") == "main"

    def test_numbers_and_booleans_read_as_their_json_text(self):
        rules = compile_set(two_targets(row("copy", "_source", {"from": "v"})))
        for value, text in [(42, "42"), (1.5, "1.5"), (True, "true"), (False, "false"), (-3, "-3")]:
            assert rules.evaluate({"v": value}).value("_source") == text


class TestNativeTests:
    @pytest.mark.parametrize(
        ("match", "value", "expected"),
        [
            ({"op": "equals", "value": "web"}, "web", True),
            ({"op": "equals", "value": "web"}, "webx", False),
            ({"op": "starts_with", "value": "we"}, "web", True),
            ({"op": "ends_with", "value": "eb"}, "web", True),
            ({"op": "ends_with", "value": "we"}, "web", False),
            ({"op": "contains", "value": "e"}, "web", True),
            ({"op": "contains", "value": "x"}, "web", False),
            ({"op": "prefix_and_suffix", "prefix": "w", "suffix": "b"}, "web", True),
            ({"op": "prefix_and_suffix", "prefix": "w", "suffix": "x"}, "web", False),
            ({"op": "length", "min": 3, "max": 3}, "web", True),
            ({"op": "length", "min": 4}, "web", False),
            ({"op": "length", "max": 2}, "web", False),
            ({"op": "length", "min": 2, "max": 2}, "éé", True),
            ({"op": "exists"}, "web", True),
            ({"op": "exists"}, "", False),
            ({"op": "contains", "value": "internal", "negate": True}, "web", True),
        ],
    )
    def test_every_native_test_reads_the_fields_text(self, match: dict[str, Any], value: str, expected: bool):
        rules = compile_set(two_targets(row("r", "_source", {"value": "hit"}, match={"field": "h", **match})))
        assert (len(rules.evaluate({"h": value})) > 0) is expected

    @pytest.mark.parametrize("record", [{}, {"h": None}, {"h": {"x": 1}}, {"h": [1]}])
    def test_a_test_on_a_missing_null_or_composite_field_fails_and_its_negation_holds(self, record):
        plain = compile_set(
            two_targets(row("r", "_source", {"value": "hit"}, match={"field": "h", "op": "contains", "value": "x"}))
        )
        negated = compile_set(
            two_targets(
                row(
                    "r",
                    "_source",
                    {"value": "hit"},
                    match={"field": "h", "op": "contains", "value": "x", "negate": True},
                )
            )
        )
        assert len(plain.evaluate(record)) == 0
        assert len(negated.evaluate(record)) == 1

    def test_exists_accepts_an_object_and_a_zero_and_refuses_null_and_empty(self):
        rules = compile_set(two_targets(row("r", "_source", {"value": "hit"}, match={"field": "h", "op": "exists"})))
        assert len(rules.evaluate({"h": {"a": 1}})) == 1
        assert len(rules.evaluate({"h": 0})) == 1
        for absent in [{}, {"h": None}, {"h": ""}]:
            assert len(rules.evaluate(absent)) == 0, absent

    def test_a_path_does_not_reach_into_an_array_or_a_string(self):
        rules = compile_set(two_targets(row("r", "_source", {"from": "a.0"})))
        assert rules.evaluate({"a": ["x"]}).value("_source") is None
        assert rules.evaluate({"a": "text"}).value("_source") is None
        assert rules.evaluate({"a": {"0": "y"}}).value("_source") == "y"

    def test_all_needs_every_part_and_negate_inverts_it(self):
        both = {
            "all": [
                {"field": "h", "op": "starts_with", "value": "web-"},
                {"field": "h", "op": "ends_with", "value": ".prod"},
            ]
        }
        rules = compile_set(
            two_targets(
                row("both", "_source", {"value": "prod"}, match=both),
                row("not-both", "_source", {"value": "other"}, match={**both, "negate": True}),
            )
        )
        assert rules.evaluate({"h": "web-1.prod"}).value("_source") == "prod"
        assert rules.evaluate({"h": "web-1.dev"}).value("_source") == "other"

    def test_a_regex_test_runs_where_the_profile_allows_it(self):
        rules = compile_set(
            two_targets(
                row("r", "_source", {"value": "hit"}, match={"field": "h", "op": "regex", "value": "^web-[0-9]+$"})
            ),
            REGEX,
        )
        assert len(rules.evaluate({"h": "web-12"})) == 1
        assert len(rules.evaluate({"h": "web-x"})) == 0
        # `$` is the end of the text only, as in the Rust regex engine.
        assert len(rules.evaluate({"h": "web-12\n"})) == 0


def org_rules(options: CompileOptions = OPTIONS) -> RuleSet:
    return compile_set(
        two_targets(
            row("sender", "_org_id", {"from": "tenant"}),
            row("web", "_org_id", {"value": "web-org"}, match={"field": "host", "op": "starts_with", "value": "web"}),
        ),
        options,
    )


CLAMP = Clamp("_org_id", frozenset({"acme", "default"}), "default")


class TestClamp:
    def test_the_clamp_replaces_a_value_outside_the_allowed_set(self):
        rules = org_rules()
        outcome = rules.evaluate({"tenant": "other-corp"}, CLAMP)
        assert outcome.value("_org_id") == "default"
        assigned = outcome.get("_org_id")
        assert assigned is not None
        assert assigned.rule is None
        assert outcome.clamp is not None
        assert (outcome.clamp.outcome, outcome.clamp.was, outcome.clamp.rule) == (
            ClampOutcome.REPLACED,
            "other-corp",
            "sender",
        )
        inside = rules.evaluate({"tenant": "acme"}, CLAMP)
        assert inside.value("_org_id") == "acme"
        assert inside.clamp is not None
        assert inside.clamp.outcome is ClampOutcome.KEPT

    def test_the_clamp_holds_the_records_own_value_too(self):
        rules = org_rules()
        foreign = rules.evaluate({"_org_id": "other-corp"}, CLAMP)
        assert foreign.value("_org_id") == "default"
        assert foreign.clamp is not None
        assert (foreign.clamp.outcome, foreign.clamp.rule) == (ClampOutcome.REPLACED, None)

        own = rules.evaluate({"_org_id": "acme"}, CLAMP)
        assert own.get("_org_id") is None, "an allowed record value is left in place"
        assert own.clamp is not None
        assert own.clamp.outcome is ClampOutcome.KEPT

        empty = rules.evaluate({"_org_id": ""}, CLAMP)
        assert empty.value("_org_id") == "default"
        assert empty.clamp is not None
        assert empty.clamp.outcome is ClampOutcome.DEFAULTED

    def test_a_clamp_on_a_target_the_set_lacks_does_nothing(self):
        outcome = org_rules().evaluate({}, Clamp("nowhere", frozenset({"a"}), "a"))
        assert outcome.clamp is None
        assert len(outcome) == 0


class TestCounting:
    def test_hits_count_per_row_and_clamps_per_row_and_record(self):
        rules = org_rules()
        for record in [{"tenant": "acme"}, {"tenant": "evil"}, {"host": "web-1"}, {"_org_id": "evil"}, {}]:
            rules.evaluate(record, CLAMP)
        assert [(u.rule, u.target, u.hits, u.clamped) for u in rules.usage()] == [
            ("sender", "_org_id", 2, 1),
            ("web", "_org_id", 1, 1),
        ]
        assert rules.record_clamped() == 1

    def test_a_batch_adds_its_counts_on_flush_and_on_exit(self):
        rules = org_rules()
        with rules.batch() as batch:
            for _ in range(3):
                batch.evaluate({"tenant": "acme"})
            assert rules.usage()[0].hits == 0, "a batch holds its counts until it flushes"
            batch.flush()
            assert rules.usage()[0].hits == 3
            batch.evaluate({"tenant": "acme"})
        assert rules.usage()[0].hits == 4, "leaving the batch flushed the last count"

    def test_threads_evaluating_together_lose_no_count(self):
        rules = org_rules()

        def work() -> None:
            for _ in range(500):
                rules.evaluate({"tenant": "acme"})

        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert rules.usage()[0].hits == 2000

    def test_counts_reach_the_metrics_series(self):
        from scalo.metrics import create_metrics

        metrics = create_metrics("rulestest", backend="prometheus")
        rules = org_rules(CompileOptions(metrics=metrics))
        rules.evaluate({"tenant": "acme"}, CLAMP)
        rules.evaluate({"_org_id": "evil"}, CLAMP)
        text = metrics.get_metrics().decode()
        assert 'rules_hits_total{rule="sender",rule_set="t"} 1.0' in text
        assert f'rules_clamped_total{{rule="{RECORD_LABEL}",rule_set="t"}} 1.0' in text

        # A recompiled set counts on the same series, while its own usage starts at zero.
        again = org_rules(CompileOptions(metrics=metrics))
        again.evaluate({"tenant": "acme"}, CLAMP)
        assert again.usage()[0].hits == 1
        assert 'rules_hits_total{rule="sender",rule_set="t"} 2.0' in metrics.get_metrics().decode()


# -- Compile ---------------------------------------------------------


class TestCompileFindings:
    def test_a_finding_serialises_as_json(self):
        when = 'x.matches("a")'
        found = RuleSet.check(two_targets(row("r", "_source", {"value": "x"}, when=when)), OPTIONS)
        assert json.loads(json.dumps(dataclasses.asdict(found[0]))) == {
            "severity": "error",
            "location": "rules[0].when",
            "message": found[0].message,
            "rule": "r",
            "span": {"start": 2, "end": 9},
        }
        assert str(found[0]).startswith("error: rules[0].when (rule r): Function 'matches()'")
        assert str(found[0]).endswith(" at 2..9")

    def test_a_duplicate_rule_id_is_refused(self):
        config = two_targets(row("a", "_source", {"value": "x"}), row("a", "_org_id", {"value": "y"}))
        found = [d for d in RuleSet.check(config, OPTIONS) if d.is_error]
        assert [d.location for d in found] == ["rules[1].id"]
        assert found[0].rule == "a"
        with pytest.raises(RulesError) as raised:
            RuleSet.compile(config, OPTIONS)
        assert [d.location for d in raised.value.diagnostics] == ["rules[1].id"]

    def test_every_error_in_a_set_is_reported_in_one_pass(self):
        config = two_targets(
            row("bad id!", "_source", {"value": "x"}),
            row("b", "nowhere", {"value": "y"}),
            row(
                "c", "_source", {"lookup": "missing", "from": "f"}, match={"field": "..", "op": "equals", "value": "x"}
            ),
        )
        assert errors(config) == [
            "rules[0].id",
            "rules[1].set.nowhere",
            "rules[2].set._source.lookup",
            "rules[2].match.field",
        ]

    def test_a_target_list_must_name_each_field_once(self):
        config = {"name": "t", "targets": ["a", "a", "b."], "rules": [row("r", "a", {"value": "x"})]}
        assert errors(config) == ["targets[1]", "targets[2]"]
        none = {"name": "t", "targets": [], "rules": [row("r", "a", {"value": "x"})]}
        assert "targets" in errors(none)
        many = {"targets": [f"t{i}" for i in range(9)]}
        assert errors(many) == ["targets"]

    def test_an_empty_set_with_no_targets_compiles(self):
        rules = compile_set({"name": "t"})
        assert len(rules) == 0
        assert rules.name == "t"
        assert compile_set({}).name == "rules"

    def test_a_row_sets_exactly_one_known_target(self):
        config = two_targets({"id": "r", "set": {"_source": {"value": "x"}, "_org_id": {"value": "y"}}})
        assert errors(config) == ["rules[0].set"]

    @pytest.mark.parametrize(
        ("action", "location"),
        [
            ({}, "rules[0].set._source"),
            ({"lookup": "t"}, "rules[0].set._source"),
            ({"value": "x", "from": "f"}, "rules[0].set._source"),
            ({"value": ""}, "rules[0].set._source.value"),
        ],
    )
    def test_an_action_takes_one_source_of_its_value(self, action, location):
        assert errors(two_targets(row("r", "_source", action))) == [location]

    @pytest.mark.parametrize(
        ("match", "expected"),
        [
            ({"field": "host", "op": "equals", "value": "x", "prefix": "p"}, ["rules[0].match.prefix"]),
            ({"field": "host", "op": "equals"}, ["rules[0].match.value"]),
            ({"field": "host", "op": "length", "min": 5, "max": 2}, ["rules[0].match.min"]),
            ({"field": "host", "op": "length"}, ["rules[0].match"]),
            ({"field": "host", "op": "prefix_and_suffix", "prefix": "a"}, ["rules[0].match"]),
            ({}, ["rules[0].match"]),
            ({"field": "host", "all": [{"field": "a", "op": "exists"}]}, ["rules[0].match.field"]),
        ],
    )
    def test_each_op_takes_its_own_operands_only(self, match, expected):
        assert errors(two_targets(row("r", "_source", {"value": "x"}, match=match))) == expected

    def test_regex_follows_the_profile(self):
        config = two_targets(
            row("r", "_source", {"value": "x"}, match={"field": "host", "op": "regex", "value": "^web-[0-9]+$"})
        )
        off = [d for d in RuleSet.check(config, OPTIONS) if d.is_error]
        assert [d.location for d in off] == ["rules[0].match.op"]
        assert "allow_regex" in off[0].message
        assert len(compile_set(config, REGEX)) == 1

        for broken in ["(", "(?=x)", r"(a)\1", ""]:
            bad = two_targets(
                row("r", "_source", {"value": "x"}, match={"field": "host", "op": "regex", "value": broken})
            )
            assert errors(bad, REGEX) == ["rules[0].match.value"], broken

    def test_a_cel_condition_error_carries_the_scanner_span(self):
        when = 'severity == "high" && name.matches("^x")'
        found = RuleSet.check(two_targets(row("r", "_source", {"value": "x"}, when=when)), OPTIONS)
        assert [d.location for d in found] == ["rules[0].when"]
        assert found[0].span is not None
        assert when.encode()[found[0].span.start : found[0].span.end] == b"matches"
        assert found[0].rule == "r"

    def test_a_span_counts_bytes_after_non_ascii_text(self):
        when = 'label == "été" && x.map(a, a)'
        found = RuleSet.check(two_targets(row("r", "_source", {"value": "x"}, when=when)), OPTIONS)
        assert found[0].span is not None
        assert when.encode()[found[0].span.start : found[0].span.end] == b"map"

    def test_match_and_when_together_are_refused(self):
        config = two_targets(row("r", "_source", {"value": "x"}, match={"field": "a", "op": "exists"}, when="a == 1"))
        assert errors(config) == ["rules[0]"]

    def test_a_lookup_table_is_bounded_and_has_no_empty_key_or_value(self):
        tight = CompileOptions(max_lookup_entries=1)
        config = two_targets(lookups={"t": {"a": "x", "b": "y"}})
        assert [d.location for d in RuleSet.check(config, tight)] == ["lookups.t"]
        empty = two_targets(lookups={"t": {"": "x", "b": ""}})
        assert errors(empty) == ["lookups.t", "lookups.t"]

    def test_id_rules(self):
        for good in ["a", "org-tags", "v1.2", "ns:row/7@x", "A_b"]:
            assert errors(two_targets(row(good, "_source", {"value": "x"}))) == [], good
        for bad in ["", "-a", "a b", "a!", "x" * 129, "é"]:
            assert errors(two_targets(row(bad, "_source", {"value": "x"}))) == ["rules[0].id"], bad


class TestShadowWarnings:
    def test_rows_after_an_unconditional_literal_are_reported_shadowed(self):
        rules = compile_set(
            two_targets(
                row("catch-all", "_source", {"value": "main"}),
                row("late", "_source", {"value": "web"}, match={"field": "host", "op": "starts_with", "value": "web-"}),
                row("other-target", "_org_id", {"value": "o"}),
            )
        )
        assert [d.location for d in rules.warnings] == ["rules[1]"]
        assert rules.warnings[0].severity is Severity.WARNING
        assert rules.warnings[0].rule == "late"
        assert "catch-all" in rules.warnings[0].message

    def test_an_earlier_exists_shadows_a_test_that_needs_the_field(self):
        rules = compile_set(
            two_targets(
                row("has-host", "_source", {"value": "a"}, match={"field": "host", "op": "exists"}),
                row("web", "_source", {"value": "b"}, match={"field": "host", "op": "equals", "value": "web"}),
                row(
                    "not-web",
                    "_source",
                    {"value": "c"},
                    match={"field": "host", "op": "equals", "value": "web", "negate": True},
                ),
                row("same", "_source", {"value": "d"}, match={"field": "host", "op": "exists"}),
            )
        )
        assert [d.location for d in rules.warnings] == ["rules[1]", "rules[3]"]

    def test_a_from_or_lookup_row_never_shadows(self):
        rules = compile_set(
            two_targets(row("copy", "_source", {"from": "src"}), row("fallback", "_source", {"value": "main"}))
        )
        assert rules.warnings == ()

    def test_an_identical_when_shadows(self):
        rules = compile_set(
            two_targets(
                row("a", "_source", {"value": "x"}, when="h == 1"), row("b", "_source", {"value": "y"}, when=" h == 1 ")
            )
        )
        assert [d.location for d in rules.warnings] == ["rules[1]"]


class TestShape:
    @pytest.mark.parametrize(
        ("config", "location"),
        [
            ({"rules": [{"id": "a", "set": {"x": {"vaule": "y"}}}]}, "rules[0].set.x.vaule"),
            ({"rulez": []}, "rulez"),
            ({"rules": [{"id": "a", "set": {"x": {"value": "y"}}, "when ": "x"}]}, "rules[0].when "),
            ({"rules": [{"id": "a", "set": {"x": {"value": 5}}}]}, "rules[0].set.x.value"),
            ({"rules": [{"set": {"x": {"value": "y"}}}]}, "rules[0].id"),
            ({"rules": [{"id": "a"}]}, "rules[0].set"),
            ({"targets": "a"}, "targets"),
            ({"targets": None}, "targets"),
            (
                {"rules": [{"id": "a", "match": {"field": "f", "op": "nope"}, "set": {"x": {"value": "y"}}}]},
                "rules[0].match.op",
            ),
            (
                {
                    "rules": [
                        {"id": "a", "match": {"field": "f", "op": "length", "min": -1}, "set": {"x": {"value": "y"}}}
                    ]
                },
                "rules[0].match.min",
            ),
            (
                {
                    "rules": [
                        {"id": "a", "match": {"field": "f", "op": "length", "min": True}, "set": {"x": {"value": "y"}}}
                    ]
                },
                "rules[0].match.min",
            ),
            (
                {"rules": [{"id": "a", "match": {"negate": "yes"}, "set": {"x": {"value": "y"}}}]},
                "rules[0].match.negate",
            ),
            ({"lookups": {"t": {"a": 1}}}, "lookups.t"),
            ({"name": 7}, "name"),
        ],
    )
    def test_a_malformed_config_is_refused_at_its_location(self, config, location):
        found = RuleSet.check(config, OPTIONS)
        assert location in [d.location for d in found], [str(d) for d in found]
        assert all(d.is_error for d in found)
        with pytest.raises(RulesError):
            RuleSet.compile(config, OPTIONS)

    def test_a_non_mapping_is_refused(self):
        not_a_set: Any = ["not", "a", "set"]
        assert [d.location for d in RuleSet.check(not_a_set, OPTIONS)] == [""]

    def test_null_optional_keys_read_as_absent(self):
        rules = compile_set(
            two_targets({"id": "a", "match": None, "when": None, "set": {"_source": {"value": "x", "from": None}}})
        )
        assert rules.evaluate({}).value("_source") == "x"


class TestFileSection:
    GOOD = """
log_level: info
routing:
  rules:
    name: ingest
    targets: [_source]
    rules:
      - id: web
        match: { field: host, op: starts_with, value: web- }
        set: { _source: { value: web } }
"""

    def test_a_section_of_the_file_compiles(self, tmp_path: Path):
        path = tmp_path / "config.yaml"
        path.write_text(self.GOOD, encoding="utf-8")
        rules = RuleSet.from_file_section(path, "routing.rules", OPTIONS)
        assert (rules.name, len(rules)) == ("ingest", 1)
        assert rules.evaluate({"host": "web-3"}).value("_source") == "web"

    def test_a_missing_section_or_file_is_a_load_error(self, tmp_path: Path):
        path = tmp_path / "config.yaml"
        path.write_text(self.GOOD, encoding="utf-8")
        with pytest.raises(RulesLoadError):
            RuleSet.from_file_section(path, "routing.absent", OPTIONS)
        with pytest.raises(RulesLoadError):
            RuleSet.from_file_section(tmp_path / "none.yaml", "routing.rules", OPTIONS)
        bad = tmp_path / "bad.yaml"
        bad.write_text("a: [unclosed", encoding="utf-8")
        with pytest.raises(RulesLoadError):
            RuleSet.from_file_section(bad, "a", OPTIONS)

    def test_an_invalid_section_reports_its_findings(self, tmp_path: Path):
        path = tmp_path / "config.yaml"
        path.write_text(self.GOOD.replace("starts_with", "regex"), encoding="utf-8")
        with pytest.raises(RulesError) as raised:
            RuleSet.from_file_section(path, "routing.rules", OPTIONS)
        assert raised.value.diagnostics[0].location == "rules[0].match.op"
