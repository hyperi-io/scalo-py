# Project:   hyperi-pylib
# File:      tests/unit/deployment/test_contract_identity_parity.py
# Purpose:   Verify ContractIdentity byte-equivalence against the shared
#            cross-language golden fixture
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Cross-language parity test for Contract Identity v1.

Loads ``tests/fixtures/contract-parity/v1-output.txt`` and asserts the
pylib ``ContractIdentity`` produces byte-identical output for each
section. Rustlib's parity test consumes the same file.

When a local rustlib checkout has its own copy of the golden file (post
rustlib pathfind), this test additionally diffs the two copies and
fails on any divergence -- a guardrail against the vendored copy
drifting from the upstream source.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from hyperi_pylib.deployment.contract_identity import ContractIdentity

GOLDEN_PATH = Path(__file__).parent.parent.parent / "fixtures" / "contract-parity" / "v1-output.txt"

RUSTLIB_GOLDEN_PATH = Path("/projects/hyperi-rustlib/tests/fixtures/contract-parity/v1-output.txt")

# Canonical test inputs -- MUST match the golden file's encoded values.
GOLDEN_SHA = "0123456789abcdef0123456789abcdef01234567"
GOLDEN_REF = "ghcr.io/hyperi-io/dfe-loader:v2.7.3"


def _parse_golden(text: str) -> dict[str, str]:
    """Split a `=== section ===`-delimited file into a dict of sections."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            if current is not None:
                sections[current] = "\n".join(buf)
            current = line.removeprefix("=== ").removesuffix(" ===")
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def test_golden_fixture_exists() -> None:
    assert GOLDEN_PATH.exists(), f"missing golden fixture: {GOLDEN_PATH}"


def test_dockerfile_labels_match_golden() -> None:
    golden = _parse_golden(GOLDEN_PATH.read_text(encoding="utf-8"))
    ident = ContractIdentity(source_commit=GOLDEN_SHA, image_ref=GOLDEN_REF)
    actual = ident.as_dockerfile_labels()
    expected = golden["dockerfile-labels"]
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(), lineterm="", fromfile="golden", tofile="pylib"
            )
        )
        pytest.fail(f"dockerfile-labels drift:\n{diff}")


@pytest.mark.parametrize("indent", [0, 2, 4])
def test_yaml_annotations_match_golden(indent: int) -> None:
    golden = _parse_golden(GOLDEN_PATH.read_text(encoding="utf-8"))
    ident = ContractIdentity(source_commit=GOLDEN_SHA, image_ref=GOLDEN_REF)
    actual = ident.as_yaml_annotations(indent=indent)
    expected = golden[f"yaml-annotations-indent-{indent}"]
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(), lineterm="", fromfile="golden", tofile="pylib"
            )
        )
        pytest.fail(f"yaml-annotations-indent-{indent} drift:\n{diff}")


def test_golden_file_has_lf_line_endings() -> None:
    raw = GOLDEN_PATH.read_bytes()
    assert b"\r\n" not in raw, "golden fixture must use LF line endings"


def test_vendored_golden_matches_rustlib_when_available() -> None:
    """If local rustlib exposes its golden, our vendored copy must match it.

    Skipped (not failed) when rustlib's golden isn't on disk -- per the
    2026-05-22 direction, rustlib lands first; until then there's
    nothing to diff against.
    """
    if not RUSTLIB_GOLDEN_PATH.exists():
        pytest.skip(f"rustlib golden not at {RUSTLIB_GOLDEN_PATH}; vendored pylib copy is the current source of truth")
    pylib = GOLDEN_PATH.read_text(encoding="utf-8")
    rustlib = RUSTLIB_GOLDEN_PATH.read_text(encoding="utf-8")
    if pylib != rustlib:
        diff = "\n".join(
            difflib.unified_diff(
                rustlib.splitlines(), pylib.splitlines(), lineterm="", fromfile="rustlib", tofile="pylib-vendored"
            )
        )
        pytest.fail(f"vendored copy diverged from rustlib upstream:\n{diff}")
