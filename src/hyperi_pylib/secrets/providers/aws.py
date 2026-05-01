"""AWS Secrets Manager provider with aiobotocore async support."""

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
from ..types import AWSConfig, SecretFilter, SecretMetadata, SecretValue
from .base import VersionedProvider

logger = logging.getLogger(__name__)

# Optional boto3/aiobotocore support
try:
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment,misc]

try:
    from aiobotocore.session import get_session as get_aiobotocore_session

    AIOBOTOCORE_AVAILABLE = True
except ImportError:
    AIOBOTOCORE_AVAILABLE = False
    get_aiobotocore_session = None  # type: ignore[assignment]


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

            raise ProviderNotAvailableError(
                "aws", "boto3", "pip install boto3 or pip install hyperi-pylib[secrets-aws]"
            )

        self._config = config
        self._sync_client = None
        self._session = None

    @property
    def name(self) -> str:
        """Provider name."""
        return "aws"

    def _get_client_kwargs(self) -> dict:
        """Get kwargs for boto3/aiobotocore client creation."""
        kwargs: dict = {
            "service_name": "secretsmanager",
            "region_name": self._config.region,
        }

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
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.get_sync, path, key)

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
                raise ProviderError(self.name, f"access denied: {path}")
            elif error_code == "DecryptionFailure":
                raise ProviderError(self.name, f"decryption failed for {path}")
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
                raise ProviderError(self.name, f"access denied: {path}")
            elif error_code == "DecryptionFailure":
                raise ProviderError(self.name, f"decryption failed for {path}")
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

    async def health_check_async(self) -> bool:
        """Check if AWS Secrets Manager is reachable."""
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.health_check_sync)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                # List secrets with max 1 result to test connectivity
                await client.list_secrets(MaxResults=1)
                return True
        except Exception:
            return False

    def health_check_sync(self) -> bool:
        """Check if AWS Secrets Manager is reachable (sync)."""
        try:
            client = self._get_sync_client()
            client.list_secrets(MaxResults=1)
            return True
        except Exception:
            return False

    # --- Helpers for Tier 1+2 ---

    @staticmethod
    def _encode_value(value: bytes) -> dict:
        """Pick SecretString vs SecretBinary based on utf-8 validity."""
        try:
            return {"SecretString": value.decode("utf-8")}
        except UnicodeDecodeError:
            return {"SecretBinary": value}

    def _aws_hint(self, operation: str) -> str:
        """IAM permission hint per HyperI spec."""
        return f"check IAM policy for secretsmanager:{operation} permission"

    def _map_client_error(self, error: "ClientError", operation: str, path: str) -> Exception:
        """Map a botocore ClientError to the appropriate domain exception."""
        code = error.response.get("Error", {}).get("Code", "")
        if code == "ResourceNotFoundException":
            return SecretNotFoundError(path, self.name)
        if code == "ResourceExistsException":
            return SecretAlreadyExistsError(path, self.name)
        if code == "AccessDeniedException":
            return SecretPermissionError(self.name, operation, path, self._aws_hint(operation))
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
        """Encode HyperI tag dict to AWS Tags list shape."""
        if not tags:
            return None
        return [{"Key": k, "Value": v} for k, v in tags.items()]

    # --- List ---

    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret names. ``filter.prefix`` filters server-side; ``filter.tags`` use AWS
        tag-key/tag-value filters; ``filter.pattern`` is a client-side fnmatch.
        """
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.list_sync, filter)

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

    async def get_metadata_async(self, path: str) -> SecretMetadata:
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.get_metadata_sync, path)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.describe_secret(SecretId=path)
                return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "describe", path)

    def get_metadata_sync(self, path: str) -> SecretMetadata:
        client = self._get_sync_client()
        try:
            response = client.describe_secret(SecretId=path)
            return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "describe", path)

    # --- Create ---

    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.create_sync, path, value, tags)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()
        api_kwargs: dict = {"Name": path, **self._encode_value(value)}
        aws_tags = self._tags_for_aws(tags)
        if aws_tags:
            api_kwargs["Tags"] = aws_tags

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.create_secret(**api_kwargs)
                meta = self._to_metadata(response, fallback_name=path)
                if tags and not meta.tags:
                    meta.tags = tags  # AWS create response doesn't echo Tags
                return meta
        except ClientError as e:
            raise self._map_client_error(e, "CreateSecret", path)

    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        client = self._get_sync_client()
        api_kwargs: dict = {"Name": path, **self._encode_value(value)}
        aws_tags = self._tags_for_aws(tags)
        if aws_tags:
            api_kwargs["Tags"] = aws_tags

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
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.update_sync, path, value)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                response = await client.update_secret(SecretId=path, **self._encode_value(value))
                return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "UpdateSecret", path)

    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        client = self._get_sync_client()
        try:
            response = client.update_secret(SecretId=path, **self._encode_value(value))
            return self._to_metadata(response, fallback_name=path)
        except ClientError as e:
            raise self._map_client_error(e, "UpdateSecret", path)

    # --- Delete ---

    async def delete_async(self, path: str) -> None:
        """Delete a secret (soft-delete; AWS keeps it recoverable for 7-30 days by default).

        AWS' default 30-day recovery window applies. Callers that need an immediate
        purge should use ``delete_secret(ForceDeleteWithoutRecovery=True)`` directly
        on the underlying client.
        """
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.delete_sync, path)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        try:
            async with session.create_client(**kwargs) as client:
                await client.delete_secret(SecretId=path)
        except ClientError as e:
            raise self._map_client_error(e, "DeleteSecret", path)

    def delete_sync(self, path: str) -> None:
        client = self._get_sync_client()
        try:
            client.delete_secret(SecretId=path)
        except ClientError as e:
            raise self._map_client_error(e, "DeleteSecret", path)

    # --- Versioning ---

    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.get_version_sync, path, version, key)

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

    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        if not AIOBOTOCORE_AVAILABLE:
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self.list_versions_sync, path)

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
            import asyncio

            return await asyncio.get_event_loop().run_in_executor(None, self._batch_get_sync, paths)

        session = get_aiobotocore_session()
        kwargs = self._get_client_kwargs()

        results: dict[str, SecretValue] = {}
        try:
            async with session.create_client(**kwargs) as client:
                response = await client.batch_get_secret_value(SecretIdList=paths)
        except ClientError as e:
            raise self._map_client_error(e, "BatchGetSecretValue", "<batch>")

        for entry in response.get("SecretValues", []) or []:
            name = entry.get("Name", "")
            results[name] = self._parse_response(entry, name, key=None)

        for err in response.get("Errors", []) or []:
            logger.warning(
                "AWS batch_get error",
                extra={
                    "secret_id": err.get("SecretId"),
                    "code": err.get("ErrorCode"),
                    "message": err.get("ErrorMessage"),
                },
            )

        return results

    def _batch_get_sync(self, paths: list[str]) -> dict[str, SecretValue]:
        """Sync sibling of batch_get_async, used as the fallback path."""
        if not paths:
            return {}
        client = self._get_sync_client()
        try:
            response = client.batch_get_secret_value(SecretIdList=paths)
        except ClientError as e:
            raise self._map_client_error(e, "BatchGetSecretValue", "<batch>")

        results: dict[str, SecretValue] = {}
        for entry in response.get("SecretValues", []) or []:
            name = entry.get("Name", "")
            results[name] = self._parse_response(entry, name, key=None)
        for err in response.get("Errors", []) or []:
            logger.warning(
                "AWS batch_get error",
                extra={
                    "secret_id": err.get("SecretId"),
                    "code": err.get("ErrorCode"),
                    "message": err.get("ErrorMessage"),
                },
            )
        return results


__all__ = ["AIOBOTOCORE_AVAILABLE", "BOTO3_AVAILABLE", "AWSProvider"]
