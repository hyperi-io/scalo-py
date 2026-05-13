#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_parity_manifest.py
#  Purpose:   Lock the cross-language parity manifest shape
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the parity manifest emitter.

The manifest is the contract surface that hyperi-ai's CI diffs
between pylib and rustlib. The tests here lock the manifest shape so
unintentional drift in pylib's output gets caught locally before it
reaches the cross-language gate.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from hyperi_pylib.logger.scrub.parity_manifest import (
    CONFIG_KEYS,
    METRIC_NAMES,
    build_manifest,
)


class TestManifestShape:
    @pytest.fixture(scope="class")
    def m(self):
        return build_manifest()

    def test_top_level_keys(self, m):
        # The keys here ARE the contract. Adding a new top-level key
        # requires a spec amendment in both pylib and rustlib.
        assert set(m.keys()) == {
            "implementation",
            "language",
            "spec_version",
            "metric_names",
            "config_keys",
            "gitleaks",
            "l3_validators",
            "redaction_label_format",
            "no_layer_4",
        }

    def test_implementation_self_identifies(self, m):
        assert m["implementation"] == "hyperi-pylib"
        assert m["language"] == "python"

    def test_spec_version_is_pinned(self, m):
        assert m["spec_version"] == "2026-05-13"

    def test_metric_names_match_constant(self, m):
        # The METRIC_NAMES tuple is the cross-language source of truth
        # for metric strings. The manifest must echo it verbatim.
        assert list(METRIC_NAMES) == m["metric_names"]

    def test_metric_names_contain_required_set(self, m):
        # Pin the exact six metric strings the spec mandates.
        required = {
            "log_scrub_matches_total",
            "log_scrub_redactions_total",
            "log_scrub_errors_total",
            "log_scrub_skipped_rules_total",
            "log_scrub_duration_seconds",
            "log_scrub_pattern_version",
        }
        assert set(m["metric_names"]) == required

    def test_config_keys_match_constant(self, m):
        assert list(CONFIG_KEYS) == m["config_keys"]

    def test_config_keys_present(self, m):
        # The seven (or more) canonical keys per spec §6 + §8.1
        # operator controls.
        for k in (
            "enabled",
            "observe_only",
            "hash_redaction",
            "metrics_enabled",
            "metrics_type_cardinality_cap",
            "fields",
            "secrets",
            "pii",
            "log_levels",
        ):
            assert k in m["config_keys"]

    def test_gitleaks_block_shape(self, m):
        gl = m["gitleaks"]
        assert "meta" in gl
        assert "total_rules_in_toml" in gl
        assert "loaded_rule_ids" in gl
        assert "skipped_rule_ids" in gl
        assert "labels" in gl
        assert gl["total_rules_in_toml"] >= 200
        assert isinstance(gl["loaded_rule_ids"], list)
        assert isinstance(gl["skipped_rule_ids"], list)

    def test_l3_validators_block(self, m):
        v = m["l3_validators"]
        assert "labels" in v
        assert "national_ids_default" in v
        # Strong-structural validators expected
        for label in ("CREDIT_CARD", "IBAN", "EMAIL", "PHONE"):
            assert label in v["labels"]
        # AU national IDs ship pre-active
        for label in ("AU_ABN", "AU_ACN", "AU_TFN", "AU_MEDICARE"):
            assert label in v["labels"]
        assert v["national_ids_default"] == ["au"]

    def test_redaction_label_format(self, m):
        fmt = m["redaction_label_format"]
        assert fmt["static"] == "[<LABEL>_REDACTED]"
        assert fmt["hash"] == "[<LABEL>_<6-hex>]"
        assert "blake2b" in fmt["hash_algorithm"]

    def test_no_layer_4_documented(self, m):
        assert "NLP/NER" in m["no_layer_4"]


class TestManifestJsonRoundTrip:
    def test_manifest_is_json_serialisable(self):
        m = build_manifest()
        s = json.dumps(m, sort_keys=True)
        # And deserialisable
        back = json.loads(s)
        assert back["implementation"] == "hyperi-pylib"

    def test_cli_entrypoint_emits_json(self):
        """``python -m ...parity_manifest`` produces valid JSON on stdout."""
        result = subprocess.run(
            [sys.executable, "-m", "hyperi_pylib.logger.scrub.parity_manifest"],
            capture_output=True,
            text=True,
            check=True,
        )
        manifest = json.loads(result.stdout)
        assert manifest["implementation"] == "hyperi-pylib"
        assert "metric_names" in manifest


class TestManifestStability:
    """Catch accidental drift in the rule set on every test run."""

    def test_gitleaks_rule_count_in_range(self):
        m = build_manifest()
        # Upstream gitleaks ships ~222 rules; allow drift but flag
        # anything outside ±10%.
        loaded = len(m["gitleaks"]["loaded_rule_ids"])
        assert 200 <= loaded <= 250, f"unexpected loaded rule count: {loaded}"

    def test_no_unexpected_skipped_rules(self):
        m = build_manifest()
        # With the `regex` package, we should compile every rule
        # upstream ships. If this asserts, investigate whether a
        # regex incompatibility crept in.
        skipped = m["gitleaks"]["skipped_rule_ids"]
        assert skipped == [], f"unexpected skipped rules: {skipped}"
