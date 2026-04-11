# Project:   hyperi-pylib
# File:      secrets/providers/gcp.py
# Purpose:   GCP Secret Manager secrets provider
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""GCP Secret Manager provider."""

import json
import logging
from datetime import UTC, datetime

from ..exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
    SecretVersionNotFoundError,
)
from ..types import GCPConfig, SecretFilter, SecretMetadata, SecretValue
from .base import VersionedProvider

logger = logging.getLogger(__name__)

try:
    from google.api_core.exceptions import NotFound, PermissionDenied, Unauthenticated
    from google.cloud import secretmanager

    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False
    secretmanager = None  # type: ignore[assignment]
    NotFound = Exception  # type: ignore[assignment,misc]
    PermissionDenied = Exception  # type: ignore[assignment,misc]
    Unauthenticated = Exception  # type: ignore[assignment,misc]


class GCPProvider(VersionedProvider):
    """GCP Secret Manager provider.

    Uses google-cloud-secret-manager with Application Default Credentials (ADC)
    or an explicit service account key file.

    Features:
    - Native async via SecretManagerServiceAsyncClient
    - JSON key extraction
    - Version tracking
    - ADC credential chain (env, service account file, metadata server)
    """

    def __init__(self, config: GCPConfig) -> None:
        """Initialise GCP provider.

        Args:
            config: GCP configuration.

        Raises:
            ProviderNotAvailableError: google-cloud-secret-manager not installed.
        """
        if not GCP_AVAILABLE:
            from ..exceptions import ProviderNotAvailableError

            raise ProviderNotAvailableError(
                "gcp",
                "google-cloud-secret-manager",
                "pip install hyperi-pylib[secrets-gcp]",
            )
        self._config = config
        self._sync_client = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "gcp"

    def _version_name(self, path: str) -> str:
        """Build full secret version resource name."""
        if path.startswith("projects/"):
            return path if "/versions/" in path else f"{path}/versions/latest"
        return f"projects/{self._config.project_id}/secrets/{path}/versions/latest"

    def _credentials(self):
        """Return service account credentials, or None to use ADC."""
        if not self._config.credentials_file:
            return None
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(
            self._config.credentials_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

    def _get_sync_client(self):
        """Get or create sync Secret Manager client."""
        if self._sync_client is None:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            self._sync_client = secretmanager.SecretManagerServiceClient(**kwargs)
        return self._sync_client

    def _parse_payload(self, data: bytes, path: str, key: str | None) -> bytes:
        """Extract key from JSON payload, or return raw bytes."""
        if key is None:
            return data
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise ProviderError(self.name, f"invalid JSON in {path}: {e}")
        if key not in parsed:
            raise SecretNotFoundError(f"{path}[{key}]", self.name)
        value = parsed[key]
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value).encode("utf-8")

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from GCP Secret Manager.

        Args:
            path: Secret ID or full resource name (projects/.../secrets/...).
            key: Optional key to extract from JSON secret.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: GCP request failed.
        """
        name = self._version_name(path)
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            response = await async_client.access_secret_version(request={"name": name})
            data = self._parse_payload(response.payload.data, path, key)
            version = response.name.split("/versions/")[-1]
            return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated) as e:
            raise ProviderError(self.name, f"authentication/permission error: {e}")
        except (SecretNotFoundError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"request failed: {e}")

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from GCP Secret Manager (sync).

        Args:
            path: Secret ID or full resource name.
            key: Optional key to extract from JSON secret.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: GCP request failed.
        """
        name = self._version_name(path)
        try:
            client = self._get_sync_client()
            response = client.access_secret_version(request={"name": name})
            data = self._parse_payload(response.payload.data, path, key)
            version = response.name.split("/versions/")[-1]
            return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated) as e:
            raise ProviderError(self.name, f"authentication/permission error: {e}")
        except (SecretNotFoundError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"request failed: {e}")

    async def health_check_async(self) -> bool:
        """Check if GCP Secret Manager is reachable."""
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            parent = f"projects/{self._config.project_id}"
            await async_client.list_secrets(request={"parent": parent, "page_size": 1})
            return True
        except Exception:
            return False

    def health_check_sync(self) -> bool:
        """Check if GCP Secret Manager is reachable (sync)."""
        try:
            client = self._get_sync_client()
            parent = f"projects/{self._config.project_id}"
            client.list_secrets(request={"parent": parent, "page_size": 1})
            return True
        except Exception:
            return False

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


__all__ = ["GCPProvider", "GCP_AVAILABLE"]
