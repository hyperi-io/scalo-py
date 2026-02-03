"""Abstract base class for secret providers."""

from abc import ABC, abstractmethod

from ..types import SecretValue


class SecretProvider(ABC):
    """Abstract base class for secret providers.

    All providers must implement both sync and async methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and error messages."""
        ...

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


__all__ = ["SecretProvider"]
