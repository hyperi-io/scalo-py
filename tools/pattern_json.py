#!/usr/bin/env python3
#  Project:   scalo
#  File:      tools/pattern_json.py
#  Purpose:   Write the JSON sidecar for each bundled pattern TOML
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Write ``<name>.json`` beside each bundled pattern TOML in ``src/scalo/data``.

The runtime reads the JSON because it loads about 30x faster than ``tomllib``
parses (see ``scalo.logger.scrub._bundled``). ``tools/vendor_patterns.sh`` runs
this after it copies the TOML files in.

Usage:
    python3 tools/pattern_json.py           # rewrite the sidecars
    python3 tools/pattern_json.py --check   # exit 1 when one is stale
"""

import json
import sys
import tomllib
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "scalo" / "data"
TABLES = ("gitleaks", "national_ids")


def render(name: str) -> str:
    """Return the JSON text for ``<name>.toml``."""
    with (DATA_DIR / f"{name}.toml").open("rb") as f:
        return json.dumps(tomllib.load(f), separators=(",", ":"), ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    """Rewrite the sidecars, or with ``--check`` report the stale ones."""
    check = "--check" in argv
    stale = 0
    for name in TABLES:
        path = DATA_DIR / f"{name}.json"
        text = render(name)
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        if check:
            print(f"stale: {path.name} does not match {name}.toml", file=sys.stderr)
            stale += 1
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.name}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
