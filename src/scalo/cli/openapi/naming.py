#  Project:   scalo
#  File:      src/scalo/cli/openapi/naming.py
#  Purpose:   Derive a command's group path and verb from a path, for specs without x-scalo
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Name a command from its REST path and method when the spec says nothing better.

An operation that carries ``x-scalo`` or a dotted ``operationId`` is named by that.
Anything else falls back to the path, with the verbs :mod:`scalo.api` uses:

- ``GET`` on a collection -> ``list``
- ``GET`` on an item (trailing parameter) -> ``get``
- ``POST`` on a collection -> ``create``
- ``PUT`` on an item -> ``apply``, ``PATCH`` -> ``update``, ``DELETE`` -> ``delete``
- anything on ``/{id}/<action>`` or a collection's ``/<action>`` -> ``<action>``

The groups are the path's literal segments, kebab-case. Path parameters never name
a group: they become options. A collection (POST -> create) is told apart from an
action (POST -> <action>) by whether the same path also has an item route
(``.../{param}``).
"""

import re

from .vendor.xform import xform_name

_VERSION = re.compile(r"^v\d+$")


def is_param(segment: str) -> bool:
    """Whether a path template segment is a parameter, such as ``{name}``."""
    return segment.startswith("{") and segment.endswith("}")


def kebab(name: str) -> str:
    """``name`` in lower kebab-case.

    ``backing_services``, ``BackingServices`` and ``Backing_Services`` all give ``backing-services``.
    """
    return xform_name(name.replace("_", "-"), "-").replace("_", "-").lower()


def api_segments(path: str, base_path: str | None = None) -> list[str]:
    """A path's segments below its base path.

    Args:
        path: The path template.
        base_path: The prefix to strip. ``None`` strips a leading ``api`` and a
            version segment such as ``v1``, when the path has them.

    Returns:
        The remaining segments.
    """
    parts = [part for part in path.split("/") if part]
    if base_path is not None:
        prefix = [part for part in base_path.split("/") if part]
        if parts[: len(prefix)] == prefix:
            return parts[len(prefix) :]
        return parts
    if parts[:1] == ["api"]:
        parts = parts[1:]
    if parts and _VERSION.match(parts[0]):
        parts = parts[1:]
    return parts


def collection_key(path: str, base_path: str | None = None) -> str | None:
    """The collection an item path belongs to, ``None`` when the path does not end in a parameter."""
    segments = api_segments(path, base_path)
    if segments and is_param(segments[-1]):
        return "/".join(segments[:-1])
    return None


def derive_group_and_verb(
    path: str, method: str, collections_with_item: set[str], base_path: str | None = None
) -> tuple[list[str], str]:
    """The group path and verb for one operation.

    Args:
        path: The path template.
        method: The HTTP method.
        collections_with_item: Every :func:`collection_key` in the spec.
        base_path: As for :func:`api_segments`.

    Returns:
        ``(group_path, verb)``.
    """
    method = method.lower()
    segments = api_segments(path, base_path)
    if not segments:
        return [], method

    literals = [kebab(segment) for segment in segments if not is_param(segment)]

    if is_param(segments[-1]):
        item_verbs = {"get": "get", "put": "apply", "patch": "update", "delete": "delete"}
        return literals, item_verbs.get(method, kebab(method))

    is_collection = "/".join(segments) in collections_with_item
    if method == "get":
        return literals, "list"
    if is_collection:
        collection_verbs = {"post": "create", "put": "apply", "patch": "update", "delete": "delete"}
        if method in collection_verbs:
            return literals, collection_verbs[method]

    # An action: the trailing literal is the verb, the resource path before it the group.
    return literals[:-1], kebab(segments[-1])
