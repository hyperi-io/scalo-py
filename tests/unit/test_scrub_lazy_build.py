#  Project:   scalo
#  File:      tests/unit/test_scrub_lazy_build.py
#  Purpose:   The default scrubber builds without compiling its secret rules, and scrubs the same
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Lazy secret-rule compilation: a build compiles nothing, and output does not change."""

import importlib.util
import json
import tomllib
from pathlib import Path

import pytest
from common import fake_secrets

import scalo
from scalo.logger.scrub import SecretsScrubber, build_scrubber
from scalo.logger.scrub import _bundled as bundled
from scalo.logger.scrub._bundled import load_bundled_table
from scalo.logger.scrub.gitleaks_toml import GitleaksTomlScrubber

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "patterns"


def tools_render(name: str) -> str:
    """Return the sidecar text ``tools/pattern_json.py`` writes for ``name``."""
    path = Path(__file__).resolve().parents[2] / "tools" / "pattern_json.py"
    spec = importlib.util.spec_from_file_location("pattern_json", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render(name)


_FAKE_SECRETS = [
    getattr(fake_secrets, name)()
    for name in sorted(vars(fake_secrets))
    if not name.startswith("_") and callable(getattr(fake_secrets, name)) and name != "opaque_secret"
]


def _corpus() -> list[str]:
    """Return text that fires secret rules, field-name masking, PII validators and none of them."""
    secret = fake_secrets.opaque_secret()
    texts = [f"deploy used {value} for the push" for value in _FAKE_SECRETS]
    texts.append("nothing to see here, just a log line")
    texts.append("")

    masking = json.loads((FIXTURES / "credential_masking_parity.json").read_text(encoding="utf-8"))
    texts.extend(case["input"].replace("{secret}", secret) for case in masking["text_cases"])

    with (FIXTURES / "pii_test_fixtures.toml").open("rb") as f:
        pii = tomllib.load(f)
    for section in pii.values():
        for key in ("valid", "invalid"):
            texts.extend(f"record {value}" for value in section.get(key, []) if isinstance(value, str))
    return texts


CORPUS = _corpus()


def _l1(scrubber) -> GitleaksTomlScrubber:
    secrets = next(layer for layer in scrubber.layers if isinstance(layer, SecretsScrubber))
    assert isinstance(secrets._inner, GitleaksTomlScrubber)
    return secrets._inner


class TestBundledSidecars:
    @pytest.mark.parametrize("name", ["gitleaks", "national_ids"])
    def test_sidecar_matches_its_toml(self, name):
        """The runtime reads the JSON, so it must say exactly what the vendored TOML says."""
        data_dir = Path(scalo.__file__).parent / "data"
        with (data_dir / f"{name}.toml").open("rb") as f:
            assert load_bundled_table(name) == tomllib.load(f)
        assert (data_dir / f"{name}.json").read_text(encoding="utf-8") == tools_render(name)

    def test_unreadable_sidecar_falls_back_to_the_toml(self, monkeypatch):
        def broken(_fp):
            raise json.JSONDecodeError("broken sidecar", "", 0)

        monkeypatch.setattr(bundled.json, "load", broken)
        assert len(load_bundled_table("gitleaks")["rules"]) >= 200


class TestBuildIsLazy:
    def test_build_compiles_no_rule(self):
        l1 = _l1(build_scrubber())
        assert l1.rule_count >= 200
        assert [r.id for r in l1._rules if r.pattern is not None] == []
        assert l1.skipped_rules == []

    def test_scrub_compiles_only_rules_whose_keywords_hit(self):
        l1 = _l1(build_scrubber())
        l1.scrub(f"push with {fake_secrets.github_classic_pat()}")
        compiled = {r.id for r in l1._rules if r.pattern is not None}
        assert "github-pat" in compiled
        assert len(compiled) < l1.rule_count / 4
        for rule in l1._rules:
            if rule.id in compiled:
                assert not rule.keywords or any(k in "push with ghp_" for k in rule.keywords)

    def test_text_that_hits_no_keyword_compiles_only_keywordless_rules(self):
        l1 = _l1(build_scrubber())
        l1.scrub("zzz")
        assert [r.id for r in l1._rules if r.pattern is not None and r.keywords] == []


@pytest.fixture(scope="module")
def precompiled():
    scrubber = build_scrubber()
    _l1(scrubber).compile_all()
    return scrubber


@pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
def test_lazy_and_precompiled_scrubbers_agree(text, precompiled):
    """A scrubber built lazily redacts exactly what one with every rule compiled up front does."""
    assert build_scrubber().scrub(text) == precompiled.scrub(text)
