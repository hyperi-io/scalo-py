#  Project:      scalo
#  File:         test_masking_parity.py
#  Purpose:      Verify SensitiveDataFilter handles all shared masking fixture cases
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""
Masking corpus tests: every case in the shared field-masking corpus is run
against SensitiveDataFilter.

The corpus is vendored at ``scalo/data/masking-patterns.yaml`` from
``hyperi-ai/standards/patterns/`` by ``tools/vendor_patterns.sh``, the same route
``pii_test_fixtures.toml`` takes. It used to be read from a
``scalo-spec/test-fixtures/`` submodule that does not exist -- no scalo-spec
repo, no ``.gitmodules``, no checkout -- so every case here skipped in every
environment including CI.

Intended as a cross-language corpus, and scalo-rs does not read it yet, so
passing here proves the Python behaviour only.
"""

from importlib import resources

import pytest
import yaml

from scalo.logger.filters import SensitiveDataFilter

_FIXTURES_PATH = resources.files("scalo") / "data" / "masking-patterns.yaml"


def _load_fixtures() -> dict | None:
    """Load the vendored masking corpus. None when the file is absent."""
    if not _FIXTURES_PATH.is_file():
        return None
    return yaml.safe_load(_FIXTURES_PATH.read_text(encoding="utf-8"))


def _test_case_ids(test_cases: list[dict]) -> list[str]:
    """Generate pytest IDs from test case names."""
    return [tc["name"] for tc in test_cases]


_fixtures = _load_fixtures()
_test_cases = _fixtures["test_cases"] if _fixtures else []

_skip_reason = "masking corpus not vendored (run tools/vendor_patterns.sh)"


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


def test_fixture_file_exists() -> None:
    """The corpus must be present, or every case above is vacuous.

    Unguarded on purpose: an absent corpus is the failure mode this test exists
    to report, so guarding it on the corpus being present would leave it
    incapable of failing -- which is how it read before, as
    ``@skipif(not _FIXTURES_PATH.exists())``.
    """
    assert _FIXTURES_PATH.is_file(), f"Masking corpus not found: {_FIXTURES_PATH}"


def test_corpus_has_positive_and_negative_cases() -> None:
    """Both directions must be covered.

    A masker that redacts everything passes an all-positive corpus, and one that
    redacts nothing passes an all-negative one.
    """
    assert _test_cases, "corpus has no test cases"
    assert any(c["should_mask"] for c in _test_cases), "no should_mask: true cases"
    assert any(not c["should_mask"] for c in _test_cases), "no should_mask: false cases"


@pytest.mark.skipif(_fixtures is None, reason=_skip_reason)
def test_fixture_has_required_keys() -> None:
    """Verify the fixture YAML has the expected top-level keys."""
    assert "sensitive_field_names" in _fixtures
    assert "test_cases" in _fixtures
    assert len(_fixtures["test_cases"]) > 0


@pytest.mark.skipif(_fixtures is None, reason=_skip_reason)
def test_fixture_sensitive_fields_present() -> None:
    """Verify that the fixture's sensitive_field_names are a subset of the filter's SENSITIVE_FIELDS."""
    from scalo.logger.filters import SENSITIVE_FIELDS

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
