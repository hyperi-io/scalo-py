"""Unit tests for secrets exceptions."""

import pytest

from hyperi_pylib.secrets.exceptions import (
    AuthenticationError,
    CacheError,
    ProviderError,
    ProviderNotAvailableError,
    ProviderNotConfiguredError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretPermissionError,
    SecretsError,
    SecretVersionNotFoundError,
    VersioningNotSupportedError,
)


class TestSecretsError:
    """Tests for SecretsError base class."""

    def test_create_base_error(self):
        """Test creating base SecretsError."""
        error = SecretsError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert isinstance(error, Exception)

    def test_inheritance(self):
        """Test that SecretsError inherits from Exception."""
        error = SecretsError("test")
        assert isinstance(error, Exception)


class TestSecretNotFoundError:
    """Tests for SecretNotFoundError."""

    def test_create_with_provider(self):
        """Test creating error with provider name."""
        error = SecretNotFoundError("my-secret", "file")

        assert error.name == "my-secret"
        assert error.provider == "file"
        assert "my-secret" in str(error)
        assert "file" in str(error)

    def test_inheritance(self):
        """Test inheritance chain."""
        error = SecretNotFoundError("test", "file")
        assert isinstance(error, SecretsError)
        assert isinstance(error, Exception)


class TestProviderError:
    """Tests for ProviderError."""

    def test_create_error(self):
        """Test creating provider error."""
        error = ProviderError("vault", "connection failed")

        assert error.provider == "vault"
        assert error.message == "connection failed"
        assert "vault" in str(error)
        assert "connection failed" in str(error)

    def test_inheritance(self):
        """Test inheritance chain."""
        error = ProviderError("aws", "timeout")
        assert isinstance(error, SecretsError)


class TestProviderNotConfiguredError:
    """Tests for ProviderNotConfiguredError."""

    def test_create_error(self):
        """Test creating not configured error."""
        error = ProviderNotConfiguredError("openbao")

        assert error.provider == "openbao"
        assert "openbao" in str(error)
        assert "not configured" in str(error).lower()

    def test_inheritance(self):
        """Test inheritance chain."""
        error = ProviderNotConfiguredError("aws")
        assert isinstance(error, SecretsError)


class TestProviderNotAvailableError:
    """Tests for ProviderNotAvailableError."""

    def test_create_error(self):
        """Test creating not available error."""
        error = ProviderNotAvailableError("openbao", "httpx", "pip install httpx")

        assert error.provider == "openbao"
        assert error.package == "httpx"
        assert error.install_hint == "pip install httpx"
        assert "httpx" in str(error)
        assert "pip install httpx" in str(error)

    def test_inheritance(self):
        """Test inheritance chain."""
        error = ProviderNotAvailableError("aws", "boto3", "pip install boto3")
        assert isinstance(error, SecretsError)


class TestCacheError:
    """Tests for CacheError."""

    def test_create_error(self):
        """Test creating cache error."""
        error = CacheError("write failed: disk full")

        assert "write failed: disk full" in str(error)

    def test_inheritance(self):
        """Test inheritance chain."""
        error = CacheError("test")
        assert isinstance(error, SecretsError)


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_create_error(self):
        """Test creating authentication error."""
        error = AuthenticationError("vault", "token expired")

        assert error.provider == "vault"
        assert "vault" in str(error)
        assert "token expired" in str(error)

    def test_inheritance(self):
        """Test inheritance chain."""
        error = AuthenticationError("aws", "invalid credentials")
        assert isinstance(error, ProviderError)
        assert isinstance(error, SecretsError)


class TestExceptionCatching:
    """Tests for exception catching hierarchy."""

    def test_catch_specific_first(self):
        """Test that specific exceptions can be caught."""
        try:
            raise SecretNotFoundError("test", "file")
        except SecretNotFoundError as e:
            assert e.name == "test"
        except SecretsError:
            pytest.fail("Should have caught SecretNotFoundError")

    def test_catch_base_class(self):
        """Test catching all secrets errors via base class."""
        errors = [
            SecretNotFoundError("test", "file"),
            ProviderError("vault", "fail"),
            ProviderNotConfiguredError("aws"),
            CacheError("disk error"),
            AuthenticationError("vault", "denied"),
            SecretAlreadyExistsError("test", "file"),
            SecretPermissionError("vault", "create", "secret/foo"),
            SecretVersionNotFoundError("test", "v2", "vault"),
            VersioningNotSupportedError("file"),
        ]

        for error in errors:
            try:
                raise error
            except SecretsError:
                pass  # All should be caught
            except Exception:
                pytest.fail(f"Expected {type(error).__name__} to be caught by SecretsError")


class TestSecretAlreadyExistsError:
    """Tests for SecretAlreadyExistsError."""

    def test_create_error(self):
        err = SecretAlreadyExistsError("api_key", "aws")
        assert err.name == "api_key"
        assert err.provider == "aws"
        assert "already exists" in str(err)
        assert "api_key" in str(err)
        assert "aws" in str(err)

    def test_inheritance(self):
        err = SecretAlreadyExistsError("x", "file")
        assert isinstance(err, SecretsError)
        assert isinstance(err, Exception)
        # Not a SecretNotFoundError -- distinct error class
        assert not isinstance(err, SecretNotFoundError)


class TestSecretPermissionError:
    """Tests for SecretPermissionError."""

    def test_create_error_without_hint(self):
        err = SecretPermissionError("vault", "create", "secret/foo")
        assert err.operation == "create"
        assert err.path == "secret/foo"
        assert err.hint is None
        assert err.provider == "vault"
        assert "permission denied" in str(err).lower()
        assert "create" in str(err)
        assert "secret/foo" in str(err)

    def test_create_error_with_hint(self):
        err = SecretPermissionError(
            "aws",
            "update",
            "prod/api_key",
            "IAM role needs secretsmanager:UpdateSecret",
        )
        assert err.hint == "IAM role needs secretsmanager:UpdateSecret"
        assert "IAM role" in str(err)

    def test_inheritance(self):
        err = SecretPermissionError("vault", "delete", "x")
        # Inherits from ProviderError (has provider attribute, not a 'not found')
        assert isinstance(err, ProviderError)
        assert isinstance(err, SecretsError)


class TestSecretVersionNotFoundError:
    """Tests for SecretVersionNotFoundError."""

    def test_create_error(self):
        err = SecretVersionNotFoundError("api_key", "v3", "vault")
        assert err.version == "v3"
        assert err.provider == "vault"
        # Embeds version in name for clarity
        assert "v3" in str(err)
        assert "api_key" in str(err)

    def test_inheritance(self):
        """Inherits from SecretNotFoundError so existing `except SecretNotFoundError`
        handlers continue to catch it."""
        err = SecretVersionNotFoundError("x", "v1", "vault")
        assert isinstance(err, SecretNotFoundError)
        assert isinstance(err, SecretsError)


class TestVersioningNotSupportedError:
    """Tests for VersioningNotSupportedError."""

    def test_create_error(self):
        err = VersioningNotSupportedError("file")
        assert err.provider == "file"
        assert "versioned access" in str(err).lower()

    def test_inheritance(self):
        err = VersioningNotSupportedError("ansible_vault")
        assert isinstance(err, ProviderError)
        assert isinstance(err, SecretsError)
