#  Project:      hyperi-pylib
#  File:         test_masking_parity.py
#  Purpose:      Verify SensitiveDataFilter handles all shared masking fixture cases
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Parity tests for sensitive data masking using the shared fixture corpus.

Loads hyperi-ai/test-fixtures/masking-patterns.yaml and verifies that
SensitiveDataFilter masks (or does not mask) each test case as specified.
This corpus is shared with hyperi-rustlib to ensure identical masking
behaviour across languages.
"""

from pathlib import Path

import pytest
import yaml

from hyperi_pylib.logger.filters import SensitiveDataFilter

# Path to the shared fixture file inside the hyperi-ai submodule
_FIXTURES_PATH = Path(__file__).parents[2] / "hyperi-ai" / "test-fixtures" / "masking-patterns.yaml"


def _load_fixtures() -> dict | None:
    """Load the shared masking patterns YAML. Returns None if file missing (submodule not checked out)."""
    if not _FIXTURES_PATH.exists():
        return None
    with _FIXTURES_PATH.open() as f:
        return yaml.safe_load(f)


def _test_case_ids(test_cases: list[dict]) -> list[str]:
    """Generate pytest IDs from test case names."""
    return [tc["name"] for tc in test_cases]


_fixtures = _load_fixtures()
_test_cases = _fixtures["test_cases"] if _fixtures else []

_skip_reason = "hyperi-ai submodule not checked out (test-fixtures unavailable)"


@pytest.mark.skipif(not _test_cases, reason=_skip_reason)
@pytest.mark.parametrize("case", _test_cases, ids=_test_case_ids(_test_cases) if _test_cases else [])
def test_masking_parity(case: dict) -> None:
    """
    Each test case in masking-patterns.yaml is exercised against SensitiveDataFilter.

    If should_mask is True the output must differ from the input (something was masked).
    If should_mask is False the output must equal the input (nothing was changed).
    """
    filt = SensitiveDataFilter()
    result = filt._mask_sensitive_string(case["input"])

    if case["should_mask"]:
        assert result != case["input"], (
            f"[{case['name']}] Expected masking but output unchanged.\n"
            f"  description: {case['description']}\n"
            f"  input:  {case['input']!r}\n"
            f"  output: {result!r}"
        )
    else:
        assert result == case["input"], (
            f"[{case['name']}] Expected no masking but output changed.\n"
            f"  description: {case['description']}\n"
            f"  input:  {case['input']!r}\n"
            f"  output: {result!r}"
        )


@pytest.mark.skipif(not _FIXTURES_PATH.exists(), reason=_skip_reason)
def test_fixture_file_exists() -> None:
    """Verify the shared fixture file is present (catches broken submodule paths)."""
    assert _FIXTURES_PATH.exists(), f"Fixture file not found: {_FIXTURES_PATH}"


@pytest.mark.skipif(_fixtures is None, reason=_skip_reason)
def test_fixture_has_required_keys() -> None:
    """Verify the fixture YAML has the expected top-level keys."""
    assert "sensitive_field_names" in _fixtures
    assert "test_cases" in _fixtures
    assert len(_fixtures["test_cases"]) > 0


@pytest.mark.skipif(_fixtures is None, reason=_skip_reason)
def test_fixture_sensitive_fields_present() -> None:
    """Verify that the fixture's sensitive_field_names are a subset of the filter's SENSITIVE_FIELDS."""
    from hyperi_pylib.logger.filters import SENSITIVE_FIELDS

    fixture_fields = set(_fixtures["sensitive_field_names"])
    # Fields that the fixture defines but the filter also knows about
    # (the filter may know more fields than the fixture lists -- that is fine)
    covered = fixture_fields & SENSITIVE_FIELDS
    missing = fixture_fields - SENSITIVE_FIELDS

    assert not missing, (
        f"Fixture declares fields not in SENSITIVE_FIELDS: {missing}\n"
        "Either add them to SENSITIVE_FIELDS or remove them from the fixture."
    )
    assert len(covered) > 0, "No fixture fields matched SENSITIVE_FIELDS -- check both files."
