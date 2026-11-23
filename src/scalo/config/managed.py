"""Managed config: an opt-in policy layer read from the Windows registry or macOS managed preferences.

Group Policy, Intune and Jamf write a machine store only an administrator can change. An app
that names its store in a :class:`ManagedSource` gets it merged above every config file and
below env vars, so a policy beats a local file edit and an administrator can still override
it from the environment or a flag. See docs/core-pillars/managed-config.md.
"""

import functools
import hashlib
import logging
import os
import plistlib
import stat
import sys
import types
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError

from dynaconf.loaders.base import SourceMetadata
from dynaconf.utils.parse_conf import boolean_fix, parse_conf_data

logger = logging.getLogger(__name__)

_POLICIES = r"SOFTWARE\Policies"
_MANAGED_PREFERENCES = Path("/Library/Managed Preferences")

# The layer refuses a key named one of these or ending in _<term>, so a _file or _path name passes.
_SECRET_TERMS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "credentials",
)

# winreg's value type ids, so the mapping runs and is tested on every OS.
_REG_SZ, _REG_DWORD, _REG_MULTI_SZ, _REG_QWORD = 1, 4, 7, 11

_SKIP = object()


@dataclass(frozen=True, slots=True)
class ManagedSource:
    r"""The machine store an app reads its managed config from.

    Attributes:
        windows_key: Path under ``HKLM\SOFTWARE\Policies``, such as ``Example\App``.
        macos_domain: Preference domain, such as ``com.example.app``, read from
            ``/Library/Managed Preferences/<domain>.plist``.
    """

    windows_key: str | None = None
    macos_domain: str | None = None


def loader_module(source: ManagedSource) -> str:
    """Register a Dynaconf loader for ``source`` and return the import path to list in ``loaders``.

    Dynaconf names a loader by import path, so the source lives in the module rather than in
    a setting a local config file could override.
    """
    digest = hashlib.sha256(repr(source).encode()).hexdigest()[:16]
    name = f"{__name__}._loader_{digest}"
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__dict__["load"] = functools.partial(_load, source)
        sys.modules[name] = module
    return name


def read_registry(subkey: str, hive: int | None = None) -> dict[str, Any] | None:
    r"""Return the tree under ``hive\subkey``, or None when the key is absent or the OS is not Windows.

    Subkeys come back as nested dicts and values as ``(data, type)`` pairs.
    ``hive`` defaults to ``HKEY_LOCAL_MACHINE``.
    """
    if sys.platform != "win32":
        return None
    import winreg

    def walk(key: Any) -> dict[str, Any]:
        subkeys, values, _ = winreg.QueryInfoKey(key)
        tree: dict[str, Any] = {}
        for index in range(values):
            name, data, kind = winreg.EnumValue(key, index)
            tree[name] = (data, kind)
        for index in range(subkeys):
            name = winreg.EnumKey(key, index)
            with winreg.OpenKey(key, name) as child:
                tree[name] = walk(child)
        return tree

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE if hive is None else hive, subkey) as key:
            return walk(key)
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Managed config %s skipped: %s", subkey, exc)
        return None


def read_plist(path: Path, owner_uid: int = 0) -> dict[str, Any] | None:
    """Return the dict in the plist at ``path``, or None when it is absent or unsafe to trust.

    The file must be owned by ``owner_uid`` and writable by nobody else, else it is skipped
    with a warning. A file that does not parse to a dict is skipped the same way.
    """
    try:
        with path.open("rb") as file:
            info = os.fstat(file.fileno())
            if info.st_uid != owner_uid or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                logger.warning("Managed config %s skipped: not owned by uid %d, or writable by others", path, owner_uid)
                return None
            data = plistlib.load(file)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, ExpatError) as exc:
        logger.warning("Managed config %s skipped: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Managed config %s skipped: the plist root is not a dict", path)
        return None
    return data


def registry_value(raw: tuple[Any, int]) -> Any:
    """Map a registry ``(data, type)`` pair. A REG_SZ reads as the same text does in an env var."""
    data, kind = raw
    if kind == _REG_SZ:
        return parse_conf_data(boolean_fix(data), tomlfy=True)
    if kind in (_REG_DWORD, _REG_QWORD):
        return data
    if kind == _REG_MULTI_SZ:
        return list(data)
    return _SKIP


def plist_value(raw: Any) -> Any:
    """Keep a plist value built of strings, numbers, bools, lists and dicts, and skip any other."""
    if isinstance(raw, list | dict):
        items = raw.values() if isinstance(raw, dict) else raw
        return raw if all(plist_value(item) is not _SKIP for item in items) else _SKIP
    return raw if isinstance(raw, str | int | float) else _SKIP


def to_config(tree: Mapping[str, Any], leaf: Callable[[Any], Any]) -> dict[str, Any]:
    """Map a store tree into nested config sections.

    A nested dict in ``tree`` is a section, and every other item goes through ``leaf``. Names
    split on ``__`` as env var names do. An unsupported value or an empty name is skipped with
    a warning.

    Raises:
        ValueError: A key names a credential. Secrets come from a file, never from policy.
    """
    config: dict[str, Any] = {}
    for path, raw in _leaves(tree):
        dotted = ".".join(path)
        if not all(path):
            logger.warning("Managed config value %s skipped: empty name", dotted)
            continue
        value = leaf(raw)
        _refuse_secret(path, value)
        if value is _SKIP:
            logger.warning("Managed config value %s skipped: unsupported type", dotted)
            continue
        logger.debug("Managed config sets %s", dotted)
        node = config
        for part in path[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = node[part] = {}
            node = child
        node[path[-1]] = value
    return config


def _leaves(tree: Mapping[str, Any], parts: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Yield the path and raw value of each item in ``tree`` that is not a section."""
    for name, raw in tree.items():
        path = (*parts, *name.split("__"))
        if isinstance(raw, dict):
            yield from _leaves(raw, path)
        else:
            yield path, raw


def _key_names(name: str, value: Any) -> Iterator[str]:
    """Yield each key name that holds a non-dict value at or inside ``value``."""
    if not isinstance(value, dict):
        yield name
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, dict):
            for key, child in item.items():
                yield from _key_names(key, child)


def _is_secret_name(name: str) -> bool:
    """Return True when ``name`` is a secret term or ends with ``_`` and one, ignoring case."""
    lower = name.lower()
    return any(lower == term or lower.endswith(f"_{term}") for term in _SECRET_TERMS)


def _refuse_secret(path: tuple[str, ...], value: Any) -> None:
    """Raise ValueError when the key at ``path``, or one inside its value, names a secret."""
    for name in _key_names(path[-1], value):
        if _is_secret_name(name):
            key = ".".join(path) if name == path[-1] else f"{'.'.join(path)} ({name})"
            logger.error("Managed config key %s refused: it holds a secret", key)
            raise ValueError(
                f"managed config key {key} holds a secret, which policy must not set. "
                "Set its file-path form (a key ending _file or _path) instead"
            )


def _overlay(base: Any, top: Any) -> Any:
    """Lay ``top`` over ``base``: dicts merge, names matching case-insensitively, and anything else replaces."""
    if not (isinstance(base, Mapping) and isinstance(top, dict)):
        return top
    merged = dict(base)
    for name, value in top.items():
        match = next((existing for existing in base if str(existing).lower() == name.lower()), name)
        merged[match] = _overlay(base.get(match), value)
    return merged


def _read(source: ManagedSource) -> tuple[str, dict[str, Any]] | None:
    """Read this OS's store for ``source`` and return its label and config, or None when there is none."""
    if sys.platform == "win32" and source.windows_key:
        subkey = rf"{_POLICIES}\{source.windows_key}"
        tree, leaf, label = read_registry(subkey), registry_value, rf"HKLM\{subkey}"
    elif sys.platform == "darwin" and source.macos_domain:
        path = _MANAGED_PREFERENCES / f"{source.macos_domain}.plist"
        tree, leaf, label = read_plist(path), plist_value, str(path)
    else:
        return None
    if tree is None:
        logger.debug("Managed config %s not present", label)
        return None
    return label, to_config(tree, leaf)


def apply(obj: Any, label: str, config: Mapping[str, Any]) -> None:
    """Merge ``config`` into the Dynaconf settings ``obj``, recording ``label`` as each key's source.

    Only the keys ``config`` holds change. A list or scalar replaces the one beneath it, so a
    local file cannot extend a list the policy sets.
    """
    logger.info("Managed config read from %s: %d keys", label, sum(1 for _ in _leaves(config)))
    identifier = SourceMetadata("managed", label, "global")
    for name, section in config.items():
        obj.set(name, _overlay(obj.get(name), section), loader_identifier=identifier, merge=False)


def _load(source: ManagedSource, obj: Any, *_args: Any, **_kwargs: Any) -> None:
    """Dynaconf's entry point, which it runs after the settings files and before env vars."""
    if found := _read(source):
        apply(obj, *found)
