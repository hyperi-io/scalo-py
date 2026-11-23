"""Managed config layer: store mapping, the plist reader, cascade order, and the registry on Windows."""

import datetime
import logging
import os
import plistlib
import re
import sys
import types
import uuid
from pathlib import Path

import pytest
from dynaconf import Dynaconf, inspect_settings

from scalo.config import ManagedSource, get_config
from scalo.config.managed import (
    apply,
    plist_value,
    read_plist,
    read_registry,
    registry_value,
    to_config,
)

SZ, DWORD, MULTI_SZ, QWORD, BINARY, EXPAND_SZ = 1, 4, 7, 11, 3, 2

NOT_SECRETS = {
    "auth_mode": "x",
    "verify_cert": True,
    "field_mapping": "x",
    "session_timeout": 5,
    "alert_email": "x",
    "private_network": True,
    "max_tokens": 9,
    "headers": [{"name": "X-Key", "value": "x"}],
    "tls": {"key_file": "/k.pem"},
}

MAPPING_CASES = [
    ("empty registry", {}, registry_value, {}),
    (
        "registry types and subkeys",
        {
            "Port": (8443, DWORD),
            "Max": (2**40, QWORD),
            "Hosts": (["a", "b"], MULTI_SZ),
            "sink": {"tls": {"enabled": ("true", SZ), "verify": ("1", SZ)}},
            "routes": ('[{name="x", weight=2}]', SZ),
            "batch__size": ("500", SZ),
            "password_file": (r"C:\secrets\pw", SZ),
        },
        registry_value,
        {
            "Port": 8443,
            "Max": 2**40,
            "Hosts": ["a", "b"],
            "sink": {"tls": {"enabled": True, "verify": 1}},
            "routes": [{"name": "x", "weight": 2}],
            "batch": {"size": 500},
            "password_file": r"C:\secrets\pw",
        },
    ),
    (
        "registry types it skips",
        {"blob": (b"\x00", BINARY), "path": ("%TEMP%", EXPAND_SZ), "": ("x", SZ), "keep": (1, DWORD)},
        registry_value,
        {"keep": 1},
    ),
    ("registry secret", {"sink": {"password": ("hunter2", SZ)}}, registry_value, "sink.password"),
    ("secret of a skipped type", {"api_key": (b"\x01", BINARY)}, registry_value, "api_key"),
    ("secret inside a value", {"sink": ('{token="x"}', SZ)}, registry_value, "sink (token)"),
    ("empty plist", {}, plist_value, {}),
    (
        "plist types",
        {"sink": {"port": 9000, "ratio": 0.5, "on": False, "mode": "true", "hosts": ["a"]}, "routes": [{"n": 1}]},
        plist_value,
        {"sink": {"port": 9000, "ratio": 0.5, "on": False, "mode": "true", "hosts": ["a"]}, "routes": [{"n": 1}]},
    ),
    (
        "plist types it skips",
        {"blob": b"\x00", "when": datetime.datetime(2026, 1, 1), "mixed": ["a", b"\x00"], "keep": "x"},
        plist_value,
        {"keep": "x"},
    ),
    ("plist secret in a list", {"routes": [{"name": "x", "token": "s3cret"}]}, plist_value, "routes (token)"),
    ("names that only look secret", NOT_SECRETS, plist_value, NOT_SECRETS),
    ("sasl password", {"kafka": {"sasl_password": "x"}}, plist_value, "kafka.sasl_password"),
    ("upper-case api key", {"API_KEY": "x"}, plist_value, "API_KEY"),
    ("client secret", {"client_secret": "x"}, plist_value, "client_secret"),
    ("bare token under auth", {"auth": {"token": "x"}}, plist_value, "auth.token"),
]


@pytest.fixture(autouse=True)
def managed_log(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """Capture the layer's records and keep them off pytest's live log, which CI renders as annotations."""
    managed_logger = logging.getLogger("scalo.config.managed")
    monkeypatch.setattr(managed_logger, "propagate", False)
    caplog.set_level(logging.DEBUG, logger=managed_logger.name)
    managed_logger.addHandler(caplog.handler)
    yield caplog
    managed_logger.removeHandler(caplog.handler)


@pytest.mark.parametrize(
    ("tree", "leaf", "expected"), [case[1:] for case in MAPPING_CASES], ids=[c[0] for c in MAPPING_CASES]
)
def test_to_config_maps_store_trees(tree, leaf, expected):
    """A store tree maps to config sections, and a secret key is refused by name."""
    if isinstance(expected, str):
        with pytest.raises(ValueError, match=re.escape(f"key {expected} holds a secret")):
            to_config(tree, leaf)
    else:
        assert to_config(tree, leaf) == expected


def test_to_config_logs_names_never_values(managed_log: pytest.LogCaptureFixture):
    """Debug names each key, a skipped value warns with its name, and no value reaches the log."""
    to_config({"sink": {"host": ("db.internal", SZ), "blob": (b"\x00", BINARY)}}, registry_value)
    messages = [(record.levelname, record.getMessage()) for record in managed_log.records]
    assert ("DEBUG", "Managed config sets sink.host") in messages
    assert ("WARNING", "Managed config value sink.blob skipped: unsupported type") in messages
    assert not any("db.internal" in message for _, message in messages)


def _write(path: Path, data: dict | list | bytes, mode: int) -> int:
    path.write_bytes(data if isinstance(data, bytes) else plistlib.dumps(data))
    path.chmod(mode)
    return path.stat().st_uid


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
@pytest.mark.parametrize(
    ("data", "mode", "uid_offset", "expected"),
    [
        ({"sink": {"port": 1}}, 0o644, 0, {"sink": {"port": 1}}),
        ({"sink": {"port": 1}}, 0o664, 0, None),
        ({"sink": {"port": 1}}, 0o646, 0, None),
        ({"sink": {"port": 1}}, 0o644, 1, None),
        (["not", "a", "dict"], 0o644, 0, None),
        (b"not a plist", 0o644, 0, None),
        (b"<plist><dict><key>a</key>", 0o644, 0, None),
    ],
    ids=["trusted", "group-writable", "world-writable", "other owner", "array root", "not a plist", "broken xml"],
)
def test_read_plist_trusts_only_an_owned_locked_file(tmp_path, data, mode, uid_offset, expected):
    """The plist is read only when its owner matches and nobody else can write it."""
    path = tmp_path / "com.example.app.plist"
    uid = _write(path, data, mode)
    assert read_plist(path, owner_uid=uid + uid_offset) == expected


def test_read_plist_missing_file_is_no_layer(tmp_path):
    """No file means no layer."""
    assert read_plist(tmp_path / "absent.plist") is None


def test_layer_sits_between_files_and_env(tmp_path, monkeypatch):
    """Policy beats the file, an env var beats policy, lists replace, and a reload reads the store again."""
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text("sink:\n  host: file\n  port: 1\n  hosts: [local]\n  mode: file\n", encoding="utf-8")
    store = {"sink": {"Port": 2, "hosts": ["policy"], "mode": "policy"}}
    loader = types.ModuleType(f"managed_test_{uuid.uuid4().hex}")
    loader.__dict__["load"] = lambda obj, *_args, **_kwargs: apply(obj, "test-store", store)
    monkeypatch.setitem(sys.modules, loader.__name__, loader)
    monkeypatch.setenv("MANAGEDTEST_SINK__MODE", "env")

    settings = Dynaconf(
        envvar_prefix="MANAGEDTEST",
        settings_files=[str(settings_file)],
        environments=False,
        merge_enabled=True,
        loaders=[loader.__name__, "dynaconf.loaders.env_loader"],
    )

    assert settings.as_dict()["SINK"] == {"host": "file", "port": 2, "hosts": ["policy"], "mode": "env"}
    sources = [
        (entry["loader"], entry["identifier"], entry["value"])
        for entry in inspect_settings(settings, "sink.port")["history"]
    ]
    assert ("managed", "test-store", 2) in sources
    store["sink"]["Port"] = 3
    settings.reload()
    assert settings.sink.port == 3


def test_get_config_without_a_store_changes_nothing():
    """A source this OS has no store for leaves the cascade as it was."""
    source = ManagedSource(
        windows_key=rf"Example\Absent{uuid.uuid4().hex}", macos_domain=f"com.example.absent{uuid.uuid4().hex}"
    )
    assert get_config(managed=source, load_dotenv=False).as_dict() == get_config(load_dotenv=False).as_dict()


def test_read_registry_maps_a_real_key():
    """Subkeys, value types and absence read through winreg as the mapping expects."""
    if sys.platform != "win32":
        pytest.skip("Windows registry test")
    import winreg

    subkey = rf"Software\scalo-managed-test-{os.getpid()}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{subkey}\sink\tls") as tls:
        winreg.SetValueEx(tls, "verify", 0, winreg.REG_SZ, "false")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{subkey}\sink") as sink:
        winreg.SetValueEx(sink, "port", 0, winreg.REG_DWORD, 8443)
        winreg.SetValueEx(sink, "hosts", 0, winreg.REG_MULTI_SZ, ["a", "b"])
        winreg.SetValueEx(sink, "blob", 0, winreg.REG_BINARY, b"\x00")
    try:
        tree = read_registry(subkey, winreg.HKEY_CURRENT_USER)
        assert tree is not None
        assert to_config(tree, registry_value) == {
            "sink": {"port": 8443, "hosts": ["a", "b"], "tls": {"verify": False}}
        }
        assert read_registry(rf"{subkey}\absent", winreg.HKEY_CURRENT_USER) is None
    finally:
        for path in (rf"{subkey}\sink\tls", rf"{subkey}\sink", subkey):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
