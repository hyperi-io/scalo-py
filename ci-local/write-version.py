#!/usr/bin/env python3
"""Extract version from pyproject.toml and write plain VERSION file."""
from pathlib import Path

try:
    import tomli
except ImportError:
    import tomllib as tomli

# Read version from pyproject.toml
pyproject = Path("pyproject.toml")
with open(pyproject, "rb") as f:
    data = tomli.load(f)

version = data["project"]["version"]

# Write plain version to VERSION file
Path("VERSION").write_text(f"{version}\n")
print(f"Wrote VERSION: {version}")
