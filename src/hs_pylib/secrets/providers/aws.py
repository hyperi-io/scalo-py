"""AWS Secrets Manager provider with aiobotocore async support."""

import json
import logging
from datetime import UTC, datetime

from ..exceptions import ProviderError, SecretNotFoundError
from ..types import AWSConfig, SecretValue
from .base import SecretProvider

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


class AWSProvider(SecretProvider):
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

            raise ProviderNotAvailableError("aws", "boto3", "pip install boto3 or pip install hs-pylib[secrets-aws]")

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


__all__ = ["AWSProvider", "BOTO3_AVAILABLE", "AIOBOTOCORE_AVAILABLE"]
