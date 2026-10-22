#  Project:   scalo
#  File:      src/scalo/cli/openapi/config.py
#  Purpose:   Named profiles and the credential file a generated CLI reads its endpoint and token from
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Profiles and credentials for a generated CLI, shaped like the AWS and gcloud CLIs.

Layout under ``~/.config/<name>`` (``$<PREFIX>_CONFIG_HOME`` moves the whole root)::

    configurations/config_<profile>   INI: [core] url = ..., account = ...
    active_config                     one line: the active profile name
    credentials.json                  {account: {token | api_key}}, mode 0600
    .credentials.lock                 advisory lock: one process changes credentials at a time

Credentials are keyed by account, so several profiles that name one account share
its token. Resolution, first wins:

- endpoint: ``--endpoint-url``, then ``$<PREFIX>_API_URL``, then the profile's ``url``
- credential: ``$<PREFIX>_API_KEY``, then ``$<PREFIX>_API_TOKEN``, then the
  stored credential of the profile's account
- profile: ``--profile``, then ``$<PREFIX>_PROFILE``, then ``active_config``
"""

import configparser
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .errors import CliConfigError

DEFAULT_PROFILE = "default"

if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def config_home(name: str, env_prefix: str) -> Path:
    """The configuration root: ``$<PREFIX>_CONFIG_HOME``, else ``~/.config/<name>``."""
    override = os.environ.get(f"{env_prefix}_CONFIG_HOME")
    if override:
        return Path(override)
    return Path.home() / ".config" / name


@dataclass(frozen=True, slots=True)
class Credential:
    """A credential: exactly one of ``token`` and ``api_key`` is set.

    Attributes:
        account: The account it belongs to.
        token: A bearer token.
        api_key: An API key.
    """

    account: str
    token: str | None = None
    api_key: str | None = None

    def __repr__(self) -> str:
        """Name the account and the kind, never the secret."""
        kind = "api_key" if self.api_key is not None else "token"
        return f"Credential(account={self.account!r}, kind={kind})"

    @property
    def is_api_key(self) -> bool:
        """Whether this is an API key rather than a token."""
        return self.api_key is not None

    @property
    def value(self) -> str | None:
        """The API key, else the token."""
        return self.api_key if self.api_key is not None else self.token


class Store:
    """The profile files and the credential file under one root.

    Args:
        home: The configuration root, such as :func:`config_home`'s answer.
    """

    def __init__(self, home: Path) -> None:
        self.home = home

    @property
    def configurations_dir(self) -> Path:
        """The directory holding one file per profile."""
        return self.home / "configurations"

    @property
    def active_config_file(self) -> Path:
        """The file naming the active profile."""
        return self.home / "active_config"

    @property
    def credentials_file(self) -> Path:
        """The file holding stored credentials."""
        return self.home / "credentials.json"

    @property
    def credentials_lock_file(self) -> Path:
        """The file whose advisory lock serialises changes to the credentials."""
        return self.home / ".credentials.lock"

    @contextmanager
    def _credentials_locked(self) -> Iterator[None]:
        """Hold the credentials lock, so two processes changing credentials take turns and neither loses an account."""
        self._ensure_home()
        fd = os.open(self.credentials_lock_file, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock(fd)
            try:
                yield
            finally:
                _unlock(fd)
        finally:
            os.close(fd)

    def _profile_file(self, name: str) -> Path:
        return self.configurations_dir / f"config_{name}"

    def _ensure_home(self) -> None:
        # Credentials live here, so the tree is owner-only whatever the umask.
        for directory in (self.home, self.configurations_dir):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                directory.chmod(0o700)
            except OSError:
                pass

    def active_profile(self) -> str:
        """The active profile's name, else :data:`DEFAULT_PROFILE`."""
        if self.active_config_file.exists():
            name = self.active_config_file.read_text(encoding="utf-8").strip()
            if name:
                return name
        return DEFAULT_PROFILE

    def set_active_profile(self, name: str) -> None:
        """Make ``name`` the active profile."""
        self._ensure_home()
        self.active_config_file.write_text(name + "\n", encoding="utf-8", newline="\n")

    def list_profiles(self) -> list[str]:
        """Every profile name, sorted."""
        if not self.configurations_dir.exists():
            return []
        prefix = "config_"
        return sorted(p.name[len(prefix) :] for p in self.configurations_dir.glob(f"{prefix}*") if p.is_file())

    def create_profile(self, name: str) -> None:
        """Create an empty profile, unless one of that name exists."""
        self._ensure_home()
        path = self._profile_file(name)
        if not path.exists():
            parser = configparser.ConfigParser()
            parser["core"] = {}
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                parser.write(handle)

    def delete_profile(self, name: str) -> None:
        """Delete a profile, falling back to the default when it was active."""
        path = self._profile_file(name)
        if path.exists():
            path.unlink()
        if self.active_profile() == name:
            self.set_active_profile(DEFAULT_PROFILE)

    def _read_profile(self, name: str) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        path = self._profile_file(name)
        if path.exists():
            try:
                parser.read(path, encoding="utf-8")
            except configparser.Error as exc:
                raise CliConfigError(f"profile {name!r} is not a readable INI file: {exc}") from exc
        if not parser.has_section("core"):
            parser.add_section("core")
        return parser

    def get_value(self, key: str, name: str | None = None) -> str | None:
        """One key from a profile, the active one unless ``name`` is given."""
        return self._read_profile(name or self.active_profile())["core"].get(key)

    def set_value(self, key: str, value: str, name: str | None = None) -> None:
        """Set one key in a profile, the active one unless ``name`` is given."""
        self._ensure_home()
        profile = name or self.active_profile()
        parser = self._read_profile(profile)
        parser["core"][key] = value
        with self._profile_file(profile).open("w", encoding="utf-8", newline="\n") as handle:
            parser.write(handle)

    def profile_items(self, name: str | None = None) -> dict[str, str]:
        """Every key in a profile, the active one unless ``name`` is given."""
        return dict(self._read_profile(name or self.active_profile())["core"])

    def _read_credentials(self) -> dict[str, dict[str, str]]:
        """The stored credentials.

        Raises:
            CliConfigError: When the file cannot be read or is not a JSON object,
                so a save never writes over accounts it could not read.
        """
        path = self.credentials_file
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CliConfigError(f"{path} cannot be read: {exc.strerror or exc}") from exc
        try:
            stored = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CliConfigError(f"{path} is not valid JSON ({exc}): repair or remove it") from exc
        if not isinstance(stored, dict):
            raise CliConfigError(f"{path} is not a JSON object of accounts: repair or remove it")
        return stored

    def _write_credentials(self, credentials: dict[str, dict[str, str]]) -> None:
        self._ensure_home()
        payload = json.dumps(credentials, indent=2) + "\n"
        # mkstemp creates the file 0600, and the rename swaps it in whole, so no reader sees half a file.
        handle, temporary = tempfile.mkstemp(dir=self.home, prefix=".credentials-", suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.credentials_file)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def save_credential(self, credential: Credential) -> None:
        """Store a credential under its account."""
        entry: dict[str, str] = {}
        if credential.api_key is not None:
            entry["api_key"] = credential.api_key
        if credential.token is not None:
            entry["token"] = credential.token
        with self._credentials_locked():
            credentials = self._read_credentials()
            credentials[credential.account] = entry
            self._write_credentials(credentials)

    def get_credential(self, account: str) -> Credential | None:
        """The credential stored for ``account``, or None."""
        entry = self._read_credentials().get(account)
        if not isinstance(entry, dict) or not entry:
            return None
        return Credential(account=account, token=entry.get("token"), api_key=entry.get("api_key"))

    def delete_credential(self, account: str) -> None:
        """Remove the credential stored for ``account``."""
        with self._credentials_locked():
            credentials = self._read_credentials()
            if account in credentials:
                del credentials[account]
                self._write_credentials(credentials)

    def list_accounts(self) -> list[str]:
        """Every account with a stored credential, sorted."""
        return sorted(self._read_credentials())


@dataclass(frozen=True, slots=True)
class Resolved:
    """The endpoint and credential one invocation uses.

    Attributes:
        url: The API's base URL, ``None`` when nothing set one.
        credential: The credential, ``None`` to call anonymously.
        account: The profile's account.
        profile: The profile that was read.
    """

    url: str | None
    credential: Credential | None
    account: str | None
    profile: str


def resolve(
    store: Store, env_prefix: str, *, url_override: str | None = None, profile_override: str | None = None
) -> Resolved:
    """Resolve the endpoint and credential in the documented order.

    Args:
        store: The profile and credential store.
        env_prefix: Prefix of the environment variables, such as ``SVC``.
        url_override: ``--endpoint-url``.
        profile_override: ``--profile``.

    Returns:
        What this invocation uses.
    """
    profile = profile_override or os.environ.get(f"{env_prefix}_PROFILE") or store.active_profile()
    url = url_override or os.environ.get(f"{env_prefix}_API_URL") or store.get_value("url", profile)
    account = store.get_value("account", profile)

    env_key = os.environ.get(f"{env_prefix}_API_KEY")
    env_token = os.environ.get(f"{env_prefix}_API_TOKEN")
    credential: Credential | None = None
    if env_key:
        credential = Credential(account=account or "env", api_key=env_key)
    elif env_token:
        credential = Credential(account=account or "env", token=env_token)
    elif account:
        credential = store.get_credential(account)
    return Resolved(url=url or None, credential=credential, account=account, profile=profile)
