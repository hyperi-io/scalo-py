#  Project:      hyperi-pylib
#  File:         test_metrics_naming_parity.py
#  Purpose:      Verify validate_metric_name and validate_dfe_prefix against shared corpus
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Parity tests for DFE metric naming validation using the shared fixture corpus.

Loads hyperi-ai/test-fixtures/metrics-naming.yaml and verifies that
validate_metric_name() and validate_dfe_prefix() accept valid names
and warn on invalid names as specified.

This corpus is shared with hyperi-rustlib to ensure identical naming
validation behaviour across languages.
"""

from pathlib import Path

import pytest
import yaml

from hyperi_pylib.metrics.naming import validate_dfe_prefix, validate_metric_name

# Path to the shared fixture file inside the hyperi-ai submodule
_FIXTURES_PATH = Path(__file__).parents[2] / "hyperi-ai" / "test-fixtures" / "metrics-naming.yaml"


def _load_fixtures() -> dict:
    """Load the shared metrics-naming YAML."""
    with _FIXTURES_PATH.open() as f:
        return yaml.safe_load(f)


_fixtures = _load_fixtures()
_valid_cases = _fixtures["valid"]
_invalid_cases = _fixtures["invalid"]


def _valid_ids(cases: list[dict]) -> list[str]:
    return [c["name"] for c in cases]


def _invalid_ids(cases: list[dict]) -> list[str]:
    return [c["name"] for c in cases]


# ---------------------------------------------------------------------------
# Valid cases — both validators must return no warnings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _valid_cases, ids=_valid_ids(_valid_cases))
def test_valid_metric_name_no_warnings(case: dict) -> None:
    """Valid metric names produce no warnings from validate_metric_name."""
    warnings = validate_metric_name(case["name"], case["type"])
    assert warnings == [], f"[{case['name']}] Expected no warnings for valid metric but got: {warnings}"


@pytest.mark.parametrize("case", _valid_cases, ids=_valid_ids(_valid_cases))
def test_valid_dfe_prefix_no_warnings(case: dict) -> None:
    """Valid metric names produce no warnings from validate_dfe_prefix."""
    warnings = validate_dfe_prefix(case["name"], case["app"])
    assert warnings == [], f"[{case['name']}] Expected no prefix warnings for valid metric but got: {warnings}"


# ---------------------------------------------------------------------------
# Invalid cases — at least one validator must return a warning
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _invalid_cases, ids=_invalid_ids(_invalid_cases))
def test_invalid_metric_produces_warning(case: dict) -> None:
    """
    Invalid metric names produce at least one warning from validate_metric_name
    or validate_dfe_prefix (or both).

    The fixture's 'reason' field documents which rule is violated.
    """
    naming_warnings = validate_metric_name(case["name"], case["type"])
    prefix_warnings = validate_dfe_prefix(case["name"], case["app"])
    all_warnings = naming_warnings + prefix_warnings

    assert len(all_warnings) > 0, (
        f"[{case['name']}] Expected at least one warning for invalid metric.\n"
        f"  reason:   {case['reason']}\n"
        f"  name:     {case['name']!r}\n"
        f"  app:      {case['app']!r}\n"
        f"  type:     {case['type']!r}\n"
        f"  warnings: {all_warnings}"
    )


# ---------------------------------------------------------------------------
# Fixture integrity checks
# ---------------------------------------------------------------------------


def test_fixture_file_exists() -> None:
    """Verify the shared fixture file is present (catches broken submodule paths)."""
    assert _FIXTURES_PATH.exists(), f"Fixture file not found: {_FIXTURES_PATH}"


def test_fixture_has_valid_and_invalid_sections() -> None:
    """Verify the fixture YAML has both valid and invalid sections with entries."""
    assert "valid" in _fixtures
    assert "invalid" in _fixtures
    assert len(_fixtures["valid"]) > 0
    assert len(_fixtures["invalid"]) > 0


def test_fixture_entries_have_required_keys() -> None:
    """Every entry must have name, app, and type fields."""
    required = {"name", "app", "type"}
    for entry in _valid_cases:
        missing = required - set(entry)
        assert not missing, f"Valid entry missing keys {missing}: {entry}"
    for entry in _invalid_cases:
        missing = required - set(entry)
        assert not missing, f"Invalid entry missing keys {missing}: {entry}"
        assert "reason" in entry, f"Invalid entry missing 'reason': {entry}"
