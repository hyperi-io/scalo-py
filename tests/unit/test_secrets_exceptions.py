"""Unit tests for secrets exceptions."""

import pytest

from hyperi_pylib.secrets.exceptions import (
    AuthenticationError,
    CacheError,
    ProviderError,
    ProviderNotAvailableError,
    ProviderNotConfiguredError,
    SecretNotFoundError,
    SecretsError,
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
        ]

        for error in errors:
            try:
                raise error
            except SecretsError:
                pass  # All should be caught
            except Exception:
                pytest.fail(f"Expected {type(error).__name__} to be caught by SecretsError")
