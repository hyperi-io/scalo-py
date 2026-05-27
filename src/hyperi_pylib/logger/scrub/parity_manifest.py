#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/parity_manifest.py
#  Purpose:   Emit a JSON manifest of what this implementation supports
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Emit a parity manifest of the scrubber's supported surface.

Spec §11 requires that hyperi-pylib and hyperi-rustlib produce
identical scrubbing outputs and identical observability surfaces.
This module collects a JSON document listing every metric name,
every loaded rule ID, every skipped rule ID, every validator
label, and every config knob this implementation supports.

The corresponding rustlib entry point will emit the same shape.
A CI job in hyperi-ai diffs the two manifests; any divergence
fails the CI run and blocks releases.

Usage:

    python -m hyperi_pylib.logger.scrub.parity_manifest > pylib.json

Or programmatically::

    from hyperi_pylib.logger.scrub.parity_manifest import build_manifest
    m = build_manifest()
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import ScrubConfig
from .factory import build_scrubber
from .gitleaks_toml import load_gitleaks_rules

# Metric names per spec §8 -- these strings are the cross-language
# contract. Both implementations MUST emit identical bytes.
METRIC_NAMES: tuple[str, ...] = (
    "log_scrub_matches_total",
    "log_scrub_redactions_total",
    "log_scrub_errors_total",
    "log_scrub_skipped_rules_total",
    "log_scrub_duration_seconds",
    "log_scrub_pattern_version",
)


# Top-level ScrubConfig keys per spec §6 -- both implementations MUST
# accept and honour every key. New keys require a spec amendment in
# both projects.
CONFIG_KEYS: tuple[str, ...] = (
    "enabled",
    "observe_only",
    "hash_redaction",
    "metrics_enabled",
    "metrics_type_cardinality_cap",
    "fields",
    "secrets",
    "pii",
    "log_levels",
)


def build_manifest() -> dict[str, Any]:
    """Build a JSON-serialisable manifest of supported surfaces."""
    # Load the bundled gitleaks rules to get the rule-ID + label list.
    raw_rules, gitleaks_meta = load_gitleaks_rules()

    # Walk the canonical defaults to gather L3 validator labels.
    cfg = ScrubConfig()
    scrubber = build_scrubber(cfg)
    l3_labels: list[str] = []
    for layer in scrubber.layers:
        if hasattr(layer, "LABEL") and layer.LABEL:
            l3_labels.append(layer.LABEL)
    l3_labels.sort()

    # Gitleaks rules -- the IDs we successfully compiled + the IDs we
    # skipped (regex incompatibility on this side).
    from .gitleaks_toml import GitleaksTomlScrubber

    gl = GitleaksTomlScrubber()
    loaded_rule_ids = sorted({r.id for r in gl._compiled})
    skipped_rule_ids = sorted(gl.skipped_rules)

    # Per-rule labels (derived) -- also part of the cross-language
    # output contract.
    rule_labels = sorted({r.label for r in gl._compiled})

    return {
        "implementation": "hyperi-pylib",
        "language": "python",
        "spec_version": "2026-05-13",
        "metric_names": list(METRIC_NAMES),
        "config_keys": list(CONFIG_KEYS),
        "gitleaks": {
            "meta": dict(gitleaks_meta),
            "total_rules_in_toml": len(raw_rules),
            "loaded_rule_ids": loaded_rule_ids,
            "skipped_rule_ids": skipped_rule_ids,
            "labels": rule_labels,
        },
        "l3_validators": {
            "labels": l3_labels,
            "national_ids_default": list(cfg.pii.validators.national_ids.enabled),
        },
        "redaction_label_format": {
            "static": "[<LABEL>_REDACTED]",
            "hash": "[<LABEL>_<6-hex>]",
            "hash_algorithm": "blake2b-keyed-4byte-truncated-to-6-hex",
        },
        "no_layer_4": ("NLP/NER scrubbing dropped from scope; see spec §2 for rationale"),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point -- emit the manifest as JSON to stdout."""
    manifest = build_manifest()
    json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
