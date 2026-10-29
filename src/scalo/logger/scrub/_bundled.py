#  Project:   scalo
#  File:      src/scalo/logger/scrub/_bundled.py
#  Purpose:   Read a bundled pattern table from its JSON sidecar, falling back to the TOML
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Read the pattern tables bundled in ``scalo/data``.

``gitleaks.toml`` and ``national_ids.toml`` are vendored from hyperi-ai. Parsing
both with ``tomllib`` costs about 30 ms in a fresh process, and ``json`` reads the
same tables in about 1 ms, so ``tools/pattern_json.py`` writes a ``.json`` sidecar
beside each TOML and this module reads that first. A test pins each sidecar to its
TOML, so the TOML stays the source of truth.
"""

import json
import tomllib
from importlib import resources
from typing import Any


def load_bundled_table(name: str) -> dict[str, Any]:
    """Return the parsed table ``scalo/data/<name>.toml``, read from ``<name>.json`` when that loads.

    Args:
        name: File stem under ``scalo/data``, such as ``"gitleaks"``.

    Returns:
        The table as ``tomllib.load`` would parse it.

    Raises:
        OSError: If neither the sidecar nor the TOML can be read.
        tomllib.TOMLDecodeError: If the sidecar cannot be used and the TOML is malformed.
    """
    data_dir = resources.files("scalo") / "data"
    try:
        with (data_dir / f"{name}.json").open("rb") as f:
            return json.load(f)
    except OSError, ValueError:
        pass
    with (data_dir / f"{name}.toml").open("rb") as f:
        return tomllib.load(f)
