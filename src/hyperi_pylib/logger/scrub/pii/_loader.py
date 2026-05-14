#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/_loader.py
#  Purpose:   Load the bundled national_ids.toml and build validator instances
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Load the bundled ``national_ids.toml`` and build validator instances.

The TOML is bundled in pylib's wheel at
``hyperi_pylib/data/national_ids.toml`` — vendored from the
canonical source in
``hyperi-ai/standards/patterns/national_ids.toml`` (see spec §3.0
for vendoring discipline).

This module is the only place that reads the TOML; the rest of the
scrub code consumes the resulting validator instances.
"""

from __future__ import annotations

import tomllib
import warnings
from importlib import resources
from pathlib import Path
from typing import Any

from ..labeler import LabelFn
from ..metrics import ScrubMetrics
from ._base import _Validator
from ._dynamic import _DynamicValidator


def load_registry(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load and parse ``national_ids.toml``.

    Args:
        path: optional path to a custom registry TOML. When ``None``
            (default), reads the package-bundled
            ``hyperi_pylib/data/national_ids.toml``.

    Returns:
        Mapping of ``{country_code: {id_name: entry_dict}}``.
    """
    if path is not None:
        with path.open("rb") as f:
            return tomllib.load(f)

    # Bundled file — read via importlib.resources so it works whether
    # pylib is installed as a wheel or run from source.
    resource = resources.files("hyperi_pylib") / "data" / "national_ids.toml"
    with resource.open("rb") as f:
        return tomllib.load(f)


def build_national_id_validators(
    *,
    registry: dict[str, dict[str, Any]] | None = None,
    enabled_countries: list[str] | None = None,
    labeler: LabelFn | None = None,
    metrics: ScrubMetrics | None = None,
) -> list[_Validator]:
    """Build validator instances for enabled national-ID entries.

    Args:
        registry: loaded TOML registry (see :func:`load_registry`). If
            ``None``, the bundled registry is loaded.
        enabled_countries: list of country codes (ISO 3166-1 alpha-2,
            lowercase) whose entries are eligible. Entries within
            those countries are still gated on ``enabled = true`` in
            the TOML. If ``None``, all countries are considered.

    Returns:
        List of :class:`_DynamicValidator` instances, ready to feed
        into :class:`LayeredScrubber`.

    Each entry must have:

    - ``enabled = true``
    - non-empty ``detection_regex``
    - either ``stdnum_module`` or ``local_validator``

    Entries failing those checks are silently skipped (the registry
    file ships many ``enabled = false`` stubs).

    Misconfigured entries (e.g. unimportable stdnum_module) emit a
    one-time warning and are skipped — never raise to the caller.
    Per spec §5.1, broken scrubber components must not break logging.
    """
    if registry is None:
        registry = load_registry()

    if enabled_countries is not None:
        enabled_countries_lc = {c.lower() for c in enabled_countries}
    else:
        enabled_countries_lc = None

    validators: list[_Validator] = []
    for country, ids in registry.items():
        if enabled_countries_lc is not None and country.lower() not in enabled_countries_lc:
            continue
        if not isinstance(ids, dict):
            continue
        for id_name, entry in ids.items():
            if not isinstance(entry, dict):
                continue
            if not entry.get("enabled", False):
                continue
            if not entry.get("detection_regex"):
                continue
            try:
                # Tag with the country.id key for debugging
                entry_with_key = dict(entry)
                entry_with_key["_entry_key"] = f"{country}.{id_name}"
                validators.append(_DynamicValidator(entry_with_key, labeler=labeler, metrics=metrics))
            except (ValueError, ImportError) as e:
                warnings.warn(
                    f"national_ids entry {country}.{id_name} not loadable: {e}. Skipping (non-blocking).",
                    RuntimeWarning,
                    stacklevel=2,
                )

    return validators
