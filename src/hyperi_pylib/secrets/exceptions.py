"""Exception hierarchy for hyperi-pylib secrets module."""


class SecretsError(Exception):
    """Base exception for all secrets-related errors."""


class SecretNotFoundError(SecretsError):
    """Secret does not exist at the specified path."""

    def __init__(self, name: str, provider: str) -> None:
        self.name = name
        self.provider = provider
        super().__init__(f"secret '{name}' not found in provider '{provider}'")


class ProviderError(SecretsError):
    """Provider communication or operation failed."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        self.message = message
        super().__init__(f"provider '{provider}' error: {message}")


class ProviderNotConfiguredError(SecretsError):
    """Requested provider is not configured."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"provider '{provider}' not configured")


class ProviderNotAvailableError(SecretsError):
    """Provider dependencies not installed."""

    def __init__(self, provider: str, package: str, install_hint: str) -> None:
        self.provider = provider
        self.package = package
        self.install_hint = install_hint
        super().__init__(f"provider '{provider}' requires '{package}': {install_hint}")


class CacheError(SecretsError):
    """Cache operation failed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"cache error: {reason}")


class AuthenticationError(ProviderError):
    """Provider authentication failed."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(provider, message)


__all__ = [
    "SecretsError",
    "SecretNotFoundError",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderNotAvailableError",
    "CacheError",
    "AuthenticationError",
]
