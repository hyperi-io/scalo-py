# Project:   scalo
# File:      tests/unit/deployment/test_contract_identity_parity.py
# Purpose:   Verify ContractIdentity byte-equivalence against the shared
#            cross-language golden fixture
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Cross-language parity test for Contract Identity v1.

Loads ``tests/fixtures/contract-parity/v1-output.txt`` and asserts the
scalo_py ``ContractIdentity`` produces byte-identical output for each
section. Rustlib's parity test consumes the same file.

When ``SCALO_RS_GOLDEN_PATH`` points at the scalo-rs copy of the golden
file, this test additionally diffs the two copies and fails on any
divergence -- a guardrail against the vendored copy drifting from the
upstream source.
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path

import pytest

from scalo.deployment.contract_identity import DEFAULT_LABEL_NAMESPACE, ContractIdentity

GOLDEN_PATH = Path(__file__).parent.parent.parent / "fixtures" / "contract-parity" / "v1-output.txt"

SCALO_RS_GOLDEN_ENV = "SCALO_RS_GOLDEN_PATH"

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
    actual = ident.as_dockerfile_labels(DEFAULT_LABEL_NAMESPACE)
    expected = golden["dockerfile-labels"]
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(), lineterm="", fromfile="golden", tofile="scalo_py"
            )
        )
        pytest.fail(f"dockerfile-labels drift:\n{diff}")


@pytest.mark.parametrize("indent", [0, 2, 4])
def test_yaml_annotations_match_golden(indent: int) -> None:
    golden = _parse_golden(GOLDEN_PATH.read_text(encoding="utf-8"))
    ident = ContractIdentity(source_commit=GOLDEN_SHA, image_ref=GOLDEN_REF)
    actual = ident.as_yaml_annotations(DEFAULT_LABEL_NAMESPACE, indent=indent)
    expected = golden[f"yaml-annotations-indent-{indent}"]
    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(), actual.splitlines(), lineterm="", fromfile="golden", tofile="scalo_py"
            )
        )
        pytest.fail(f"yaml-annotations-indent-{indent} drift:\n{diff}")


def test_golden_file_has_lf_line_endings() -> None:
    raw = GOLDEN_PATH.read_bytes()
    assert b"\r\n" not in raw, "golden fixture must use LF line endings"


def test_vendored_golden_matches_scalo_rs_when_available() -> None:
    """If SCALO_RS_GOLDEN_PATH names scalo-rs's golden, our vendored copy must match it.

    Skipped (not failed) when the variable is unset or the file is missing,
    because there is nothing to diff against.
    """
    configured = os.environ.get(SCALO_RS_GOLDEN_ENV)
    if not configured:
        pytest.skip(
            f"{SCALO_RS_GOLDEN_ENV} is not set; set it to scalo-rs's tests/fixtures/contract-parity/v1-output.txt"
        )
    scalo_rs_path = Path(configured)
    if not scalo_rs_path.is_file():
        pytest.skip(f"{SCALO_RS_GOLDEN_ENV} points at {scalo_rs_path}, which does not exist")
    scalo_py = GOLDEN_PATH.read_text(encoding="utf-8")
    scalo_rs = scalo_rs_path.read_text(encoding="utf-8")
    if scalo_py != scalo_rs:
        diff = "\n".join(
            difflib.unified_diff(
                scalo_rs.splitlines(),
                scalo_py.splitlines(),
                lineterm="",
                fromfile="scalo_rs",
                tofile="scalo_py-vendored",
            )
        )
        pytest.fail(f"vendored copy diverged from scalo_rs upstream:\n{diff}")
