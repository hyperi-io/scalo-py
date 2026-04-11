"""OpenBao/Vault secret provider with httpx async support."""

from __future__ import annotations

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

        jwt = token_path.read_text().strip()
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

        jwt = token_path.read_text().strip()
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

    # --- Stubs for new abstract methods (to be implemented) ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        raise NotImplementedError("not yet implemented")

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        raise NotImplementedError("not yet implemented")

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        raise NotImplementedError("not yet implemented")

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        raise NotImplementedError("not yet implemented")

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        raise NotImplementedError("not yet implemented")

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        raise NotImplementedError("not yet implemented")

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        raise NotImplementedError("not yet implemented")

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        raise NotImplementedError("not yet implemented")

    async def delete_async(self, path: str) -> None:
        raise NotImplementedError("not yet implemented")

    def delete_sync(self, path: str) -> None:
        raise NotImplementedError("not yet implemented")

    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        raise NotImplementedError("not yet implemented")

    def get_version_sync(self, path: str, version: str, key: str | None = None) -> SecretValue:
        raise NotImplementedError("not yet implemented")

    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        raise NotImplementedError("not yet implemented")

    def list_versions_sync(self, path: str) -> list[SecretMetadata]:
        raise NotImplementedError("not yet implemented")


__all__ = ["OpenBaoProvider", "HTTPX_AVAILABLE"]
