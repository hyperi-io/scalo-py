"""OpenBao/Vault secret provider with httpx async support."""

from __future__ import annotations

import base64
import fnmatch
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from ..exceptions import (
    AuthenticationError,
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
    SecretVersionNotFoundError,
)
from ..types import OpenBaoConfig, SecretFilter, SecretMetadata, SecretValue
from .base import VersionedProvider

logger = logging.getLogger(__name__)

# Optional httpx support
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore[assignment]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse OpenBao ISO datetime string. Returns None for empty/missing/invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class OpenBaoProvider(VersionedProvider):
    """OpenBao/Vault secret provider.

    Uses httpx for true async HTTP operations (no thread pool).

    Supports:
    - Token authentication
    - AppRole authentication
    - Kubernetes authentication
    - KV v2 secrets engine
    """

    def __init__(self, config: OpenBaoConfig) -> None:
        """Initialize OpenBao provider.

        Args:
            config: OpenBao configuration.

        Raises:
            ProviderNotAvailableError: httpx not installed.
        """
        if not HTTPX_AVAILABLE:
            from ..exceptions import ProviderNotAvailableError

            raise ProviderNotAvailableError(
                "openbao", "httpx", "pip install httpx or pip install hyperi-pylib[secrets-vault]"
            )

        self._config = config
        self._token: str | None = config.token
        self._token_expires_at: datetime | None = None
        self._client: httpx.AsyncClient | None = None
        self._sync_client: httpx.Client | None = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "openbao"

    def _get_base_headers(self) -> dict[str, str]:
        """Get base headers for requests."""
        headers: dict[str, str] = {}
        if self._token:
            headers["X-Vault-Token"] = self._token
        if self._config.namespace:
            headers["X-Vault-Namespace"] = self._config.namespace
        return headers

    def _get_ssl_context(self) -> httpx.Client | bool:
        """Get SSL verification settings."""
        if self._config.skip_verify:
            return False
        if self._config.ca_cert:
            return self._config.ca_cert
        return True

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            verify = self._get_ssl_context()
            self._client = httpx.AsyncClient(
                base_url=self._config.address,
                headers=self._get_base_headers(),
                timeout=self._config.timeout_secs,
                verify=verify,  # type: ignore[arg-type]
            )
        return self._client

    def _get_sync_client(self) -> httpx.Client:
        """Get or create sync HTTP client."""
        if self._sync_client is None:
            verify = self._get_ssl_context()
            self._sync_client = httpx.Client(
                base_url=self._config.address,
                headers=self._get_base_headers(),
                timeout=self._config.timeout_secs,
                verify=verify,  # type: ignore[arg-type]
            )
        return self._sync_client

    async def _authenticate_async(self) -> None:
        """Authenticate and obtain a token."""
        if self._config.auth_method == "token":
            if not self._token:
                raise AuthenticationError(self.name, "no token provided")
            return

        client = await self._get_async_client()

        if self._config.auth_method == "approle":
            await self._auth_approle_async(client)
        elif self._config.auth_method == "kubernetes":
            await self._auth_kubernetes_async(client)
        else:
            raise AuthenticationError(self.name, f"unsupported auth method: {self._config.auth_method}")

    def _authenticate_sync(self) -> None:
        """Authenticate and obtain a token (sync)."""
        if self._config.auth_method == "token":
            if not self._token:
                raise AuthenticationError(self.name, "no token provided")
            return

        client = self._get_sync_client()

        if self._config.auth_method == "approle":
            self._auth_approle_sync(client)
        elif self._config.auth_method == "kubernetes":
            self._auth_kubernetes_sync(client)
        else:
            raise AuthenticationError(self.name, f"unsupported auth method: {self._config.auth_method}")

    async def _auth_approle_async(self, client: httpx.AsyncClient) -> None:
        """Authenticate with AppRole."""
        if not self._config.role_id or not self._config.secret_id:
            raise AuthenticationError(self.name, "AppRole requires role_id and secret_id")

        mount = self._config.mount or "approle"
        url = f"/v1/auth/{mount}/login"

        try:
            response = await client.post(
                url,
                json={"role_id": self._config.role_id, "secret_id": self._config.secret_id},
            )
            response.raise_for_status()
            data = response.json()
            self._set_token_from_auth(data)
        except httpx.HTTPStatusError as e:
            raise AuthenticationError(self.name, f"AppRole auth failed: {e.response.status_code}")
        except Exception as e:
            raise AuthenticationError(self.name, f"AppRole auth failed: {e}")

    def _auth_approle_sync(self, client: httpx.Client) -> None:
        """Authenticate with AppRole (sync)."""
        if not self._config.role_id or not self._config.secret_id:
            raise AuthenticationError(self.name, "AppRole requires role_id and secret_id")

        mount = self._config.mount or "approle"
        url = f"/v1/auth/{mount}/login"

        try:
            response = client.post(
                url,
                json={"role_id": self._config.role_id, "secret_id": self._config.secret_id},
            )
            response.raise_for_status()
            data = response.json()
            self._set_token_from_auth(data)
        except httpx.HTTPStatusError as e:
            raise AuthenticationError(self.name, f"AppRole auth failed: {e.response.status_code}")
        except Exception as e:
            raise AuthenticationError(self.name, f"AppRole auth failed: {e}")

    async def _auth_kubernetes_async(self, client: httpx.AsyncClient) -> None:
        """Authenticate with Kubernetes service account."""
        if not self._config.role:
            raise AuthenticationError(self.name, "Kubernetes auth requires role")

        token_path = Path(self._config.token_path)
        if not token_path.exists():
            raise AuthenticationError(self.name, f"Service account token not found: {token_path}")

        jwt = token_path.read_text(encoding="utf-8").strip()
        mount = self._config.mount or "kubernetes"
        url = f"/v1/auth/{mount}/login"

        try:
            response = await client.post(url, json={"role": self._config.role, "jwt": jwt})
            response.raise_for_status()
            data = response.json()
            self._set_token_from_auth(data)
        except httpx.HTTPStatusError as e:
            raise AuthenticationError(self.name, f"Kubernetes auth failed: {e.response.status_code}")
        except Exception as e:
            raise AuthenticationError(self.name, f"Kubernetes auth failed: {e}")

    def _auth_kubernetes_sync(self, client: httpx.Client) -> None:
        """Authenticate with Kubernetes service account (sync)."""
        if not self._config.role:
            raise AuthenticationError(self.name, "Kubernetes auth requires role")

        token_path = Path(self._config.token_path)
        if not token_path.exists():
            raise AuthenticationError(self.name, f"Service account token not found: {token_path}")

        jwt = token_path.read_text(encoding="utf-8").strip()
        mount = self._config.mount or "kubernetes"
        url = f"/v1/auth/{mount}/login"

        try:
            response = client.post(url, json={"role": self._config.role, "jwt": jwt})
            response.raise_for_status()
            data = response.json()
            self._set_token_from_auth(data)
        except httpx.HTTPStatusError as e:
            raise AuthenticationError(self.name, f"Kubernetes auth failed: {e.response.status_code}")
        except Exception as e:
            raise AuthenticationError(self.name, f"Kubernetes auth failed: {e}")

    def _set_token_from_auth(self, data: dict) -> None:
        """Extract and set token from auth response."""
        auth = data.get("auth", {})
        self._token = auth.get("client_token")
        if not self._token:
            raise AuthenticationError(self.name, "no client_token in auth response")

        # Track token expiration
        lease_duration = auth.get("lease_duration", 0)
        if lease_duration > 0:
            self._token_expires_at = datetime.now(UTC).replace(microsecond=0) + __import__("datetime").timedelta(
                seconds=lease_duration
            )

        # Update client headers
        if self._client:
            self._client.headers["X-Vault-Token"] = self._token
        if self._sync_client:
            self._sync_client.headers["X-Vault-Token"] = self._token

    def _is_token_expired(self) -> bool:
        """Check if token needs renewal."""
        if not self._token_expires_at:
            return False
        # Renew 60 seconds before expiration
        buffer = __import__("datetime").timedelta(seconds=60)
        return datetime.now(UTC) >= (self._token_expires_at - buffer)

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from OpenBao/Vault.

        Args:
            path: Vault path (e.g., "secret/data/myapp/config").
            key: Optional key within the secret data.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Vault request failed.
        """
        # Ensure authenticated
        if not self._token or self._is_token_expired():
            await self._authenticate_async()

        client = await self._get_async_client()

        # Normalize path for KV v2
        api_path = self._normalize_kv_path(path)

        try:
            response = await client.get(api_path)

            if response.status_code == 404:
                raise SecretNotFoundError(path, self.name)

            response.raise_for_status()
            data = response.json()

            return self._parse_kv_response(data, path, key)

        except SecretNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise AuthenticationError(self.name, f"permission denied: {path}")
            raise ProviderError(self.name, f"request failed: {e.response.status_code}")
        except Exception as e:
            if isinstance(e, (SecretNotFoundError, AuthenticationError, ProviderError)):
                raise
            raise ProviderError(self.name, f"request failed: {e}")

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from OpenBao/Vault (sync).

        Args:
            path: Vault path (e.g., "secret/data/myapp/config").
            key: Optional key within the secret data.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Vault request failed.
        """
        # Ensure authenticated
        if not self._token or self._is_token_expired():
            self._authenticate_sync()

        client = self._get_sync_client()

        # Normalize path for KV v2
        api_path = self._normalize_kv_path(path)

        try:
            response = client.get(api_path)

            if response.status_code == 404:
                raise SecretNotFoundError(path, self.name)

            response.raise_for_status()
            data = response.json()

            return self._parse_kv_response(data, path, key)

        except SecretNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise AuthenticationError(self.name, f"permission denied: {path}")
            raise ProviderError(self.name, f"request failed: {e.response.status_code}")
        except Exception as e:
            if isinstance(e, (SecretNotFoundError, AuthenticationError, ProviderError)):
                raise
            raise ProviderError(self.name, f"request failed: {e}")

    def _normalize_kv_path(self, path: str) -> str:
        """Normalize path for KV v2 API.

        Ensures path starts with /v1/ and has /data/ for KV v2.
        """
        # Remove leading slash if present
        path = path.lstrip("/")

        # If already starts with v1/, use as-is
        if path.startswith("v1/"):
            return f"/{path}"

        # For KV v2, insert /data/ after mount point
        # e.g., "secret/myapp/config" -> "/v1/secret/data/myapp/config"
        parts = path.split("/", 1)
        if len(parts) == 2:
            mount, rest = parts
            # Check if 'data' is already in path
            if not rest.startswith("data/"):
                return f"/v1/{mount}/data/{rest}"
        return f"/v1/{path}"

    def _parse_kv_response(self, data: dict, path: str, key: str | None) -> SecretValue:
        """Parse KV v2 response into SecretValue."""
        # KV v2 response structure
        secret_data = data.get("data", {}).get("data", {})
        metadata = data.get("data", {}).get("metadata", {})

        if not secret_data:
            raise SecretNotFoundError(path, self.name)

        # Extract specific key if requested
        if key is not None:
            if key not in secret_data:
                raise SecretNotFoundError(f"{path}[{key}]", self.name)
            value = secret_data[key]
            # Convert to bytes
            if isinstance(value, bytes):
                result_data = value
            elif isinstance(value, str):
                result_data = value.encode("utf-8")
            else:
                result_data = json.dumps(value).encode("utf-8")
        else:
            # Return entire secret as JSON
            result_data = json.dumps(secret_data).encode("utf-8")

        return SecretValue(
            data=result_data,
            fetched_at=datetime.now(UTC),
            version=str(metadata.get("version", "")),
            source=self.name,
        )

    async def health_check_async(self) -> bool:
        """Check if Vault is healthy and reachable."""
        try:
            client = await self._get_async_client()
            response = await client.get("/v1/sys/health")
            # Vault returns 200 for initialized+unsealed, 429/472/473/501/503 for other states
            return response.status_code in (200, 429)
        except Exception:
            return False

    def health_check_sync(self) -> bool:
        """Check if Vault is healthy and reachable (sync)."""
        try:
            client = self._get_sync_client()
            response = client.get("/v1/sys/health")
            return response.status_code in (200, 429)
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None

    # --- Helpers for Tier 1+2 ---

    def _normalize_metadata_path(self, path: str) -> str:
        """Normalize a Vault path to its KV v2 metadata endpoint.

        Examples:
            "secret/myapp/config" -> "/v1/secret/metadata/myapp/config"
            "secret/data/myapp"   -> "/v1/secret/metadata/myapp"  (data/ swapped for metadata/)
            "v1/secret/metadata/x" -> "/v1/secret/metadata/x" (already qualified)
        """
        path = path.lstrip("/")
        if path.startswith("v1/"):
            return f"/{path}"
        parts = path.split("/", 1)
        if len(parts) == 2:
            mount, rest = parts
            if rest.startswith("metadata/"):
                return f"/v1/{mount}/{rest}"
            if rest.startswith("data/"):
                return f"/v1/{mount}/metadata/{rest[len('data/') :]}"
            return f"/v1/{mount}/metadata/{rest}"
        return f"/v1/{path}"

    def _normalize_list_path(self, prefix: str) -> str:
        """Normalize a prefix into a KV v2 LIST URL (trailing slash required)."""
        url = self._normalize_metadata_path(prefix)
        if not url.endswith("/"):
            url += "/"
        return url

    @staticmethod
    def _encode_value_for_storage(value: bytes) -> dict[str, str]:
        """Wrap raw bytes for KV v2 storage.

        Stored under key "value" if the value is valid utf-8, else under
        "value_b64" as base64 (allowing arbitrary binary). Round-trips through
        ``get_sync(path, key="value")`` or ``key="value_b64"``.
        """
        try:
            return {"value": value.decode("utf-8")}
        except UnicodeDecodeError:
            return {"value_b64": base64.b64encode(value).decode("ascii")}

    def _permission_hint(self, operation: str) -> str:
        """Standard Vault permission hint."""
        return f"check Vault policy for '{operation}' capability on this path"

    def _parse_metadata_response(self, response_json: dict, name: str) -> SecretMetadata:
        """Convert a KV v2 GET /metadata/ response into SecretMetadata."""
        data = response_json.get("data", {}) or {}
        current_version = data.get("current_version")
        versions = data.get("versions") or {}
        return SecretMetadata(
            name=name,
            created_at=_parse_iso_datetime(data.get("created_time")),
            updated_at=_parse_iso_datetime(data.get("updated_time")),
            version=str(current_version) if current_version is not None else None,
            version_count=len(versions) if versions else None,
            tags=data.get("custom_metadata") or None,
            source=self.name,
        )

    def _parse_post_response(
        self, response_json: dict, name: str, tags: dict[str, str] | None = None
    ) -> SecretMetadata:
        """Convert a KV v2 POST /data/ response into SecretMetadata.

        POST /data/ returns only the new version's create_time and version
        number; older versions and aggregate metadata are not echoed back.
        """
        data = response_json.get("data", {}) or {}
        version = data.get("version")
        created = _parse_iso_datetime(data.get("created_time"))
        return SecretMetadata(
            name=name,
            created_at=created,
            updated_at=created,
            version=str(version) if version is not None else None,
            version_count=int(version) if isinstance(version, int) and version > 0 else None,
            tags=tags or None,
            source=self.name,
        )

    @staticmethod
    def _is_cas_conflict(body: dict) -> bool:
        """Detect a KV v2 cas (compare-and-set) conflict in an error body."""
        errors = body.get("errors") or []
        return any("check-and-set parameter" in str(e) for e in errors)

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List secrets under a prefix. Requires ``filter.prefix`` to identify the mount.

        ``filter.tags`` is ignored -- KV v2 LIST does not filter on custom_metadata
        server-side. ``filter.pattern`` is applied as a client-side fnmatch.
        Sub-paths (keys ending in "/") are excluded from results.
        """
        if not filter or not filter.prefix:
            return []

        if not self._token or self._is_token_expired():
            await self._authenticate_async()

        client = await self._get_async_client()
        url = self._normalize_list_path(filter.prefix)

        try:
            response = await client.request("LIST", url)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"list {filter.prefix} failed: {e}")

        if response.status_code == 404:
            return []
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "list", filter.prefix, self._permission_hint("list"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"list {filter.prefix} failed: HTTP {response.status_code}")

        keys = (response.json().get("data", {}) or {}).get("keys", []) or []
        results = [k for k in keys if not k.endswith("/")]
        if filter.pattern:
            results = [r for r in results if fnmatch.fnmatch(r, filter.pattern)]
        return sorted(results)

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        """List secrets under a prefix (sync). See ``list_async``."""
        if not filter or not filter.prefix:
            return []

        if not self._token or self._is_token_expired():
            self._authenticate_sync()

        client = self._get_sync_client()
        url = self._normalize_list_path(filter.prefix)

        try:
            response = client.request("LIST", url)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"list {filter.prefix} failed: {e}")

        if response.status_code == 404:
            return []
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "list", filter.prefix, self._permission_hint("list"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"list {filter.prefix} failed: HTTP {response.status_code}")

        keys = (response.json().get("data", {}) or {}).get("keys", []) or []
        results = [k for k in keys if not k.endswith("/")]
        if filter.pattern:
            results = [r for r in results if fnmatch.fnmatch(r, filter.pattern)]
        return sorted(results)

    # --- Metadata ---

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        """Get KV v2 metadata for a secret (no value returned)."""
        if not self._token or self._is_token_expired():
            await self._authenticate_async()
        client = await self._get_async_client()

        try:
            response = await client.get(self._normalize_metadata_path(path))
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")

        if response.status_code == 404:
            raise SecretNotFoundError(path, self.name)
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "read", path, self._permission_hint("read"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"get_metadata {path} failed: HTTP {response.status_code}")

        return self._parse_metadata_response(response.json(), path)

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        """Get KV v2 metadata for a secret (sync)."""
        if not self._token or self._is_token_expired():
            self._authenticate_sync()
        client = self._get_sync_client()

        try:
            response = client.get(self._normalize_metadata_path(path))
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")

        if response.status_code == 404:
            raise SecretNotFoundError(path, self.name)
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "read", path, self._permission_hint("read"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"get_metadata {path} failed: HTTP {response.status_code}")

        return self._parse_metadata_response(response.json(), path)

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new secret. Fails if it already exists (KV v2 cas=0).

        ``value`` is wrapped as ``{"value": <utf-8>}`` (or ``{"value_b64": ...}``
        for non-utf-8 bytes). ``tags`` are stored as KV v2 ``custom_metadata``
        via a separate POST to the metadata endpoint.
        """
        if not self._token or self._is_token_expired():
            await self._authenticate_async()
        client = await self._get_async_client()

        body = {"data": self._encode_value_for_storage(value), "options": {"cas": 0}}
        try:
            response = await client.post(self._normalize_kv_path(path), json=body)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"create {path} failed: {e}")

        if response.status_code == 403:
            raise SecretPermissionError(self.name, "create", path, self._permission_hint("create"))
        if response.status_code == 400 and self._is_cas_conflict(response.json()):
            raise SecretAlreadyExistsError(path, self.name)
        if response.status_code >= 400:
            raise ProviderError(self.name, f"create {path} failed: HTTP {response.status_code}")

        metadata = self._parse_post_response(response.json(), path, tags)

        if tags:
            md_url = self._normalize_metadata_path(path)
            try:
                md_response = await client.post(md_url, json={"custom_metadata": tags})
            except httpx.HTTPError as e:
                raise ProviderError(self.name, f"create {path} (tags) failed: {e}")
            if md_response.status_code == 403:
                raise SecretPermissionError(
                    self.name, "create", path, self._permission_hint("create (custom_metadata)")
                )
            if md_response.status_code >= 400:
                raise ProviderError(self.name, f"create {path} (tags) failed: HTTP {md_response.status_code}")

        return metadata

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new secret (sync). See ``create_async``."""
        if not self._token or self._is_token_expired():
            self._authenticate_sync()
        client = self._get_sync_client()

        body = {"data": self._encode_value_for_storage(value), "options": {"cas": 0}}
        try:
            response = client.post(self._normalize_kv_path(path), json=body)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"create {path} failed: {e}")

        if response.status_code == 403:
            raise SecretPermissionError(self.name, "create", path, self._permission_hint("create"))
        if response.status_code == 400 and self._is_cas_conflict(response.json()):
            raise SecretAlreadyExistsError(path, self.name)
        if response.status_code >= 400:
            raise ProviderError(self.name, f"create {path} failed: HTTP {response.status_code}")

        metadata = self._parse_post_response(response.json(), path, tags)

        if tags:
            md_url = self._normalize_metadata_path(path)
            try:
                md_response = client.post(md_url, json={"custom_metadata": tags})
            except httpx.HTTPError as e:
                raise ProviderError(self.name, f"create {path} (tags) failed: {e}")
            if md_response.status_code == 403:
                raise SecretPermissionError(
                    self.name, "create", path, self._permission_hint("create (custom_metadata)")
                )
            if md_response.status_code >= 400:
                raise ProviderError(self.name, f"create {path} (tags) failed: HTTP {md_response.status_code}")

        return metadata

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing secret (creates a new version). Fails if absent.

        The update is a two-step pre-check + POST: first GET /metadata/ to map
        absence cleanly to ``SecretNotFoundError`` (KV v2 has no native
        "must-exist" precondition for write), then POST /data/.
        """
        if not self._token or self._is_token_expired():
            await self._authenticate_async()
        client = await self._get_async_client()

        # Pre-check existence -- maps to SecretNotFoundError if absent.
        await self.get_metadata_async(path)

        body = {"data": self._encode_value_for_storage(value)}
        try:
            response = await client.post(self._normalize_kv_path(path), json=body)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"update {path} failed: {e}")

        if response.status_code == 403:
            raise SecretPermissionError(self.name, "update", path, self._permission_hint("update"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"update {path} failed: HTTP {response.status_code}")

        return self._parse_post_response(response.json(), path)

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing secret (sync). See ``update_async``."""
        if not self._token or self._is_token_expired():
            self._authenticate_sync()
        client = self._get_sync_client()

        self.get_metadata_sync(path)

        body = {"data": self._encode_value_for_storage(value)}
        try:
            response = client.post(self._normalize_kv_path(path), json=body)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"update {path} failed: {e}")

        if response.status_code == 403:
            raise SecretPermissionError(self.name, "update", path, self._permission_hint("update"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"update {path} failed: HTTP {response.status_code}")

        return self._parse_post_response(response.json(), path)

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Delete a secret entirely (DELETE /metadata/ destroys all versions)."""
        if not self._token or self._is_token_expired():
            await self._authenticate_async()
        client = await self._get_async_client()

        # Pre-check existence so callers see SecretNotFoundError, not silent success.
        await self.get_metadata_async(path)

        url = self._normalize_metadata_path(path)
        try:
            response = await client.delete(url)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"delete {path} failed: {e}")

        if response.status_code == 403:
            raise SecretPermissionError(self.name, "delete", path, self._permission_hint("delete"))
        if response.status_code not in (200, 204):
            raise ProviderError(self.name, f"delete {path} failed: HTTP {response.status_code}")

    def delete_sync(self, path: str) -> None:
        """Delete a secret entirely (sync)."""
        if not self._token or self._is_token_expired():
            self._authenticate_sync()
        client = self._get_sync_client()

        self.get_metadata_sync(path)

        url = self._normalize_metadata_path(path)
        try:
            response = client.delete(url)
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"delete {path} failed: {e}")

        if response.status_code == 403:
            raise SecretPermissionError(self.name, "delete", path, self._permission_hint("delete"))
        if response.status_code not in (200, 204):
            raise ProviderError(self.name, f"delete {path} failed: HTTP {response.status_code}")

    # --- Versioning ---

    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        """Fetch a specific version of a secret."""
        if not self._token or self._is_token_expired():
            await self._authenticate_async()
        client = await self._get_async_client()

        url = self._normalize_kv_path(path)
        try:
            response = await client.get(url, params={"version": version})
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")

        if response.status_code == 404:
            # KV v2 returns 404 for both missing secret and missing version;
            # disambiguate via metadata (cheap second call only on the failure path).
            try:
                await self.get_metadata_async(path)
            except SecretNotFoundError:
                raise SecretNotFoundError(path, self.name)
            raise SecretVersionNotFoundError(path, version, self.name)
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "read", path, self._permission_hint("read"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: HTTP {response.status_code}")

        return self._parse_kv_response(response.json(), path, key)

    def get_version_sync(self, path: str, version: str, key: str | None = None) -> SecretValue:
        """Fetch a specific version of a secret (sync)."""
        if not self._token or self._is_token_expired():
            self._authenticate_sync()
        client = self._get_sync_client()

        url = self._normalize_kv_path(path)
        try:
            response = client.get(url, params={"version": version})
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")

        if response.status_code == 404:
            try:
                self.get_metadata_sync(path)
            except SecretNotFoundError:
                raise SecretNotFoundError(path, self.name)
            raise SecretVersionNotFoundError(path, version, self.name)
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "read", path, self._permission_hint("read"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: HTTP {response.status_code}")

        return self._parse_kv_response(response.json(), path, key)

    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        """List all versions of a secret, newest first."""
        if not self._token or self._is_token_expired():
            await self._authenticate_async()
        client = await self._get_async_client()

        try:
            response = await client.get(self._normalize_metadata_path(path))
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")

        if response.status_code == 404:
            raise SecretNotFoundError(path, self.name)
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "read", path, self._permission_hint("read"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"list_versions {path} failed: HTTP {response.status_code}")

        return self._build_version_list(response.json(), path)

    def list_versions_sync(self, path: str) -> list[SecretMetadata]:
        """List all versions of a secret, newest first (sync)."""
        if not self._token or self._is_token_expired():
            self._authenticate_sync()
        client = self._get_sync_client()

        try:
            response = client.get(self._normalize_metadata_path(path))
        except httpx.HTTPError as e:
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")

        if response.status_code == 404:
            raise SecretNotFoundError(path, self.name)
        if response.status_code == 403:
            raise SecretPermissionError(self.name, "read", path, self._permission_hint("read"))
        if response.status_code >= 400:
            raise ProviderError(self.name, f"list_versions {path} failed: HTTP {response.status_code}")

        return self._build_version_list(response.json(), path)

    def _build_version_list(self, response_json: dict, name: str) -> list[SecretMetadata]:
        """Turn KV v2 ``data.versions`` dict into a newest-first list of SecretMetadata."""
        data = response_json.get("data", {}) or {}
        versions = data.get("versions") or {}
        tags = data.get("custom_metadata") or None

        items: list[SecretMetadata] = []
        for v_str, v_meta in versions.items():
            try:
                v_int = int(v_str)
            except (TypeError, ValueError):
                continue
            items.append(
                SecretMetadata(
                    name=name,
                    created_at=_parse_iso_datetime(v_meta.get("created_time")),
                    updated_at=_parse_iso_datetime(v_meta.get("deletion_time"))
                    or _parse_iso_datetime(v_meta.get("created_time")),
                    version=str(v_int),
                    version_count=None,
                    tags=tags,
                    source=self.name,
                )
            )
        items.sort(key=lambda m: int(m.version) if m.version else 0, reverse=True)
        return items


__all__ = ["HTTPX_AVAILABLE", "OpenBaoProvider"]
