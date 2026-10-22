# Project:   scalo
# File:      tests/unit/test_yaml_loader.py
# Purpose:   scalo's YAML readers parse with libyaml and build the documents the pure-Python loader builds
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""The safe loader every scalo reader goes through, against PyYAML's pure-Python one.

libyaml is only worth taking if nothing a reader gets back changes, so each case parses
the same text both ways and compares the documents.
"""

import importlib
import textwrap
from pathlib import Path

import pytest
import yaml
from yaml.constructor import ConstructorError

import scalo._yaml as scalo_yaml
from scalo._yaml import safe_load
from scalo.config import DirectoryConfigStore

TESTS = Path(__file__).resolve().parents[1]

# Each YAML 1.1 shape a config or schema file carries, as PyYAML's safe loader reads it.
SHAPES = {
    "scalars": """
        int: 42
        octal: 0o17
        legacy_octal: 017
        hex: 0x1F
        float: 3.14
        exponent: 1e3
        infinity: .inf
        not_a_number: .nan
        booleans: [true, False, yes, No, on, OFF]
        nulls: [null, ~, ]
        date: 2026-10-22
        timestamp: 2026-10-22T11:04:25.283394Z
        version_string: "1.0"
        bare_version: 1.0.0
        """,
    "strings": """
        plain: hello world
        single: 'it''s quoted'
        double: "tab\\tand unicode \\u00e9 and emoji \\U0001F600"
        literal: |
          line one
            indented
          line three
        folded: >-
          folded onto
          one line
        colon_in_value: "http://example.com:8080/path"
        non_ascii: Zürich, 東京
        """,
    "structure": """
        defaults: &defaults
          retries: 3
          timeout: 30
        service:
          <<: *defaults
          timeout: 60
        alias_list: [*defaults, *defaults]
        nested:
          - name: a
            tags: [x, y]
          - name: b
            tags: {}
        empty_map: {}
        empty_list: []
        set_like: !!set {a: null, b: null}
        binary: !!binary aGVsbG8=
        """,
    "empty": "",
    "only_comment": "# nothing here\n",
    "top_level_list": "- a\n- b\n",
    "explicit_document": "---\nkey: value\n...\n",
}


def _both(text: str) -> tuple[object, object]:
    return safe_load(text), yaml.load(text, Loader=yaml.SafeLoader)


def _nan_safe(value: object) -> object:
    """``value`` with NaN replaced by a marker, since NaN never equals itself."""
    if isinstance(value, float) and value != value:
        return "<nan>"
    if isinstance(value, dict):
        return {k: _nan_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_nan_safe(v) for v in value]
    return value


class TestLoader:
    def test_the_installed_pyyaml_parses_through_libyaml(self):
        # Without libyaml every reader falls back to the pure-Python loader, about nine times slower.
        assert yaml.__with_libyaml__
        assert scalo_yaml.SafeLoader is yaml.CSafeLoader

    @pytest.mark.parametrize("shape", sorted(SHAPES))
    def test_each_shape_reads_as_the_pure_python_loader_reads_it(self, shape):
        fast, pure = _both(textwrap.dedent(SHAPES[shape]))
        assert _nan_safe(fast) == _nan_safe(pure)

    def test_every_yaml_fixture_reads_as_the_pure_python_loader_reads_it(self):
        fixtures = sorted([*TESTS.rglob("*.yaml"), *TESTS.rglob("*.yml")])
        assert fixtures, "no YAML fixture to compare"
        for path in fixtures:
            fast, pure = _both(path.read_text(encoding="utf-8"))
            assert _nan_safe(fast) == _nan_safe(pure), path

    def test_a_file_object_reads_like_its_text(self, tmp_path):
        path = tmp_path / "doc.yaml"
        path.write_text(textwrap.dedent(SHAPES["structure"]), encoding="utf-8")
        with path.open(encoding="utf-8") as stream:
            assert safe_load(stream) == safe_load(path.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("broken", ["a: [unclosed\n", "key: value\n  bad: indent\n", "\tkey: tab\n"])
    def test_broken_yaml_raises_a_yaml_error_both_ways(self, broken):
        with pytest.raises(yaml.YAMLError):
            safe_load(broken)
        with pytest.raises(yaml.YAMLError):
            yaml.load(broken, Loader=yaml.SafeLoader)

    def test_a_python_tag_is_refused_as_the_safe_loader_refuses_it(self):
        with pytest.raises(ConstructorError):
            safe_load("!!python/object/apply:os.system ['true']")


class TestFallback:
    def test_a_pyyaml_without_libyaml_reads_with_the_pure_python_loader(self, monkeypatch):
        monkeypatch.delattr(yaml, "CSafeLoader")
        try:
            reloaded = importlib.reload(scalo_yaml)
            assert reloaded.SafeLoader is yaml.SafeLoader
            assert reloaded.safe_load("a: [1, 2]\n") == {"a": [1, 2]}
        finally:
            monkeypatch.undo()
            importlib.reload(scalo_yaml)
        assert scalo_yaml.SafeLoader is yaml.CSafeLoader


class TestDirectoryStore:
    def test_a_tree_of_files_reads_as_the_pure_python_loader_reads_it(self, tmp_path):
        expected: dict[str, object] = {}
        for index in range(300):
            shape = sorted(SHAPES)[index % len(SHAPES)]
            text = textwrap.dedent(SHAPES[shape])
            table = f"group-{index % 7}/doc-{index}"
            path = tmp_path / f"{table}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            pure = yaml.load(text, Loader=yaml.SafeLoader)
            # The store reads an empty file as an empty mapping and skips anything else that is not one.
            if pure is None:
                expected[table] = {}
            elif isinstance(pure, dict):
                expected[table] = pure
        store = DirectoryConfigStore(tmp_path, refresh_interval=0)
        store.start()
        try:
            read = {table: store.get(table) for table in store.list_tables()}
        finally:
            store.stop()

        assert {t: _nan_safe(v) for t, v in read.items() if v is not None} == {
            t: _nan_safe(v) for t, v in expected.items()
        }
