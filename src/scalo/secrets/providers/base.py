"""Abstract base class for secret providers, and the health log every provider shares."""

import functools
import hashlib
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from ..types import SecretFilter, SecretMetadata, SecretValue

if TYPE_CHECKING:
    from ...logger.scrub import Scrubber


@functools.cache
def _fault_scrubber() -> Scrubber:
    """Return the scrubber that masks provider error text, built on the first fault."""
    from ...logger.scrub import build_scrubber

    return build_scrubber()


def mask_fault(text: str) -> str:
    """Mask credentials in a provider's error text, or withhold the text when it cannot be masked."""
    try:
        return _fault_scrubber().scrub(text)
    except Exception:
        # Failing closed: a scrubber fault must neither leak the text nor break the health check.
        return "<message withheld, it could not be masked>"


async def mask_fault_off_loop(text: str) -> str:
    """Mask a provider's error text on a worker thread, because the first call builds the scrubber."""
    # Imported here so that ``import scalo.secrets`` does not load anyio.
    from ...concurrency import run_blocking

    return await run_blocking(mask_fault, text)


# scrypt cost: about 16 MiB and tens of milliseconds per credential, paid once per provider instance.
_SCRYPT_N = 2**14
_SCRYPT_R = 8


def credential_digest(value: str | bytes | None, salt: bytes) -> str:
    """Return a salted scrypt digest of a credential, or "" for none, to scope a cache entry to it.

    The digest reaches cache file names on disk, so a fast hash would let a low-entropy
    password be guessed offline. scrypt with the cache directory's own salt does not.

    Args:
        value: The credential.
        salt: The cache directory's salt (``DiskCache.salt``).

    Returns:
        32 hex digits, or "" when there is no credential.
    """
    if not value:
        return ""
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.scrypt(raw, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=1, dklen=16).hex()


def _describe(failure: str | BaseException) -> str:
    """Write a failure as ``ErrorType: message``, or pass on the reason a provider gave as text."""
    if isinstance(failure, str):
        return failure
    message = str(failure)
    return f"{type(failure).__name__}: {message}" if message else type(failure).__name__


class HealthLog:
    """Logs a provider's health by transition, so a probe that runs every few seconds writes one line per outage.

    The first failed check logs a warning with the masked reason. Checks that keep failing log nothing, and the
    first one to pass logs one INFO line. One log serves a provider's sync and async checks alike.
    """

    def __init__(self, log: logging.Logger, provider: str) -> None:
        """Start a log for ``provider`` that writes to ``log``, the provider module's own logger."""
        self._log = log
        self._provider = provider
        self._healthy: bool | None = None
        self._lock = threading.Lock()

    def _enter(self, healthy: bool) -> tuple[bool, bool]:
        """Store the outcome of a check, and return whether it opened an outage and whether it closed one."""
        with self._lock:
            before, self._healthy = self._healthy, healthy
        return (not healthy and before is not False), (healthy and before is False)

    def _withdraw(self) -> None:
        """Forget an outage whose warning was never written, so the next failed check announces it."""
        with self._lock:
            self._healthy = None

    def _went_down(self, reason: str) -> None:
        # Every caller passes mask_fault output, so `reason` is scrubbed or withheld text.
        self._log.warning("Health check of provider %s failed: %s", self._provider, reason)

    def _recovered(self) -> None:
        self._log.info("Health check of provider %s passes again", self._provider)

    def record(self, failure: str | BaseException | None) -> bool:
        """Log what a finished check changed, and return whether the provider is healthy (``failure`` is None)."""
        went_down, recovered = self._enter(failure is None)
        if went_down and failure is not None:
            self._went_down(mask_fault(_describe(failure)))
        elif recovered:
            self._recovered()
        return failure is None

    async def arecord(self, failure: str | BaseException | None) -> bool:
        """Do what ``record`` does, masking the reason on a worker thread so the event loop never stalls."""
        went_down, recovered = self._enter(failure is None)
        if went_down and failure is not None:
            try:
                reason = await mask_fault_off_loop(_describe(failure))
            except BaseException:
                # A check cancelled while masking has written nothing, so its outage is still to be announced.
                self._withdraw()
                raise
            self._went_down(reason)
        elif recovered:
            self._recovered()
        return failure is None

    def run(self, probe: Callable[[], str | None]) -> bool:
        """Run ``probe`` and record it: an exception, or a reason it returns, is a failure, and None is a pass."""
        failure: str | BaseException | None
        try:
            failure = probe()
        except Exception as fault:
            failure = fault
        return self.record(failure)

    async def arun(self, probe: Callable[[], Awaitable[str | None]]) -> bool:
        """Run the async ``probe`` and record it as ``run`` does."""
        failure: str | BaseException | None
        try:
            failure = await probe()
        except Exception as fault:
            failure = fault
        return await self.arecord(failure)


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

    def cache_identity(self, salt: bytes) -> tuple[str, ...]:  # noqa: V107 -- overrides digest credentials with it
        """Name the backend and principal this provider reads as, to key the shared disk cache.

        Two providers that can return different values for one path must differ here.
        A credential appears only as :func:`credential_digest` with ``salt``. The manager
        calls this once per provider.

        Args:
            salt: The cache directory's salt.

        Returns:
            The identity, the provider's name first.
        """
        return (self.name,)

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


__all__ = ["HealthLog", "SecretProvider", "VersionedProvider", "mask_fault", "mask_fault_off_loop"]
