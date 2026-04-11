"""Abstract base class for secret providers."""

from abc import ABC, abstractmethod

from ..types import SecretFilter, SecretMetadata, SecretValue


class SecretProvider(ABC):
    """Abstract base class for secret providers.

    All providers must implement both sync and async methods for:
    - get: fetch a single secret
    - list: enumerate secrets matching a filter
    - get_metadata: fetch metadata without the secret value
    - create: create a new secret
    - update: update an existing secret's value
    - delete: remove a secret
    - health_check: verify provider connectivity
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and error messages."""
        ...

    # --- Read ---

    @abstractmethod
    async def get_async(self, path: str, key: str | None = None) -> SecretValue:
        """Fetch secret asynchronously.

        Args:
            path: Secret path (file path, Vault path, or AWS secret ID).
            key: Optional key to extract from JSON secret.

        Returns:
            SecretValue with raw data and metadata.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Provider communication failed.
        """
        ...

    @abstractmethod
    def get_sync(self, path: str, key: str | None = None) -> SecretValue:
        """Fetch secret synchronously.

        Same semantics as get_async().
        """
        ...

    # --- List ---

    @abstractmethod
    async def list_async(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret names/paths matching filter.

        Args:
            filter: Optional filter (prefix, tags, pattern).
                prefix: server-side on most providers, primary efficient filter.
                tags: server-side on cloud providers, ignored by file-based.
                pattern: client-side fnmatch post-filter on results.

        Returns:
            List of secret names/paths.
        """
        ...

    @abstractmethod
    def list_sync(self, filter: SecretFilter | None = None) -> list[str]:
        """List secret names/paths matching filter (sync)."""
        ...

    # --- Metadata ---

    @abstractmethod
    async def get_metadata_async(self, path: str) -> SecretMetadata:
        """Get secret metadata without fetching the value.

        Args:
            path: Secret path.

        Returns:
            SecretMetadata with available fields populated.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Provider communication failed.
        """
        ...

    @abstractmethod
    def get_metadata_sync(self, path: str) -> SecretMetadata:
        """Get secret metadata without fetching the value (sync)."""
        ...

    # --- Create ---

    @abstractmethod
    async def create_async(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new secret.

        Args:
            path: Secret path/name.
            value: Secret value as bytes.
            tags: Optional tags/labels. Ignored by file-based providers.

        Returns:
            SecretMetadata of the created secret.

        Raises:
            SecretAlreadyExistsError: Secret already exists.
            SecretPermissionError: Caller lacks write permission.
            ProviderError: Write failed.
        """
        ...

    @abstractmethod
    def create_sync(self, path: str, value: bytes, tags: dict[str, str] | None = None) -> SecretMetadata:
        """Create a new secret (sync)."""
        ...

    # --- Update ---

    @abstractmethod
    async def update_async(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing secret's value.

        Args:
            path: Secret path/name.
            value: New secret value as bytes.

        Returns:
            SecretMetadata of the updated secret (new version).

        Raises:
            SecretNotFoundError: Secret does not exist.
            SecretPermissionError: Caller lacks write permission.
            ProviderError: Write failed.
        """
        ...

    @abstractmethod
    def update_sync(self, path: str, value: bytes) -> SecretMetadata:
        """Update an existing secret's value (sync)."""
        ...

    # --- Delete ---

    @abstractmethod
    async def delete_async(self, path: str) -> None:
        """Delete a secret.

        Args:
            path: Secret path/name.

        Raises:
            SecretNotFoundError: Secret does not exist.
            SecretPermissionError: Caller lacks write permission.
            ProviderError: Delete failed.
        """
        ...

    @abstractmethod
    def delete_sync(self, path: str) -> None:
        """Delete a secret (sync)."""
        ...

    # --- Health ---

    @abstractmethod
    async def health_check_async(self) -> bool:
        """Check if provider is healthy."""
        ...

    @abstractmethod
    def health_check_sync(self) -> bool:
        """Check if provider is healthy synchronously."""
        ...

    async def close(self) -> None:  # noqa: B027
        """Release provider resources. Default: no-op."""


class VersionedProvider(SecretProvider):
    """Extended base class for providers that support versioned secret access.

    Providers: OpenBao, AWS, GCP, Azure.
    Not implemented by: File, AnsibleVault.

    Use isinstance(provider, VersionedProvider) to check capability before
    calling version-specific methods.
    """

    @abstractmethod
    async def get_version_async(self, path: str, version: str, key: str | None = None) -> SecretValue:
        """Fetch a specific version of a secret.

        Args:
            path: Secret path.
            version: Version identifier (provider-specific format).
            key: Optional key to extract from structured secret.

        Returns:
            SecretValue for the requested version.

        Raises:
            SecretVersionNotFoundError: Version does not exist.
            SecretNotFoundError: Secret does not exist.
            ProviderError: Provider communication failed.
        """
        ...

    @abstractmethod
    def get_version_sync(self, path: str, version: str, key: str | None = None) -> SecretValue:
        """Fetch a specific version (sync)."""
        ...

    @abstractmethod
    async def list_versions_async(self, path: str) -> list[SecretMetadata]:
        """List all versions of a secret, newest first.

        Args:
            path: Secret path.

        Returns:
            List of SecretMetadata, one per version.

        Raises:
            SecretNotFoundError: Secret does not exist.
            ProviderError: Provider communication failed.
        """
        ...

    @abstractmethod
    def list_versions_sync(self, path: str) -> list[SecretMetadata]:
        """List all versions (sync)."""
        ...


__all__ = ["SecretProvider", "VersionedProvider"]
