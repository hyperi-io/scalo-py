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
    from google.api_core.exceptions import AlreadyExists, NotFound, PermissionDenied, Unauthenticated
    from google.cloud import secretmanager

    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False
    secretmanager = None  # type: ignore[assignment]
    AlreadyExists = Exception  # type: ignore[assignment,misc]
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

    # --- Helpers for Tier 1+2 ---

    def _parent(self) -> str:
        """Build the GCP parent resource for the configured project."""
        return f"projects/{self._config.project_id}"

    def _secret_name(self, path: str) -> str:
        """Build the full resource name for a Secret (no version)."""
        if path.startswith("projects/"):
            # Strip /versions/X if present so this returns the Secret resource
            if "/versions/" in path:
                return path.split("/versions/")[0]
            return path
        return f"projects/{self._config.project_id}/secrets/{path}"

    def _version_resource_name(self, path: str, version: str) -> str:
        """Build the full resource name for a SecretVersion."""
        secret = self._secret_name(path)
        return f"{secret}/versions/{version}"

    def _gcp_hint(self, operation: str) -> str:
        """IAM permission hint for GCP per HyperI spec."""
        return f"check IAM role for secretmanager.secrets.{operation}"

    @staticmethod
    def _short_name(full_name: str) -> str:
        """Return ``foo`` from ``projects/X/secrets/foo`` (or ``foo`` from ``foo``)."""
        if "/secrets/" not in full_name:
            return full_name
        tail = full_name.split("/secrets/", 1)[1]
        # Strip /versions/N suffix if present
        return tail.split("/", 1)[0]

    def _secret_to_metadata(self, secret, version_count: int | None = None) -> SecretMetadata:
        """Convert a google.cloud.secretmanager_v1.types.Secret into SecretMetadata."""
        labels = dict(secret.labels) if getattr(secret, "labels", None) else None
        return SecretMetadata(
            name=self._short_name(secret.name),
            created_at=self._dt_from_protobuf(getattr(secret, "create_time", None)),
            updated_at=None,  # GCP Secret resource itself doesn't track update time
            expires_at=self._dt_from_protobuf(getattr(secret, "expire_time", None)),
            version=None,  # filled by caller if known
            version_count=version_count,
            tags=labels or None,
            source=self.name,
        )

    def _version_to_metadata(self, version, secret_name: str) -> SecretMetadata:
        """Convert a google.cloud.secretmanager_v1.types.SecretVersion into SecretMetadata."""
        version_id = version.name.split("/versions/")[-1] if version.name else None
        return SecretMetadata(
            name=self._short_name(secret_name),
            created_at=self._dt_from_protobuf(getattr(version, "create_time", None)),
            updated_at=self._dt_from_protobuf(getattr(version, "destroy_time", None))
            or self._dt_from_protobuf(getattr(version, "create_time", None)),
            expires_at=None,
            version=version_id,
            version_count=None,
            tags=None,
            source=self.name,
        )

    @staticmethod
    def _dt_from_protobuf(proto_ts) -> datetime | None:
        """Convert a google.protobuf.timestamp_pb2.Timestamp (or compatible) to datetime."""
        if proto_ts is None:
            return None
        # Both real Timestamp and proto-plus DatetimeWithNanoseconds expose .seconds/.nanos
        # or work as datetime themselves.
        if isinstance(proto_ts, datetime):
            return proto_ts if proto_ts.tzinfo else proto_ts.replace(tzinfo=UTC)
        try:
            ts = proto_ts.timestamp_pb()
            return datetime.fromtimestamp(ts.seconds + ts.nanos / 1e9, tz=UTC)
        except AttributeError:
            try:
                seconds = getattr(proto_ts, "seconds", 0)
                nanos = getattr(proto_ts, "nanos", 0)
                return datetime.fromtimestamp(seconds + nanos / 1e9, tz=UTC)
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _build_filter(filter: SecretFilter | None) -> str:
        """Translate a SecretFilter into GCP's filter syntax for list_secrets."""
        if not filter:
            return ""
        parts = []
        if filter.prefix:
            parts.append(f"name:{filter.prefix}")
        if filter.tags:
            for k, v in filter.tags.items():
                parts.append(f"labels.{k}={v}")
        return " AND ".join(parts)

    def _post_filter(self, names: list[str], filter: SecretFilter | None) -> list[str]:
        """Apply client-side fnmatch on already-filtered names."""
        import fnmatch

        if filter and filter.pattern:
            names = [n for n in names if fnmatch.fnmatch(n, filter.pattern)]
        return sorted(names)

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            request = {"parent": self._parent()}
            filter_str = self._build_filter(filter)
            if filter_str:
                request["filter"] = filter_str
            page_result = await async_client.list_secrets(request=request)
            names: list[str] = []
            async for secret in page_result:
                names.append(self._short_name(secret.name))
            return self._post_filter(names, filter)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(
                self.name, "list", filter.prefix if filter and filter.prefix else "*", self._gcp_hint("list")
            )
        except Exception as e:
            raise ProviderError(self.name, f"list failed: {e}")

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        try:
            client = self._get_sync_client()
            request = {"parent": self._parent()}
            filter_str = self._build_filter(filter)
            if filter_str:
                request["filter"] = filter_str
            names: list[str] = []
            for secret in client.list_secrets(request=request):
                names.append(self._short_name(secret.name))
            return self._post_filter(names, filter)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(
                self.name, "list", filter.prefix if filter and filter.prefix else "*", self._gcp_hint("list")
            )
        except Exception as e:
            raise ProviderError(self.name, f"list failed: {e}")

    # --- Metadata ---

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            secret = await async_client.get_secret(request={"name": self._secret_name(path)})

            # Fill in version details with a list_secret_versions call (cheap; usually one page).
            version_count = 0
            current_version: str | None = None
            page_result = await async_client.list_secret_versions(request={"parent": self._secret_name(path)})
            async for v in page_result:
                version_count += 1
                if current_version is None and getattr(v, "state", None) and "ENABLED" in str(v.state):
                    current_version = v.name.split("/versions/")[-1]

            meta = self._secret_to_metadata(secret, version_count=version_count or None)
            meta.version = current_version
            return meta
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "get", path, self._gcp_hint("get"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        try:
            client = self._get_sync_client()
            secret = client.get_secret(request={"name": self._secret_name(path)})

            version_count = 0
            current_version: str | None = None
            for v in client.list_secret_versions(request={"parent": self._secret_name(path)}):
                version_count += 1
                if current_version is None and getattr(v, "state", None) and "ENABLED" in str(v.state):
                    current_version = v.name.split("/versions/")[-1]

            meta = self._secret_to_metadata(secret, version_count=version_count or None)
            meta.version = current_version
            return meta
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "get", path, self._gcp_hint("get"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_metadata {path} failed: {e}")

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)

            secret_body: dict = {"replication": {"automatic": {}}}
            if tags:
                secret_body["labels"] = tags
            secret = await async_client.create_secret(
                request={"parent": self._parent(), "secret_id": path, "secret": secret_body}
            )
            version = await async_client.add_secret_version(request={"parent": secret.name, "payload": {"data": value}})
            meta = self._secret_to_metadata(secret, version_count=1)
            meta.version = version.name.split("/versions/")[-1]
            return meta
        except AlreadyExists:
            raise SecretAlreadyExistsError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "create", path, self._gcp_hint("create"))
        except (SecretAlreadyExistsError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"create {path} failed: {e}")

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        try:
            client = self._get_sync_client()
            secret_body: dict = {"replication": {"automatic": {}}}
            if tags:
                secret_body["labels"] = tags
            secret = client.create_secret(request={"parent": self._parent(), "secret_id": path, "secret": secret_body})
            version = client.add_secret_version(request={"parent": secret.name, "payload": {"data": value}})
            meta = self._secret_to_metadata(secret, version_count=1)
            meta.version = version.name.split("/versions/")[-1]
            return meta
        except AlreadyExists:
            raise SecretAlreadyExistsError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "create", path, self._gcp_hint("create"))
        except (SecretAlreadyExistsError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"create {path} failed: {e}")

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update by adding a new SecretVersion. GCP secrets are immutable per version;
        ``update`` semantics map to ``add_secret_version`` on the existing Secret resource.
        """
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            version = await async_client.add_secret_version(
                request={"parent": self._secret_name(path), "payload": {"data": value}}
            )
            secret = await async_client.get_secret(request={"name": self._secret_name(path)})
            meta = self._secret_to_metadata(secret)
            meta.version = version.name.split("/versions/")[-1]
            return meta
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "update", path, self._gcp_hint("update"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"update {path} failed: {e}")

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        try:
            client = self._get_sync_client()
            version = client.add_secret_version(request={"parent": self._secret_name(path), "payload": {"data": value}})
            secret = client.get_secret(request={"name": self._secret_name(path)})
            meta = self._secret_to_metadata(secret)
            meta.version = version.name.split("/versions/")[-1]
            return meta
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "update", path, self._gcp_hint("update"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"update {path} failed: {e}")

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Delete the entire Secret resource (all versions)."""
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            await async_client.delete_secret(request={"name": self._secret_name(path)})
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "delete", path, self._gcp_hint("delete"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"delete {path} failed: {e}")

    def delete_sync(self, path: str) -> None:
        try:
            client = self._get_sync_client()
            client.delete_secret(request={"name": self._secret_name(path)})
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "delete", path, self._gcp_hint("delete"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"delete {path} failed: {e}")

    # --- Versioning ---

    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            response = await async_client.access_secret_version(
                request={"name": self._version_resource_name(path, version)}
            )
            data = self._parse_payload(response.payload.data, path, key)
            return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except NotFound:
            # Disambiguate: secret missing vs version missing
            try:
                await self.get_metadata_async(path)
            except SecretNotFoundError:
                raise SecretNotFoundError(path, self.name)
            raise SecretVersionNotFoundError(path, version, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "get", path, self._gcp_hint("get"))
        except (SecretNotFoundError, SecretVersionNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")

    def get_version_sync(self, path: str, version: str, key: str | None = None) -> SecretValue:
        try:
            client = self._get_sync_client()
            response = client.access_secret_version(request={"name": self._version_resource_name(path, version)})
            data = self._parse_payload(response.payload.data, path, key)
            return SecretValue(data=data, fetched_at=datetime.now(UTC), version=version, source=self.name)
        except NotFound:
            try:
                self.get_metadata_sync(path)
            except SecretNotFoundError:
                raise SecretNotFoundError(path, self.name)
            raise SecretVersionNotFoundError(path, version, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "get", path, self._gcp_hint("get"))
        except (SecretNotFoundError, SecretVersionNotFoundError, SecretPermissionError, ProviderError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"get_version {path}@{version} failed: {e}")

    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        try:
            credentials = self._credentials()
            kwargs = {"credentials": credentials} if credentials else {}
            async_client = secretmanager.SecretManagerServiceAsyncClient(**kwargs)
            secret_name = self._secret_name(path)
            page_result = await async_client.list_secret_versions(request={"parent": secret_name})
            items: list[SecretMetadata] = []
            async for v in page_result:
                items.append(self._version_to_metadata(v, secret_name))
            items.sort(key=lambda m: m.created_at or datetime.fromtimestamp(0, tz=UTC), reverse=True)
            return items
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "list", path, self._gcp_hint("list"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")

    def list_versions_sync(self, path: str) -> list[SecretMetadata]:
        try:
            client = self._get_sync_client()
            secret_name = self._secret_name(path)
            items: list[SecretMetadata] = []
            for v in client.list_secret_versions(request={"parent": secret_name}):
                items.append(self._version_to_metadata(v, secret_name))
            items.sort(key=lambda m: m.created_at or datetime.fromtimestamp(0, tz=UTC), reverse=True)
            return items
        except NotFound:
            raise SecretNotFoundError(path, self.name)
        except (PermissionDenied, Unauthenticated):
            raise SecretPermissionError(self.name, "list", path, self._gcp_hint("list"))
        except (SecretNotFoundError, SecretPermissionError):
            raise
        except Exception as e:
            raise ProviderError(self.name, f"list_versions {path} failed: {e}")


__all__ = ["GCP_AVAILABLE", "GCPProvider"]
