#  Project:      scalo
#  File:         test_metrics_naming_parity.py
#  Purpose:      Verify validate_metric_name and validate_dfe_prefix against shared corpus
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Metric naming corpus tests: every entry in the shared naming corpus is run
against validate_metric_name() and validate_dfe_prefix().

The corpus is vendored at ``scalo/data/metrics-naming.yaml`` from
``hyperi-ai/standards/patterns/`` by ``tools/vendor_patterns.sh``, the same route
``pii_test_fixtures.toml`` takes. It used to be read from a
``scalo-spec/test-fixtures/`` submodule that does not exist, so every entry here
skipped in every environment including CI.

Intended as a cross-language corpus, and scalo-rs does not read it yet, so
passing here proves the Python behaviour only.
"""

from importlib import resources

import pytest
import yaml

from scalo.metrics.naming import validate_dfe_prefix, validate_metric_name

_FIXTURES_PATH = resources.files("scalo") / "data" / "metrics-naming.yaml"


def _load_fixtures() -> dict | None:
    """Load the vendored naming corpus. None when the file is absent."""
    if not _FIXTURES_PATH.is_file():
        return None
    return yaml.safe_load(_FIXTURES_PATH.read_text(encoding="utf-8"))


_fixtures = _load_fixtures()
_valid_cases = _fixtures["valid"] if _fixtures else []
_invalid_cases = _fixtures["invalid"] if _fixtures else []

_skip_reason = "naming corpus not vendored (run tools/vendor_patterns.sh)"


def _valid_ids(cases: list[dict]) -> list[str]:
    return [c["name"] for c in cases]


def _invalid_ids(cases: list[dict]) -> list[str]:
    return [c["name"] for c in cases]


# ---------------------------------------------------------------------------
# Valid cases -- both validators must return no warnings
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _valid_cases, reason=_skip_reason)
@pytest.mark.parametrize("case", _valid_cases, ids=_valid_ids(_valid_cases) if _valid_cases else [])
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
# Invalid cases -- at least one validator must return a warning
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _invalid_cases, reason=_skip_reason)
@pytest.mark.parametrize("case", _invalid_cases, ids=_invalid_ids(_invalid_cases) if _invalid_cases else [])
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
    """The corpus must be present, or every entry above is vacuous.

    Unguarded on purpose: an absent corpus is the failure mode this test exists
    to report, so guarding it on the corpus being present would leave it
    incapable of failing -- which is how it read before, as
    ``@skipif(not _FIXTURES_PATH.exists())``.
    """
    assert _FIXTURES_PATH.is_file(), f"Naming corpus not found: {_FIXTURES_PATH}"


@pytest.mark.skipif(_fixtures is None, reason=_skip_reason)
def test_fixture_has_valid_and_invalid_sections() -> None:
    """Verify the fixture YAML has both valid and invalid sections with entries."""
    assert "valid" in _fixtures
    assert "invalid" in _fixtures
    assert len(_fixtures["valid"]) > 0
    assert len(_fixtures["invalid"]) > 0


@pytest.mark.skipif(_fixtures is None, reason=_skip_reason)
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
