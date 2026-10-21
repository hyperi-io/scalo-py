#  Project:   scalo
#  File:      src/scalo/cli/openapi/documents.py
#  Purpose:   The one JSON-then-YAML parser behind specs, input documents and object options
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Parse a document handed to the CLI, JSON first and then YAML.

Each caller names the source in its own error: a spec raises ``SpecError``, an
option ``CliUsageError``.
"""

import json
from typing import Any

import yaml


class DocumentError(ValueError):
    """The text is not a document of a kind the caller accepts."""


def read_document(text: str, *, yaml_allowed: bool = True) -> Any:
    """``text`` parsed as JSON, else as YAML when allowed.

    Raises:
        DocumentError: Saying why, as ``not valid JSON: ...`` or ``neither JSON nor YAML: ...``.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if not yaml_allowed:
            raise DocumentError(f"not valid JSON: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DocumentError(f"neither JSON nor YAML: {exc}") from exc
