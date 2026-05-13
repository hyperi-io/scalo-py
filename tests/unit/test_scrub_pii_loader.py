#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_pii_loader.py
#  Purpose:   Tests for the TOML-driven national-ID validator loader
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for ``hyperi_pylib.logger.scrub.pii._loader`` and ``_dynamic``."""

from __future__ import annotations

import pytest

from hyperi_pylib.logger.scrub import Scrubber
from hyperi_pylib.logger.scrub.pii import (
    _DynamicValidator,
    build_national_id_validators,
    load_registry,
)


# ---------------------------------------------------------------------------
# Registry load
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_loads_bundled_toml(self):
        reg = load_registry()
        assert isinstance(reg, dict)
        # AU is the only fully-curated country in v1
        assert "au" in reg
        assert "abn" in reg["au"]

    def test_au_abn_entry_shape(self):
        reg = load_registry()
        entry = reg["au"]["abn"]
        assert entry["enabled"] is True
        assert entry["context_required"] is True
        assert "abn" in entry["keywords"]
        assert entry["detection_regex"]
        assert entry["redaction_label"] == "AU_ABN"
        assert entry["stdnum_module"] == "stdnum.au.abn"

    def test_au_medicare_uses_local_validator(self):
        reg = load_registry()
        entry = reg["au"]["medicare"]
        assert "local_validator" in entry
        assert entry["local_validator"].startswith("hyperi_pylib.logger.scrub.pii.au_medicare:")

    def test_other_countries_are_stubs(self):
        reg = load_registry()
        # us.ssn exists as a stub (seeded from stdnum, not yet curated)
        assert reg.get("us", {}).get("ssn", {}).get("enabled", False) is False
        # ... and most other entries
        stub_count = 0
        active_count = 0
        for ids in reg.values():
            if not isinstance(ids, dict):
                continue
            for entry in ids.values():
                if not isinstance(entry, dict):
                    continue
                if entry.get("enabled", False):
                    active_count += 1
                else:
                    stub_count += 1
        # We ship 4 active (au.abn, au.acn, au.tfn, au.medicare)
        assert active_count == 4
        assert stub_count > 150


# ---------------------------------------------------------------------------
# build_national_id_validators
# ---------------------------------------------------------------------------


class TestBuildNationalIdValidators:
    def test_default_au_only(self):
        validators = build_national_id_validators(enabled_countries=["au"])
        labels = sorted(v.LABEL for v in validators)
        assert labels == ["AU_ABN", "AU_ACN", "AU_MEDICARE", "AU_TFN"]

    def test_empty_country_list_yields_none(self):
        validators = build_national_id_validators(enabled_countries=[])
        assert validators == []

    def test_all_countries_returns_only_active(self):
        # No country filter — but only ``enabled = true`` entries materialise
        validators = build_national_id_validators(enabled_countries=None)
        assert len(validators) == 4  # only AU entries are active in v1

    def test_unknown_country_skipped(self):
        # Bogus country — gracefully ignored
        validators = build_national_id_validators(enabled_countries=["zz"])
        assert validators == []

    def test_country_code_case_insensitive(self):
        # Spec uses lowercase, but operators may type uppercase
        v_lower = build_national_id_validators(enabled_countries=["au"])
        v_upper = build_national_id_validators(enabled_countries=["AU"])
        assert {v.LABEL for v in v_lower} == {v.LABEL for v in v_upper}

    def test_every_validator_satisfies_protocol(self):
        validators = build_national_id_validators(enabled_countries=["au"])
        for v in validators:
            assert isinstance(v, Scrubber)


# ---------------------------------------------------------------------------
# _DynamicValidator construction errors
# ---------------------------------------------------------------------------


class TestDynamicValidatorErrors:
    def test_missing_module_raises_value_error(self):
        entry = {
            "redaction_label": "TEST",
            "detection_regex": r"\bx\b",
            "keywords": [],
            "stdnum_module": "stdnum.nonexistent.fake",
        }
        with pytest.raises(ValueError, match="missing module"):
            _DynamicValidator(entry)

    def test_local_validator_bad_format_raises(self):
        entry = {
            "redaction_label": "TEST",
            "detection_regex": r"\bx\b",
            "keywords": [],
            "local_validator": "no_colon_separator",
        }
        with pytest.raises(ValueError, match="module:attribute"):
            _DynamicValidator(entry)

    def test_neither_module_nor_local_raises(self):
        entry = {
            "redaction_label": "TEST",
            "detection_regex": r"\bx\b",
            "keywords": [],
        }
        with pytest.raises(ValueError, match="stdnum_module.*local_validator"):
            _DynamicValidator(entry)

    def test_local_validator_missing_attr_raises(self):
        entry = {
            "redaction_label": "TEST",
            "detection_regex": r"\bx\b",
            "keywords": [],
            "local_validator": "hyperi_pylib.logger.scrub.pii.au_medicare:does_not_exist",
        }
        with pytest.raises(ValueError, match="not callable or missing"):
            _DynamicValidator(entry)


class TestLoaderFailsSafeOnBadEntry:
    """build_national_id_validators MUST warn on bad entries, never raise."""

    def test_bad_entry_warns_then_skipped(self, tmp_path):
        # Build a synthetic registry with one bad entry + one good entry
        registry = {
            "au": {
                "abn": {
                    "redaction_label": "AU_ABN",
                    "detection_regex": r"\b\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b",
                    "keywords": ["abn"],
                    "context_required": True,
                    "enabled": True,
                    "stdnum_module": "stdnum.au.abn",
                },
                "broken": {
                    "redaction_label": "AU_BROKEN",
                    "detection_regex": r"\bx\b",
                    "keywords": [],
                    "enabled": True,
                    "stdnum_module": "stdnum.totally.nonexistent",
                },
            }
        }
        with pytest.warns(RuntimeWarning, match="not loadable"):
            validators = build_national_id_validators(
                registry=registry,
                enabled_countries=["au"],
            )
        # Good entry loaded; bad entry skipped
        assert len(validators) == 1
        assert validators[0].LABEL == "AU_ABN"
