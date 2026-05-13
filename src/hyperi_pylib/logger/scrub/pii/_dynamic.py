#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/_dynamic.py
#  Purpose:   Dynamic validator constructed from TOML registry entries
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Dynamic validator built from a TOML registry entry.

Generic Scrubber-Protocol implementation that takes its label,
regex, keywords, and validation function from a TOML entry rather
than hard-coding them in a per-country class.

Spec §3.4 and §9.2 describe the entry shape. See
``src/hyperi_pylib/data/national_ids.toml`` for the canonical
registry shipped with pylib.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from typing import Any

from ..labeler import LabelFn
from ._base import _Validator


class _DynamicValidator(_Validator):
    """Validator whose label/regex/keywords/validator come from a TOML entry.

    Construction takes a single dict in the registry-entry shape:

    .. code-block:: toml

        [au.abn]
        stdnum_module = "stdnum.au.abn"
        country_code = "AU"
        id_description = "ABN (Australian Business Number)"
        redaction_label = "AU_ABN"
        enabled = true
        context_required = true
        keywords = ["abn", "australian business number"]
        detection_regex = '\\b\\d{2}[ ]?\\d{3}[ ]?\\d{3}[ ]?\\d{3}\\b'

    Either ``stdnum_module`` (e.g. ``"stdnum.au.abn"``) or
    ``local_validator`` (e.g. ``"hyperi_pylib.logger.scrub.pii.au_medicare:_is_valid_medicare"``)
    MUST be present. The first is dynamically imported and its
    ``is_valid`` function used; the second is a colon-separated
    ``module:attribute`` reference resolved at construction.
    """

    def __init__(
        self,
        entry: dict[str, Any],
        labeler: LabelFn | None = None,
    ) -> None:
        super().__init__(labeler=labeler)
        self.LABEL: str = entry["redaction_label"]
        self.PATTERN: re.Pattern[str] = re.compile(entry["detection_regex"])
        self.KEYWORDS: tuple[str, ...] = tuple(entry.get("keywords", ()))
        self.entry_key: str = entry.get("_entry_key", "")
        self._validate_fn: Callable[[str], bool] = _resolve_validator(entry)

    def validate(self, candidate: str) -> bool:
        try:
            return bool(self._validate_fn(candidate))
        except Exception:  # pragma: no cover — stdnum raises for bad input
            return False

    def __repr__(self) -> str:
        kind = "context-required" if self.KEYWORDS else "strong-structural"
        if self.entry_key:
            return f"_DynamicValidator(entry={self.entry_key!r}, {kind}, label={self.LABEL!r})"
        return f"_DynamicValidator({kind}, label={self.LABEL!r})"


def _resolve_validator(entry: dict[str, Any]) -> Callable[[str], bool]:
    """Resolve an entry's validator function via stdnum_module or local_validator."""
    if "stdnum_module" in entry:
        module_name = entry["stdnum_module"]
        try:
            mod = importlib.import_module(module_name)
        except ImportError as e:
            raise ValueError(
                f"national_ids entry refers to missing module {module_name!r}: {e}"
            ) from e
        if not hasattr(mod, "is_valid"):
            raise ValueError(
                f"stdnum module {module_name!r} has no is_valid function"
            )
        return mod.is_valid

    if "local_validator" in entry:
        ref = entry["local_validator"]
        try:
            module_name, attr_name = ref.split(":", 1)
        except ValueError as e:
            raise ValueError(
                f"local_validator must be 'module:attribute', got {ref!r}"
            ) from e
        try:
            mod = importlib.import_module(module_name)
        except ImportError as e:
            raise ValueError(
                f"local_validator module {module_name!r} not importable: {e}"
            ) from e
        fn = getattr(mod, attr_name, None)
        if fn is None or not callable(fn):
            raise ValueError(
                f"local_validator {ref!r} not callable or missing"
            )
        return fn

    raise ValueError(
        "registry entry must have either 'stdnum_module' or 'local_validator'"
    )
