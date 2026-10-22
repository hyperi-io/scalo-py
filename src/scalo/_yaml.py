# Project:   scalo
# File:      _yaml.py
# Purpose:   The safe YAML loader every scalo reader parses with: libyaml where PyYAML has it
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED
"""Parse YAML with PyYAML's safe loader, through libyaml when PyYAML was built with it.

libyaml builds the same documents as the pure-Python loader about nine times faster,
which is what a directory of a few thousand files waits on at startup. A PyYAML with
no libyaml falls back to the pure-Python loader.
"""

from typing import IO, Any

import yaml

SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
"""``yaml.CSafeLoader`` where PyYAML carries libyaml, else ``yaml.SafeLoader``."""


def safe_load(stream: str | bytes | IO[str] | IO[bytes]) -> Any:
    """The first YAML document in *stream*, as ``yaml.safe_load`` reads it.

    Raises:
        yaml.YAMLError: The stream is not valid YAML.
    """
    return yaml.load(stream, Loader=SafeLoader)  # noqa: S506
