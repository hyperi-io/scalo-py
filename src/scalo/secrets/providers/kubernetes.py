# Project:   scalo
# File:      secrets/providers/kubernetes.py
# Purpose:   Kubernetes Secret provider over the in-cluster API
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Kubernetes provider: the data keys of one named Secret, read and written through the in-cluster API.

The provider never creates, deletes or lists Secrets, so a Role granting ``get`` and ``update`` on that one
``resourceName`` is all it needs. A write reads the Secret, changes one key and replaces the whole object,
carrying the ``resourceVersion`` it read. When another writer got in first the API server answers 409, and
the write starts again from a fresh read, so neither writer's change is lost. A read answered 429 or 5xx,
or not answered at all, is tried again, but a replace never is: a replace whose answer was lost may
already have landed.
"""

import asyncio
import base64
import binascii
import fnmatch
import json
import logging
import os
import random
import re
import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..exceptions import (
    AuthenticationError,
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
    SecretsError,
)
from ..types import KubernetesConfig, SecretFilter, SecretMetadata, SecretValue, _check_namespace
from .base import HealthLog, SecretProvider, credential_digest

logger = logging.getLogger(__name__)

try:
    import httpx
    import stamina

    CLIENT_AVAILABLE = True
except ImportError:
    # The constructor raises before any use of httpx or stamina.
    CLIENT_AVAILABLE = False

# The API server's rule for a Secret data key, the same one it applies to a ConfigMap key.
_DATA_KEY = re.compile(r"[-._a-zA-Z0-9]+")
_DATA_KEY_MAX = 253

# client-go's DefaultRetry: 10 ms between conflicting writes, with 10% jitter.
_CONFLICT_WAIT_SECS = 0.01
_CONFLICT_JITTER = 0.1

# A read is tried three times, waiting 0.1 s then 0.2 s plus up to 0.1 s of jitter, or what Retry-After asks up to 2 s.
_READ_ATTEMPTS = 3
_READ_WAIT_INITIAL_SECS = 0.1
_READ_WAIT_MAX_SECS = 2.0
_READ_WAIT_JITTER_SECS = 0.1

# A refusal's message is quoted into the error, capped so a large body cannot flood a log line.
_STATUS_MESSAGE_MAX = 300

# RFC 6750 token68, which a JWT's base64url segments and dots fit inside.
_TOKEN68 = re.compile(r"[A-Za-z0-9\-._~+/]+=*")


def check_data_key(key: str) -> None:
    """Refuse a key the API server would reject in a Secret's ``data``.

    Raises:
        ValueError: ``key`` is empty, longer than 253 characters, holds a character other than letters,
            digits, ``-``, ``_`` and ``.``, or is ``.``, ``..`` or starts with ``..``.
    """
    if len(key) > _DATA_KEY_MAX or not _DATA_KEY.fullmatch(key) or key in (".", "..") or key.startswith(".."):
        raise ValueError(
            f"{key!r} is not a valid Kubernetes Secret key: use letters, digits, '-', '_' and '.', at most "
            f"{_DATA_KEY_MAX} characters, and not '.', '..' or a name starting with '..'"
        )


def _conflict_wait() -> float:
    return _CONFLICT_WAIT_SECS * (1 + random.uniform(0, _CONFLICT_JITTER))


class _TransientRead(Exception):
    """A GET worth trying again: a 429, a 5xx, or no answer. Its repr carries only the reason, for stamina's retry log.

    Attributes:
        response: The 429 or 5xx answer, None when there was no answer.
        error: The transport error, None when there was an answer.
        wait: Seconds the API server asked to wait in Retry-After, None for the usual backoff.
    """

    def __init__(
        self,
        reason: str,
        *,
        response: httpx.Response | None = None,
        error: httpx.TransportError | None = None,
        wait: float | None = None,
    ) -> None:
        """Record why the read failed and what the next wait should be."""
        super().__init__(reason)
        self.response = response
        self.error = error
        self.wait = wait

    def __repr__(self) -> str:
        """Name the reason only, never the request."""
        return f"_TransientRead({self.args[0]!r})"


def _retry_read(exc: Exception) -> bool | float:
    """The stamina hook: repeat a transient read, after Retry-After when the API server sent one."""
    if not isinstance(exc, _TransientRead):
        return False
    return exc.wait if exc.wait is not None else True


def _retry_after(response: httpx.Response) -> float | None:
    """Retry-After in seconds, capped at the longest read wait. None when absent or an HTTP date."""
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return None
    return min(max(seconds, 0.0), _READ_WAIT_MAX_SECS)


def _transient_answer(response: httpx.Response) -> _TransientRead | None:
    """A 429 or 5xx answer as a transient read, None for any other status."""
    status = response.status_code
    if status == 429:
        return _TransientRead(f"HTTP {status}", response=response, wait=_retry_after(response))
    if 500 <= status < 600:
        return _TransientRead(f"HTTP {status}", response=response)
    return None


def _transient_error(error: httpx.HTTPError) -> _TransientRead | None:
    """A transport error as a transient read, None when httpx refused to send or the error is not transport."""
    # httpx refuses a malformed header or a URL with no http scheme the same way on every attempt.
    if isinstance(error, (httpx.LocalProtocolError, httpx.UnsupportedProtocol)):
        return None
    if isinstance(error, httpx.TransportError):
        return _TransientRead(type(error).__name__, error=error)
    return None


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _parse_timestamp(value: object) -> datetime | None:
    """Parse a Kubernetes RFC 3339 timestamp. Returns None for a missing or malformed one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _status_message(response: httpx.Response) -> str:
    """The ``message`` of a Kubernetes Status body, or the bare status code when there is none."""
    try:
        message = response.json().get("message")
    except ValueError, AttributeError:
        message = None
    if not isinstance(message, str) or not message:
        return f"HTTP {response.status_code}"
    return message[:_STATUS_MESSAGE_MAX]


def _extract_json_key(data: bytes, path: str, key: str, provider: str) -> bytes:
    """Read ``key`` out of a JSON object stored at ``path``, as the file provider does.

    Raises:
        ProviderError: The value is not a JSON object.
        SecretNotFoundError: The object has no ``key``.
    """
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProviderError(provider, f"key {path!r} does not hold JSON: {e}")
    if not isinstance(parsed, dict):
        raise ProviderError(provider, f"key {path!r} does not hold a JSON object")
    if key not in parsed:
        raise SecretNotFoundError(f"{path}[{key}]", provider)
    value = parsed[key]
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value).encode("utf-8")


class KubernetesProvider(SecretProvider):
    """Kubernetes Secret provider: each data key of one named Secret is a secret, addressed by its key.

    Authenticates with the pod's service account token over the in-cluster API, checking the API server
    against the service account CA. Uses httpx for true async HTTP.

    A path is a data key of the configured Secret. ``create`` adds a key, ``update`` replaces one, and
    ``delete`` removes one. The Secret itself must already exist. A value's version, and the metadata's, is
    the Secret's ``resourceVersion``, which changes when any of its keys does.
    """

    def __init__(self, config: KubernetesConfig) -> None:
        """Initialise the Kubernetes provider.

        Args:
            config: Kubernetes configuration.

        Raises:
            ProviderNotAvailableError: httpx or stamina not installed.
        """
        if not CLIENT_AVAILABLE:
            from ..exceptions import ProviderNotAvailableError

            raise ProviderNotAvailableError("kubernetes", "httpx and stamina", "pip install scalo[secrets-kubernetes]")

        self._config = config
        self._namespace: str | None = config.namespace
        self._client: httpx.AsyncClient | None = None
        self._sync_client: httpx.Client | None = None
        self._health = HealthLog(logger, self.name)

    @property
    def name(self) -> str:
        """Provider name."""
        return "kubernetes"

    @property
    def cache_identity(self) -> tuple[str, ...]:
        """See base class."""
        return (
            self.name,
            self._config.api_server or "",
            self._config.namespace or "",
            self._config.secret_name,
            self._config.token_path,
        )

    # --- Connection ---

    def _base_url(self) -> str:
        """The API server URL: the configured one, else the one Kubernetes gives every pod."""
        if self._config.api_server:
            return self._config.api_server.rstrip("/")
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT")
        if not host or not port:
            raise ProviderError(
                self.name,
                "no API server: set api_server, or run in a pod, where KUBERNETES_SERVICE_HOST and "
                "KUBERNETES_SERVICE_PORT are set",
            )
        if ":" in host:
            host = f"[{host}]"
        return f"https://{host}:{port}"

    def _ssl_verify(self) -> ssl.SSLContext:
        """The TLS context the API server is checked with, under the scalo crypto posture.

        Raises:
            ProviderError: The CA bundle cannot be read.
        """
        from scalo.crypto import ssl_context

        try:
            return ssl_context(cafile=self._config.ca_cert)
        except OSError as e:
            raise ProviderError(self.name, f"cannot load the API server CA {self._config.ca_cert}: {e}")

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url(),
                timeout=self._config.timeout_secs,
                verify=self._ssl_verify(),
            )
        return self._client

    def _get_sync_client(self) -> httpx.Client:
        """Get or create the sync HTTP client."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self._base_url(),
                timeout=self._config.timeout_secs,
                verify=self._ssl_verify(),
            )
        return self._sync_client

    def _resolve_namespace(self) -> str:
        """The Secret's namespace: the configured one, else the pod's own.

        Raises:
            ProviderError: No namespace is configured and the pod's cannot be read.
        """
        if self._namespace is None:
            path = Path(self._config.namespace_path)
            try:
                namespace = path.read_text(encoding="utf-8").strip()
            except OSError as e:
                raise ProviderError(
                    self.name, f"no namespace: set namespace, or mount the pod's service account ({path}: {e.strerror})"
                )
            try:
                _check_namespace(namespace)
            except ValueError as e:
                raise ProviderError(self.name, f"{path}: {e}")
            self._namespace = namespace
        return self._namespace

    def _secret_url(self) -> str:
        return f"/api/v1/namespaces/{self._resolve_namespace()}/secrets/{self._config.secret_name}"

    def _location(self) -> str:
        """The Secret as errors name it, ``<namespace>/<name>``."""
        return f"{self._resolve_namespace()}/{self._config.secret_name}"

    def _headers(self) -> dict[str, str]:
        """Request headers carrying the service account token, read fresh because the kubelet rotates it.

        Raises:
            AuthenticationError: The token file cannot be read, is empty, or holds anything but a token68
                bearer token. The error names the file, never its content.
        """
        path = Path(self._config.token_path)
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise AuthenticationError(self.name, f"service account token not readable at {path}: {e.strerror}")
        except UnicodeDecodeError:
            raise AuthenticationError(self.name, f"service account token at {path} is not UTF-8 text") from None
        if not token:
            raise AuthenticationError(self.name, f"service account token at {path} is empty")
        if not _TOKEN68.fullmatch(token):
            # httpx would quote a control character into its error, or raise on non-ASCII, either way the token.
            raise AuthenticationError(
                self.name, f"service account token at {path} holds characters a bearer token cannot"
            )
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # --- Responses ---

    def _refusal(self, response: httpx.Response, operation: str) -> ProviderError:
        """The error an answer other than success, 404 or 409 maps to."""
        status = response.status_code
        location = self._location()
        if status == 401:
            return AuthenticationError(self.name, "API server refused the service account token: HTTP 401")
        if status == 403:
            return SecretPermissionError(
                self.name,
                operation,
                location,
                "grant the service account get and update on this Secret, through a Role naming it in resourceNames",
            )
        # 400 is a body the API server could not decode, such as a value that is not base64, and 422 one it rejected.
        if status in (400, 422):
            return ProviderError(self.name, f"{operation} {location} refused as invalid: {_status_message(response)}")
        return ProviderError(self.name, f"{operation} {location} failed: HTTP {status}")

    def _unreachable(self, operation: str, exc: Exception) -> ProviderError:
        return ProviderError(self.name, f"{operation} {self._location()} failed: API server unreachable: {exc}")

    def _read_gave_up(self, operation: str, transient: _TransientRead) -> ProviderError:
        """The error for a read still transient on its last attempt."""
        if transient.response is not None:
            return self._refusal(transient.response, operation)
        return self._unreachable(operation, transient.error or transient)

    def _read_attempts(self) -> Any:
        """The bounded retry a GET runs under, stopping early once the request timeout has elapsed in total."""
        return stamina.retry_context(
            on=_retry_read,
            attempts=_READ_ATTEMPTS,
            timeout=self._config.timeout_secs,
            wait_initial=_READ_WAIT_INITIAL_SECS,
            wait_max=_READ_WAIT_MAX_SECS,
            wait_jitter=_READ_WAIT_JITTER_SECS,
        )

    def _missing_secret(self, operation: str) -> ProviderError:
        return ProviderError(
            self.name,
            f"{operation} {self._location()} failed: the Secret does not exist, and this provider writes keys "
            "into an existing Secret, never creating one",
        )

    def _conflicted(self, operation: str) -> ProviderError:
        return ProviderError(
            self.name,
            f"{operation} {self._location()} failed: another writer changed the Secret on each of "
            f"{self._config.conflict_retries + 1} attempts",
        )

    def _parse_secret(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise ProviderError(self.name, f"{operation} {self._location()} failed: the answer is not a Secret object")
        return body

    def _read_answer(self, response: httpx.Response, operation: str) -> dict[str, Any] | None:
        """The Secret a GET returned, or None when it does not exist."""
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise self._refusal(response, operation)
        return self._parse_secret(response, operation)

    def _replace_answer(self, response: httpx.Response, operation: str) -> dict[str, Any] | None:
        """The Secret a PUT stored, or None when another writer changed it since it was read."""
        if response.status_code == 409:
            return None
        if response.status_code == 404:
            raise self._missing_secret(operation)
        if response.status_code != 200:
            raise self._refusal(response, operation)
        return self._parse_secret(response, operation)

    def _value(self, secret: dict[str, Any], path: str, key: str | None) -> SecretValue:
        """The value of data key ``path`` in ``secret``, or of ``key`` inside it when that holds JSON."""
        data = secret.get("data") or {}
        if path not in data:
            raise SecretNotFoundError(path, self.name)
        try:
            raw = base64.b64decode(data[path], validate=True)
        except binascii.Error, TypeError, ValueError:
            raise ProviderError(self.name, f"key {path!r} in {self._location()} is not base64")
        if key is not None:
            raw = _extract_json_key(raw, path, key, self.name)
        return SecretValue(
            data=raw,
            fetched_at=datetime.now(UTC),
            version=(secret.get("metadata") or {}).get("resourceVersion"),
            source=self.name,
        )

    def _metadata(self, secret: dict[str, Any], path: str) -> SecretMetadata:
        meta = secret.get("metadata") or {}
        return SecretMetadata(
            name=path,
            created_at=_parse_timestamp(meta.get("creationTimestamp")),
            version=meta.get("resourceVersion"),
            source=self.name,
        )

    def _keys(self, secret: dict[str, Any] | None, filter: SecretFilter | None) -> list[str]:
        keys = sorted((secret or {}).get("data") or {})
        if filter and filter.prefix:
            keys = [k for k in keys if k.startswith(filter.prefix)]
        if filter and filter.pattern:
            keys = [k for k in keys if fnmatch.fnmatch(k, filter.pattern)]
        return keys

    # --- Changes a write applies to the Secret's data ---

    def _adding(self, path: str, value: bytes) -> Callable[[dict[str, str]], None]:
        def change(data: dict[str, str]) -> None:
            if path in data:
                raise SecretAlreadyExistsError(path, self.name)
            data[path] = _encode(value)

        return change

    def _replacing(self, path: str, value: bytes) -> Callable[[dict[str, str]], None]:
        def change(data: dict[str, str]) -> None:
            if path not in data:
                raise SecretNotFoundError(path, self.name)
            data[path] = _encode(value)

        return change

    def _removing(self, path: str) -> Callable[[dict[str, str]], None]:
        def change(data: dict[str, str]) -> None:
            if path not in data:
                raise SecretNotFoundError(path, self.name)
            del data[path]

        return change

    # --- HTTP, sync ---

    def _get_secret_sync(self, operation: str) -> dict[str, Any] | None:
        client = self._get_sync_client()
        url = self._secret_url()
        try:
            for attempt in self._read_attempts():
                with attempt:
                    try:
                        response = client.get(url, headers=self._headers())
                    except httpx.HTTPError as e:
                        raise _transient_error(e) or self._unreachable(operation, e) from e
                    if transient := _transient_answer(response):
                        raise transient
                    return self._read_answer(response, operation)
        except _TransientRead as e:
            raise self._read_gave_up(operation, e) from e
        raise RuntimeError("stamina ended the retries without raising")  # pragma: no cover

    def _modify_sync(self, operation: str, path: str, change: Callable[[dict[str, str]], None]) -> SecretMetadata:
        """Read the Secret, apply ``change`` to its data and replace it, starting again after a conflict."""
        check_data_key(path)
        client = self._get_sync_client()
        for attempt in range(self._config.conflict_retries + 1):
            secret = self._get_secret_sync(operation)
            if secret is None:
                raise self._missing_secret(operation)
            data = dict(secret.get("data") or {})
            change(data)
            secret["data"] = data
            try:
                response = client.put(self._secret_url(), headers=self._headers(), json=secret)
            except httpx.HTTPError as e:
                raise self._unreachable(operation, e)
            stored = self._replace_answer(response, operation)
            if stored is not None:
                return self._metadata(stored, path)
            if attempt < self._config.conflict_retries:
                time.sleep(_conflict_wait())
        raise self._conflicted(operation)

    # --- HTTP, async ---

    async def _get_secret_async(self, operation: str) -> dict[str, Any] | None:
        client = await self._get_async_client()
        url = self._secret_url()
        try:
            async for attempt in self._read_attempts():
                with attempt:
                    try:
                        response = await client.get(url, headers=self._headers())
                    except httpx.HTTPError as e:
                        raise _transient_error(e) or self._unreachable(operation, e) from e
                    if transient := _transient_answer(response):
                        raise transient
                    return self._read_answer(response, operation)
        except _TransientRead as e:
            raise self._read_gave_up(operation, e) from e
        raise RuntimeError("stamina ended the retries without raising")  # pragma: no cover

    async def _modify_async(
        self, operation: str, path: str, change: Callable[[dict[str, str]], None]
    ) -> SecretMetadata:
        """Read the Secret, apply ``change`` to its data and replace it, starting again after a conflict."""
        check_data_key(path)
        client = await self._get_async_client()
        for attempt in range(self._config.conflict_retries + 1):
            secret = await self._get_secret_async(operation)
            if secret is None:
                raise self._missing_secret(operation)
            data = dict(secret.get("data") or {})
            change(data)
            secret["data"] = data
            try:
                response = await client.put(self._secret_url(), headers=self._headers(), json=secret)
            except httpx.HTTPError as e:
                raise self._unreachable(operation, e)
            stored = self._replace_answer(response, operation)
            if stored is not None:
                return self._metadata(stored, path)
            if attempt < self._config.conflict_retries:
                await asyncio.sleep(_conflict_wait())
        raise self._conflicted(operation)

    # --- Read ---

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Read data key ``path`` of the Secret.

        Args:
            path: The data key.
            key: Optional key to extract when the value is a JSON object.

        Returns:
            SecretValue with the decoded value, versioned by the Secret's resourceVersion.

        Raises:
            ValueError: ``path`` is not a valid Secret key.
            SecretNotFoundError: The Secret, or the key in it, does not exist.
            SecretPermissionError: The service account may not read the Secret.
            ProviderError: The API server could not be reached or refused the request.
        """
        check_data_key(path)
        secret = await self._get_secret_async("read")
        if secret is None:
            raise SecretNotFoundError(self._location(), self.name)
        return self._value(secret, path, key)

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Read data key ``path`` of the Secret (sync). See ``get_async``."""
        check_data_key(path)
        secret = self._get_secret_sync("read")
        if secret is None:
            raise SecretNotFoundError(self._location(), self.name)
        return self._value(secret, path, key)

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List the Secret's data keys, sorted.

        ``filter.prefix`` and ``filter.pattern`` apply client-side, and ``filter.tags`` is ignored: a key
        carries no labels. A Secret that does not exist lists no keys.
        """
        return self._keys(await self._get_secret_async("read"), filter)

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        """List the Secret's data keys, sorted (sync). See ``list_async``."""
        return self._keys(self._get_secret_sync("read"), filter)

    # --- Metadata ---

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        """Metadata of data key ``path``: the Secret's creation time and resourceVersion.

        Raises:
            ValueError: ``path`` is not a valid Secret key.
            SecretNotFoundError: The Secret, or the key in it, does not exist.
        """
        check_data_key(path)
        secret = await self._get_secret_async("read")
        if secret is None:
            raise SecretNotFoundError(self._location(), self.name)
        if path not in (secret.get("data") or {}):
            raise SecretNotFoundError(path, self.name)
        return self._metadata(secret, path)

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        """Metadata of data key ``path`` (sync). See ``get_metadata_async``."""
        check_data_key(path)
        secret = self._get_secret_sync("read")
        if secret is None:
            raise SecretNotFoundError(self._location(), self.name)
        if path not in (secret.get("data") or {}):
            raise SecretNotFoundError(path, self.name)
        return self._metadata(secret, path)

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Add data key ``path`` to the Secret. ``tags`` are ignored: a key carries no labels.

        Raises:
            ValueError: ``path`` is not a valid Secret key.
            SecretAlreadyExistsError: The Secret already holds the key.
            SecretPermissionError: The service account may not read or update the Secret.
            ProviderError: The Secret does not exist, the API server refused the write, or every attempt
                conflicted with another writer.
        """
        return await self._modify_async("create", path, self._adding(path, value))

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Add data key ``path`` to the Secret (sync). See ``create_async``."""
        return self._modify_sync("create", path, self._adding(path, value))

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Replace the value of data key ``path``.

        Raises:
            ValueError: ``path`` is not a valid Secret key.
            SecretNotFoundError: The Secret does not hold the key.
            SecretPermissionError: The service account may not read or update the Secret.
            ProviderError: The Secret does not exist, the API server refused the write, or every attempt
                conflicted with another writer.
        """
        return await self._modify_async("update", path, self._replacing(path, value))

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        """Replace the value of data key ``path`` (sync). See ``update_async``."""
        return self._modify_sync("update", path, self._replacing(path, value))

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Remove data key ``path`` from the Secret, which stays in place.

        Raises:
            ValueError: ``path`` is not a valid Secret key.
            SecretNotFoundError: The Secret does not hold the key.
            SecretPermissionError: The service account may not read or update the Secret.
            ProviderError: The Secret does not exist, the API server refused the write, or every attempt
                conflicted with another writer.
        """
        await self._modify_async("delete", path, self._removing(path))

    def delete_sync(self, path: str) -> None:
        """Remove data key ``path`` from the Secret (sync). See ``delete_async``."""
        self._modify_sync("delete", path, self._removing(path))

    # --- Health ---

    async def health_check_async(self) -> bool:
        """Check the Secret can be read with the service account, logging when that starts or stops being so.

        Raises:
            Exception: Anything other than a secrets error, which is a fault in the provider, not in its health.
        """
        failure = None
        try:
            secret = await self._get_secret_async("read")
        except SecretsError as e:
            failure = str(e)
        else:
            if secret is None:
                failure = f"{self._location()} does not exist"
        return await self._health.arecord(failure)

    def health_check_sync(self) -> bool:
        """Check the Secret can be read with the service account (sync). See ``health_check_async``."""
        failure = None
        try:
            secret = self._get_secret_sync("read")
        except SecretsError as e:
            failure = str(e)
        else:
            if secret is None:
                failure = f"{self._location()} does not exist"
        return self._health.record(failure)

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None


__all__ = ["KubernetesProvider", "check_data_key"]
