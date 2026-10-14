#  Project:   scalo
#  File:      tests/unit/test_credential_masking_parity.py
#  Purpose:   Run every case of the shared credential-masking corpus against scalo-py
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Every entry of the credential-masking corpus scalo-rs runs too, run against scalo-py.

The corpus is scalo-rs's ``tests/fixtures/credential_masking_parity.json``,
vendored to ``tests/fixtures/patterns/`` by ``tools/vendor_patterns.sh``.
Placeholders are filled the way its ``_comment`` says, so no credential-shaped
literal sits on disk.
"""

import json
import sys
from pathlib import Path

import pytest
from common.fake_secrets import opaque_secret
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.logger.filters import MASK_VALUE, is_credential_name, mask_url_userinfo
from scalo.logger.logger import setup
from scalo.logger.scrub import FieldNameScrubber

CORPUS_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "patterns" / "credential_masking_parity.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
SECRET = opaque_secret("credname")

SECTIONS = ("parent_cases", "text_cases", "url_cases", "structured_cases", "coarse_cases")


def _fill(text: str, mask: str = MASK_VALUE) -> str:
    """Replace the corpus placeholders with the runtime secret, the window filler and ``mask``."""
    text = text.replace("{pw}", "p" + "@" + SECRET).replace("{secret}", SECRET).replace("{window}", "x" * 4096)
    return text.replace("{mask}", mask)


def _fill_value(value):
    """Fill the placeholders in every string of a JSON value."""
    return json.loads(_fill(json.dumps(value)))


def _cases(section: str) -> list:
    return [pytest.param(case, id=case["id"]) for case in CORPUS[section]]


def _names(*lists: str) -> list:
    return [pytest.param(name, id=f"{name_list}:{name}") for name_list in lists for name in CORPUS["names"][name_list]]


@pytest.fixture
def json_logger(monkeypatch):
    """Route the logger's JSON output to a stream the test reads back."""
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    stream = StreamDouble(False)
    with preserved_stdlib_logging():
        monkeypatch.setattr(sys, "stderr", stream)
        setup(otel_tracing=False, log_format="json")
        yield stream
        logger.remove()


@pytest.mark.parametrize("section", SECTIONS)
def test_every_section_holds_cases(section):
    assert CORPUS[section], f"{section} is empty"


@pytest.mark.parametrize("name", _names("credential", "spellings_of_api_key", "previous_scalo_rs_defaults"))
def test_a_credential_name_is_a_credential(name):
    assert is_credential_name(name)


@pytest.mark.parametrize("name", _names("shown", "no_term"))
def test_a_setting_name_is_not_a_credential(name):
    assert not is_credential_name(name)


@pytest.mark.parametrize("case", _cases("parent_cases"))
def test_a_parent_qualifies_only_a_bare_key_or_value(case):
    assert is_credential_name(case["name"], case["parent"]) is case["credential"]


@pytest.mark.parametrize("case", _cases("text_cases"))
def test_text_is_masked_as_the_corpus_says(case):
    assert FieldNameScrubber().scrub(_fill(case["input"])) == _fill(case["expected"])


@pytest.mark.parametrize("case", _cases("url_cases"))
def test_a_url_is_masked_as_the_corpus_says(case):
    mask = _fill(case["mask"])

    masked = mask_url_userinfo(_fill(case["input"]), mask, keep_user=case["keep_user"])

    assert masked == _fill(case["expected"], mask)


@pytest.mark.parametrize("case", _cases("coarse_cases"))
def test_a_coarse_case_is_masked_or_left_as_the_corpus_says(case):
    text = _fill(case["input"])

    assert (FieldNameScrubber().scrub(text) != text) is case["should_mask"]


@pytest.mark.parametrize("case", _cases("structured_cases"))
def test_record_fields_are_masked_as_the_corpus_says(json_logger, case):
    expected = _fill_value(case["expected"])

    logger.warning("corpus", **_fill_value(case["input"]))

    lines = json_logger.getvalue().splitlines()
    assert len(lines) == 1, lines
    fields = json.loads(lines[0])["fields"]
    assert {key: fields.get(key) for key in expected} == expected
    assert SECRET not in json_logger.getvalue()
