"""AWS Secrets Manager provider with aiobotocore async support."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import override

from ...concurrency import run_blocking
from ..exceptions import (
    ProviderError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPendingDeletionError,
    SecretPermissionError,
    SecretVersionNotFoundError,
)
from ..types import AWSConfig, SecretFilter, SecretMetadata, SecretValue
from .base import HealthLog, VersionedProvider, credential_digest

logger = logging.getLogger(__name__)

# Optional boto3/aiobotocore support
try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    # The constructor raises before any use of boto3 or ClientError.
    BOTO3_AVAILABLE = False

try:
    from aiobotocore.session import get_session as get_aiobotocore_session

    AIOBOTOCORE_AVAILABLE = True
except ImportError:
    # Every use of get_aiobotocore_session is guarded by AIOBOTOCORE_AVAILABLE.
    AIOBOTOCORE_AVAILABLE = False

# AWS reports a name inside its recovery window only as InvalidRequestException, so the message decides.
_PENDING_DELETION = re.compile(r"(?:marked|scheduled) for deletion|marked deleted", re.IGNORECASE)


class AWSProvider(VersionedProvider):
    """AWS Secrets Manager provider.

    Uses boto3 for sync operations and aiobotocore for async operations.

    Features:
    - Native async with aiobotocore
    - JSON key extraction
    - Version tracking
    - Automatic credential chain
    """

    def __init__(self, config: AWSConfig) -> None:
        """Initialize AWS provider.

        Args:
            config: AWS configuration.

        Raises:
            ProviderNotAvailableError: boto3 not installed.
        """
        if not BOTO3_AVAILABLE:
            from ..exceptions import ProviderNotAvailableError

            raise ProviderNotAvailableError("aws", "boto3", "pip install boto3 or pip install scalo[secrets-aws]")

        self._config = config
        self._sync_client = None
        self._session = None
        self._health = HealthLog(logger, self.name)

    @property
    def name(self) -> str:
        """Provider name."""
        return "aws"

    def cache_identity(self, salt: bytes) -> tuple[str, ...]:
        """See base class."""
        return (
            self.name,
            self._config.region or "",
            self._config.endpoint_url or "",
            credential_digest(self._config.access_key_id, salt),
        )

    def _get_client_kwargs(self) -> dict:
        """Get kwargs for boto3/aiobotocore client creation."""
        kwargs: dict = {"service_name": "secretsmanager"}

        # An unset region is left to the SDK chain, never pinned to a default.
        if self._config.region:
            kwargs["region_name"] = self._config.region

        if self._config.endpoint_url:
            kwargs["endpoint_url"] = self._config.endpoint_url

        if self._config.access_key_id and self._config.secret_access_key:
            kwargs["aws_access_key_id"] = self._config.access_key_id
            kwargs["aws_secret_access_key"] = self._config.secret_access_key

        return kwargs

    def _get_sync_client(self):
        """Get or create sync boto3 client."""
        if self._sync_client is None:
            kwargs = self._get_client_kwargs()
            # Add timeout config for sync client
            from botocore.config import Config

            kwargs["config"] = Config(
                connect_timeout=self._config.timeout_secs,
                read_timeout=self._config.timeout_secs,
            )
            self._sync_client = boto3.client(**kwargs)
        return self._sync_client

    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from AWS Secrets Manager.

        Args:
            path: Secret ID or ARN.
            key: Optional key within JSON secret.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: AWS request failed.
        """
        if not AIOBOTOCORE_AVAILABLE:
            # Fall back to sync in thread pool if aiobotocore not available

            return await run_blocking(self.get_sync, path, key)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.get_secret_value(SecretId=path)
                return self._parse_response(response, path, key)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise SecretNotFoundError(path, self.name)
            elif error_code == "AccessDeniedException":
                raise SecretPermissionError(self.name, "GetSecretValue", path, self._aws_hint("GetSecretValue"))
            elif error_code == "DecryptionFailure":
                raise ProviderError(self.name, f"decryption failed for {path}")
            elif self._is_pending_deletion(e):
                raise SecretPendingDeletionError(self.name, "GetSecretValue", path)
            else:
                raise ProviderError(self.name, f"AWS error: {error_code}")
        except Exception as e:
            if isinstance(e, (SecretNotFoundError, ProviderError)):
                raise
            raise ProviderError(self.name, f"request failed: {e}")

    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Get secret from AWS Secrets Manager (sync).

        Args:
            path: Secret ID or ARN.
            key: Optional key within JSON secret.

        Returns:
            SecretValue with secret data.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: AWS request failed.
        """
        client = self._get_sync_client()

        try:
            response = client.get_secret_value(SecretId=path)
            return self._parse_response(response, path, key)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise SecretNotFoundError(path, self.name)
            elif error_code == "AccessDeniedException":
                raise SecretPermissionError(self.name, "GetSecretValue", path, self._aws_hint("GetSecretValue"))
            elif error_code == "DecryptionFailure":
                raise ProviderError(self.name, f"decryption failed for {path}")
            elif self._is_pending_deletion(e):
                raise SecretPendingDeletionError(self.name, "GetSecretValue", path)
            else:
                raise ProviderError(self.name, f"AWS error: {error_code}")
        except Exception as e:
            if isinstance(e, (SecretNotFoundError, ProviderError)):
                raise
            raise ProviderError(self.name, f"request failed: {e}")

    def _parse_response(self, response: dict, path: str, key: str | None) -> SecretValue:
        """Parse AWS response into SecretValue."""
        # Get secret value (string or binary)
        if "SecretString" in response:
            secret_string = response["SecretString"]
            data = secret_string.encode("utf-8")

            # Extract key from JSON if requested
            if key is not None:
                try:
                    parsed = json.loads(secret_string)
                except json.JSONDecodeError as e:
                    raise ProviderError(self.name, f"invalid JSON in {path}: {e}")

                if key not in parsed:
                    raise SecretNotFoundError(f"{path}[{key}]", self.name)

                value = parsed[key]
                if isinstance(value, bytes):
                    data = value
                elif isinstance(value, str):
                    data = value.encode("utf-8")
                else:
                    data = json.dumps(value).encode("utf-8")

        elif "SecretBinary" in response:
            data = response["SecretBinary"]
            if key is not None:
                raise ProviderError(self.name, f"cannot extract key from binary secret: {path}")
        else:
            raise ProviderError(self.name, f"no secret value in response for {path}")

        return SecretValue(
            data=data,
            fetched_at=datetime.now(UTC),
            version=response.get("VersionId"),
            source=self.name,
        )

    async def _probe_async(self) -> None:
        session = get_aiobotocore_session()
        async with session.create_client(**self._get_client_kwargs()) as client:
            # List secrets with max 1 result to test connectivity
            await client.list_secrets(MaxResults=1)

    def _probe_sync(self) -> None:
        self._get_sync_client().list_secrets(MaxResults=1)

    async def health_check_async(self) -> bool:
        """Check if AWS Secrets Manager is reachable, logging the reason once when it is not."""
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.health_check_sync)
        return await self._health.arun(self._probe_async)

    def health_check_sync(self) -> bool:
        """Check if AWS Secrets Manager is reachable (sync), logging the reason once when it is not."""
        return self._health.run(self._probe_sync)

    # --- Helpers for Tier 1+2 ---

    @staticmethod
    def _encode_value(value: bytes) -> dict:
        """Pick SecretString vs SecretBinary based on utf-8 validity."""
        try:
            return {"SecretString": value.decode("utf-8")}
        except UnicodeDecodeError:
            return {"SecretBinary": value}

    def _aws_hint(self, operation: str) -> str:
        """IAM permission hint for this operation."""
        return f"check IAM policy for secretsmanager:{operation} permission"

    @staticmethod
    def _is_pending_deletion(error: ClientError) -> bool:
        """Whether AWS refused the call because the secret is inside its recovery window."""
        detail = error.response.get("Error", {})
        return detail.get("Code") == "InvalidRequestException" and bool(
            _PENDING_DELETION.search(detail.get("Message") or "")
        )

    def _map_client_error(self, error: ClientError, operation: str, path: str) -> Exception:
        """Map a botocore ClientError to the appropriate domain exception."""
        code = error.response.get("Error", {}).get("Code", "")
        if code == "ResourceNotFoundException":
            return SecretNotFoundError(path, self.name)
        if code == "ResourceExistsException":
            return SecretAlreadyExistsError(path, self.name)
        if code == "AccessDeniedException":
            return SecretPermissionError(self.name, operation, path, self._aws_hint(operation))
        if self._is_pending_deletion(error):
            return SecretPendingDeletionError(self.name, operation, path)
        return ProviderError(self.name, f"{operation} {path} failed: {code or 'unknown'}")

    def _to_metadata(self, response: dict, fallback_name: str | None = None) -> SecretMetadata:
        """Convert a describe_secret / create_secret / update_secret response into SecretMetadata."""
        name = response.get("Name") or fallback_name or ""
        tag_list = response.get("Tags") or []
        tags = {t["Key"]: t["Value"] for t in tag_list if "Key" in t and "Value" in t} or None

        version_stages = response.get("VersionIdsToStages") or {}
        current_version: str | None = None
        for vid, stages in version_stages.items():
            if "AWSCURRENT" in stages:
                current_version = vid
                break
        if current_version is None:
            # create_secret / update_secret returns just VersionId at the top level
            current_version = response.get("VersionId")

        return SecretMetadata(
            name=name,
            created_at=response.get("CreatedDate"),
            updated_at=response.get("LastChangedDate") or response.get("CreatedDate"),
            expires_at=response.get("NextRotationDate"),
            version=current_version,
            version_count=len(version_stages) if version_stages else None,
            tags=tags,
            source=self.name,
        )

    @staticmethod
    def _tags_for_aws(tags: dict[str, str] | None) -> list[dict[str, str]] | None:
        """Encode a tag dict to AWS Tags list shape."""
        if not tags:
            return None
        return [{"Key": k, "Value": v} for k, v in tags.items()]

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret names matching ``filter``.

        ``filter.prefix`` filters server-side, ``filter.tags`` use AWS
        tag-key/tag-value filters, and ``filter.pattern`` is a client-side fnmatch.
        """
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.list_sync, filter)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()
        aws_filters = self._build_list_filters(filter)

        names: list[str] = []
        try:
            async with session.create_client(**kwargs) as client:
                next_token: str | None = None
                while True:
                    params: dict = {"MaxResults": 100}
                    if aws_filters:
                        params["Filters"] = aws_filters
                    if next_token:
                        params["NextToken"] = next_token
                    response = await client.list_secrets(**params)
                    names.extend(s.get("Name", "") for s in response.get("SecretList", []) if s.get("Name"))
                    next_token = response.get("NextToken")
                    if not next_token:
                        break
        except ClientError as e:
            raise self._map_client_error(e, "list", filter.prefix if filter and filter.prefix else "*")

        return self._post_filter(names, filter)

    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret names (sync)."""
        client = self._get_sync_client()
        aws_filters = self._build_list_filters(filter)

        names: list[str] = []
        try:
            paginator = client.get_paginator("list_secrets")
            paginate_kwargs: dict = {"MaxResults": 100}
            if aws_filters:
                paginate_kwargs["Filters"] = aws_filters
            for page in paginator.paginate(**paginate_kwargs):
                names.extend(s.get("Name", "") for s in page.get("SecretList", []) if s.get("Name"))
        except ClientError as e:
            raise self._map_client_error(e, "list", filter.prefix if filter and filter.prefix else "*")

        return self._post_filter(names, filter)

    @staticmethod
    def _build_list_filters(filter: SecretFilter | None) -> list[dict] | None:
        """Translate a SecretFilter into AWS list_secrets Filters list."""
        if not filter:
            return None
        aws_filters: list[dict] = []
        if filter.prefix:
            aws_filters.append({"Key": "name", "Values": [filter.prefix]})
        if filter.tags:
            for k, v in filter.tags.items():
                aws_filters.append({"Key": "tag-key", "Values": [k]})
                aws_filters.append({"Key": "tag-value", "Values": [v]})
        return aws_filters or None

    @staticmethod
    def _post_filter(names: list[str], filter: SecretFilter | None) -> list[str]:
        """Apply client-side fnmatch on already-filtered names."""
        import fnmatch

        if filter and filter.pattern:
            names = [n for n in names if fnmatch.fnmatch(n, filter.pattern)]
        return sorted(names)

    # --- Metadata ---

    @override
    async def get_metadata_async(self, path: str) -> SecretMetadata:
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.get_metadata_sync, path)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.describe_secret(SecretId=path)
                return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "describe", path)

    @override
    def get_metadata_sync(self, path: str) -> SecretMetadata:
        client = self._get_sync_client()
        try:
            response = client.describe_secret(SecretId=path)
            return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "describe", path)

    # --- Create ---

    def _create_kwargs(self, path: str, value: bytes, tags: dict[str, str] | None) -> dict:
        """CreateSecret arguments, carrying the configured KMS key when one is set."""
        api_kwargs: dict = {"Name": path, **self._encode_value(value)}
        aws_tags = self._tags_for_aws(tags)
        if aws_tags:
            api_kwargs["Tags"] = aws_tags
        if self._config.kms_key_id:
            api_kwargs["KmsKeyId"] = self._config.kms_key_id
        return api_kwargs

    @override
    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.create_sync, path, value, tags)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()
        api_kwargs = self._create_kwargs(path, value, tags)

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.create_secret(**api_kwargs)
                meta = self._to_metadata(response, fallback_name=path)
                if tags and not meta.tags:
                    meta.tags = tags  # AWS create response doesn't echo Tags
                return meta
        except ClientError as e:
            raise self._map_client_error(e, "CreateSecret", path)

    @override
    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        client = self._get_sync_client()
        api_kwargs = self._create_kwargs(path, value, tags)

        try:
            response = client.create_secret(**api_kwargs)
            meta = self._to_metadata(response, fallback_name=path)
            if tags and not meta.tags:
                meta.tags = tags
            return meta
        except ClientError as e:
            raise self._map_client_error(e, "CreateSecret", path)

    # --- Update ---

    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing secret. Maps ResourceNotFoundException to SecretNotFoundError."""
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.update_sync, path, value)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.update_secret(SecretId=path, **self._encode_value(value))
                return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "UpdateSecret", path)

    @override
    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        client = self._get_sync_client()
        try:
            response = client.update_secret(SecretId=path, **self._encode_value(value))
            return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "UpdateSecret", path)

    # --- Delete ---

    def _delete_kwargs(self, path: str) -> dict:
        """DeleteSecret arguments for the configured ``recovery_window_days``."""
        api_kwargs: dict = {"SecretId": path}
        window = self._config.recovery_window_days
        if window == 0:
            api_kwargs["ForceDeleteWithoutRecovery"] = True
        elif window is not None:
            api_kwargs["RecoveryWindowInDays"] = window
        return api_kwargs

    async def delete_async(self, path: str) -> None:
        """Delete a secret, applying ``AWSConfig.recovery_window_days``.

        Unset, AWS keeps the secret recoverable for its default 30 days. ``0`` deletes it at once, with no
        recovery, and 7-30 sets the window. Until the window ends a read, update or create of the name raises
        ``SecretPendingDeletionError``.
        """
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.delete_sync, path)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                await client.delete_secret(**self._delete_kwargs(path))
        except ClientError as e:
            raise self._map_client_error(e, "DeleteSecret", path)

    def delete_sync(self, path: str) -> None:
        """Delete a secret, applying ``AWSConfig.recovery_window_days`` (see ``delete_async``)."""
        client = self._get_sync_client()
        try:
            client.delete_secret(**self._delete_kwargs(path))
        except ClientError as e:
            raise self._map_client_error(e, "DeleteSecret", path)

    # --- Versioning ---

    @override
    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.get_version_sync, path, version, key)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.get_secret_value(SecretId=path, VersionId=version)
                return self._parse_response(response, path, key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                # AWS uses the same code for "secret missing" and "version missing".
                # Disambiguate via describe_secret on the failure path.
                try:
                    await self.get_metadata_async(path)
                except SecretNotFoundError:
                    raise SecretNotFoundError(path, self.name)
                raise SecretVersionNotFoundError(path, version, self.name)
            raise self._map_client_error(e, "GetSecretValue", path)

    @override
    def get_version_sync(self, path: str, version: str, key: str | None = None) -> SecretValue:
        client = self._get_sync_client()
        try:
            response = client.get_secret_value(SecretId=path, VersionId=version)
            return self._parse_response(response, path, key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                try:
                    self.get_metadata_sync(path)
                except SecretNotFoundError:
                    raise SecretNotFoundError(path, self.name)
                raise SecretVersionNotFoundError(path, version, self.name)
            raise self._map_client_error(e, "GetSecretValue", path)

    @override
    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self.list_versions_sync, path)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        items: list[dict] = []
        try:
            async with session.create_client(**kwargs) as client:
                next_token: str | None = None
                while True:
                    params: dict = {"SecretId": path, "IncludeDeprecated": False}
                    if next_token:
                        params["NextToken"] = next_token
                    response = await client.list_secret_version_ids(**params)
                    items.extend(response.get("Versions", []))
                    next_token = response.get("NextToken")
                    if not next_token:
                        break
        except ClientError as e:
            raise self._map_client_error(e, "ListSecretVersionIds", path)

        return self._build_version_list(items, path)

    @override
    def list_versions_sync(self, path: str) -> list[SecretMetadata]:
        client = self._get_sync_client()
        items: list[dict] = []
        try:
            next_token: str | None = None
            while True:
                params: dict = {"SecretId": path, "IncludeDeprecated": False}
                if next_token:
                    params["NextToken"] = next_token
                response = client.list_secret_version_ids(**params)
                items.extend(response.get("Versions", []))
                next_token = response.get("NextToken")
                if not next_token:
                    break
        except ClientError as e:
            raise self._map_client_error(e, "ListSecretVersionIds", path)

        return self._build_version_list(items, path)

    def _build_version_list(self, versions: list[dict], name: str) -> list[SecretMetadata]:
        """Convert list_secret_version_ids items into newest-first SecretMetadata list."""
        items = []
        for v in versions:
            items.append(
                SecretMetadata(
                    name=name,
                    created_at=v.get("CreatedDate"),
                    updated_at=v.get("LastAccessedDate") or v.get("CreatedDate"),
                    version=v.get("VersionId"),
                    version_count=None,
                    tags=None,
                    source=self.name,
                )
            )
        items.sort(key=lambda m: m.created_at or datetime.fromtimestamp(0, tz=UTC), reverse=True)
        return items

    # --- Native batch ---

    async def batch_get_async(self, paths: list[str]) -> dict[str, SecretValue]:
        """Native AWS batch fetch via batch_get_secret_value.

        Returns a dict mapping path -> SecretValue for successfully fetched
        secrets. Failures are logged and omitted from the result, matching
        SecretsManager.batch_get's non-fatal contract.
        """
        if not paths:
            return {}

        if not AIOBOTOCORE_AVAILABLE:
            return await run_blocking(self._batch_get_sync, paths)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.batch_get_secret_value(SecretIdList=paths)
        except ClientError as e:
            raise self._map_client_error(e, "BatchGetSecretValue", "<batch>")

        return self._collect_batch(response)

    def _batch_get_sync(self, paths: list[str]) -> dict[str, SecretValue]:
        """Sync sibling of batch_get_async, used as the fallback path."""
        if not paths:
            return {}
        client = self._get_sync_client()
        try:
            response = client.batch_get_secret_value(SecretIdList=paths)
        except ClientError as e:
            raise self._map_client_error(e, "BatchGetSecretValue", "<batch>")

        return self._collect_batch(response)

    def _collect_batch(self, response: dict) -> dict[str, SecretValue]:
        """Parse a BatchGetSecretValue response, logging and omitting each per-secret failure."""
        results: dict[str, SecretValue] = {}
        for entry in response.get("SecretValues", []) or []:
            name = entry.get("Name", "")
            results[name] = self._parse_response(entry, name, key=None)
        for err in response.get("Errors", []) or []:
            logger.warning(
                "AWS batch_get error",
                # codeql[py/clear-text-logging-sensitive-data] an Errors entry holds the name or ARN, never the value
                extra={
                    "secret_id": err.get("SecretId"),
                    "code": err.get("ErrorCode"),
                    # "message" is a reserved LogRecord attribute, so extra= rejects it.
                    "error_message": err.get("Message"),
                },
            )
        return results


__all__ = ["AIOBOTOCORE_AVAILABLE", "BOTO3_AVAILABLE", "AWSProvider"]
