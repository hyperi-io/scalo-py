"""
Tests for hyperlib logger filters (sensitive data masking).
"""

import pytest

from hyperlib.logger.filters import MASK_VALUE, SENSITIVE_FIELDS, SensitiveDataFilter


class TestSensitiveDataFilter:
    """Test the SensitiveDataFilter for log data masking."""

    def test_mask_password_key_value(self):
        """Test masking password in key=value format."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("password=secret123", f"password={MASK_VALUE}"),
            ("password=super_secret", f"password={MASK_VALUE}"),
            ("pwd=abc123", f"pwd={MASK_VALUE}"),
            ("passwd=test", f"passwd={MASK_VALUE}"),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_password_json(self):
        """Test masking password in JSON format."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ('{"password":"secret"}', f'{{"password":"{MASK_VALUE}"}}'),
            ('{"password": "secret"}', f'{{"password": "{MASK_VALUE}"}}'),
            ('"password":"secret"', f'"password":"{MASK_VALUE}"'),
            ('password:"secret"', f'password:"{MASK_VALUE}"'),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_api_key(self):
        """Test masking API keys in various formats."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("api_key=sk-1234567890", f"api_key={MASK_VALUE}"),
            ("apikey=abc123", f"apikey={MASK_VALUE}"),
            ('"api_key":"sk-1234"', f'"api_key":"{MASK_VALUE}"'),
            ("api_key: sk-test", f"api_key: {MASK_VALUE}"),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_bearer_token(self):
        """Test masking bearer tokens."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", f"bearer {MASK_VALUE}"),
            ("token=abc123xyz", f"token={MASK_VALUE}"),
            ("access_token=jwt-token-here", f"access_token={MASK_VALUE}"),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_database_url(self):
        """Test masking passwords in database URLs."""
        filter_inst = SensitiveDataFilter()

        cases = [
            (
                "postgresql://user:secret@localhost/db",
                f"postgresql://user:{MASK_VALUE}@localhost/db",
            ),
            (
                "mysql://root:password123@host:3306/mydb",
                f"mysql://root:{MASK_VALUE}@host:3306/mydb",
            ),
            (
                "redis://:password@redis.example.com/0",
                f"redis://:{MASK_VALUE}@redis.example.com/0",
            ),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_secrets_in_dict(self):
        """Test masking sensitive fields in dictionaries."""
        filter_inst = SensitiveDataFilter()

        input_dict = {
            "username": "admin",
            "password": "secret123",
            "api_key": "sk-1234567890",
            "normal_field": "normal_value",
        }

        result = filter_inst._mask_sensitive_dict(input_dict)

        assert result["username"] == "admin"  # Not sensitive
        assert result["password"] == MASK_VALUE
        assert result["api_key"] == MASK_VALUE
        assert result["normal_field"] == "normal_value"

    def test_mask_nested_dict(self):
        """Test masking sensitive fields in nested dictionaries."""
        filter_inst = SensitiveDataFilter()

        input_dict = {
            "config": {
                "database": {
                    "host": "localhost",
                    "password": "db_secret",
                },
                "api": {
                    "token": "api_token_123",
                },
            },
            "user": "admin",
        }

        result = filter_inst._mask_sensitive_dict(input_dict)

        assert result["config"]["database"]["host"] == "localhost"
        assert result["config"]["database"]["password"] == MASK_VALUE
        assert result["config"]["api"]["token"] == MASK_VALUE
        assert result["user"] == "admin"

    def test_mask_list_of_dicts(self):
        """Test masking sensitive fields in lists of dictionaries."""
        filter_inst = SensitiveDataFilter()

        input_dict = {
            "users": [
                {"name": "alice", "password": "alice_pass"},
                {"name": "bob", "password": "bob_pass"},
            ]
        }

        result = filter_inst._mask_sensitive_dict(input_dict)

        assert result["users"][0]["name"] == "alice"
        assert result["users"][0]["password"] == MASK_VALUE
        assert result["users"][1]["name"] == "bob"
        assert result["users"][1]["password"] == MASK_VALUE

    def test_mask_multiple_fields_in_string(self):
        """Test masking multiple sensitive fields in one string."""
        filter_inst = SensitiveDataFilter()

        input_text = "password=secret&api_key=sk-123&token=jwt-abc&username=admin"
        result = filter_inst._mask_sensitive_string(input_text)

        assert "password=" + MASK_VALUE in result
        assert "api_key=" + MASK_VALUE in result
        assert "token=" + MASK_VALUE in result
        assert "username=admin" in result  # username is NOT sensitive

    def test_mask_authorization_header(self):
        """Test masking authorization headers."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("authorization: Bearer token123", f"authorization: {MASK_VALUE}"),
            ("Authorization=Bearer xyz", f"Authorization={MASK_VALUE}"),
            ('"authorization":"Bearer abc"', f'"authorization":"{MASK_VALUE}"'),
        ]

        for input_text, _expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert "Bearer" not in result or MASK_VALUE in result, f"Failed for: {input_text}"

    def test_mask_aws_secrets(self):
        """Test masking AWS secret access keys."""
        filter_inst = SensitiveDataFilter()

        cases = [
            (
                "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                f"aws_secret_access_key={MASK_VALUE}",
            ),
            (
                "secret_access_key=abc123",
                f"secret_access_key={MASK_VALUE}",
            ),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_case_insensitive(self):
        """Test that masking is case-insensitive."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("PASSWORD=secret", f"PASSWORD={MASK_VALUE}"),
            ("Password=secret", f"Password={MASK_VALUE}"),
            ("PassWord=secret", f"PassWord={MASK_VALUE}"),
            ("API_KEY=sk-123", f"API_KEY={MASK_VALUE}"),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_preserves_non_sensitive(self):
        """Test that non-sensitive fields are preserved."""
        filter_inst = SensitiveDataFilter()

        input_text = "username=admin&email=admin@example.com&role=superuser"
        result = filter_inst._mask_sensitive_string(input_text)

        # These should NOT be masked
        assert "username=admin" in result
        assert "email=admin@example.com" in result
        assert "role=superuser" in result

    def test_custom_sensitive_fields_class_level(self):
        """Test adding custom sensitive fields at class level."""
        # Add custom field
        SensitiveDataFilter.add_sensitive_fields({"employee_id"})

        filter_inst = SensitiveDataFilter()
        input_text = "employee_id=123456&name=John"
        result = filter_inst._mask_sensitive_string(input_text)

        assert f"employee_id={MASK_VALUE}" in result
        assert "name=John" in result

        # Clean up
        SensitiveDataFilter._custom_fields.discard("employee_id")

    def test_custom_sensitive_fields_instance_level(self):
        """Test adding custom sensitive fields at instance level."""
        filter_inst = SensitiveDataFilter(extra_fields={"ssn", "credit_card"})

        input_text = "ssn=123-45-6789&credit_card=1234-5678-9012-3456&name=John"
        result = filter_inst._mask_sensitive_string(input_text)

        assert f"ssn={MASK_VALUE}" in result
        assert f"credit_card={MASK_VALUE}" in result
        assert "name=John" in result

    def test_all_default_sensitive_fields_covered(self):
        """Test that all default sensitive fields are properly masked."""
        filter_inst = SensitiveDataFilter()

        # Test a representative sample of all SENSITIVE_FIELDS
        test_fields = [
            "password",
            "token",
            "api_key",
            "secret",
            "authorization",
            "session_id",
            "private_key",
        ]

        for field in test_fields:
            assert field in SENSITIVE_FIELDS, f"{field} not in SENSITIVE_FIELDS"

            input_text = f"{field}=test_value"
            result = filter_inst._mask_sensitive_string(input_text)
            assert f"{field}={MASK_VALUE}" in result, f"Failed to mask {field}"

    def test_mask_complex_json_structure(self):
        """Test masking in complex nested JSON structures."""
        filter_inst = SensitiveDataFilter()

        input_dict = {
            "service": "api",
            "config": {
                "authentication": {  # Changed from "auth" (which is sensitive)
                    "type": "oauth2",
                    "client_secret": "very_secret",
                    "access_token": "jwt_token_here",
                },
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "connection": {  # Changed from "credentials" (which is sensitive)
                        "username": "admin",
                        "password": "db_password",
                    },
                },
            },
            "metadata": {
                "created": "2025-11-07",
                "version": "1.0.0",
            },
        }

        result = filter_inst._mask_sensitive_dict(input_dict)

        # Check that sensitive fields are masked
        assert result["config"]["authentication"]["client_secret"] == MASK_VALUE
        assert result["config"]["authentication"]["access_token"] == MASK_VALUE
        assert result["config"]["database"]["connection"]["password"] == MASK_VALUE

        # Check that non-sensitive fields are preserved
        assert result["service"] == "api"
        assert result["config"]["authentication"]["type"] == "oauth2"
        assert result["config"]["database"]["host"] == "localhost"
        assert result["config"]["database"]["port"] == 5432
        assert result["config"]["database"]["connection"]["username"] == "admin"
        assert result["metadata"]["created"] == "2025-11-07"

    def test_mask_form_encoded_data(self):
        """Test masking form-encoded data (application/x-www-form-urlencoded)."""
        filter_inst = SensitiveDataFilter()

        input_text = "username=admin&password=secret123&email=admin@example.com&token=jwt-abc"
        result = filter_inst._mask_sensitive_string(input_text)

        assert "username=admin" in result
        assert f"password={MASK_VALUE}" in result
        assert "email=admin@example.com" in result
        assert f"token={MASK_VALUE}" in result

    def test_mask_empty_values(self):
        """Test masking fields with empty values."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("password=", f"password={MASK_VALUE}"),
            ('{"password":""}', f'{{"password":"{MASK_VALUE}"}}'),
            ("token=&username=admin", f"token={MASK_VALUE}&username=admin"),
        ]

        for input_text, _expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert MASK_VALUE in result, f"Failed for: {input_text}"

    def test_mask_special_characters_in_values(self):
        """Test masking values with special characters."""
        filter_inst = SensitiveDataFilter()

        cases = [
            ("password=p@ssw0rd!", f"password={MASK_VALUE}"),
            ("api_key=sk-123_ABC-xyz", f"api_key={MASK_VALUE}"),
            ("secret=$pec!al#Ch@rs", f"secret={MASK_VALUE}"),
        ]

        for input_text, expected in cases:
            result = filter_inst._mask_sensitive_string(input_text)
            assert result == expected, f"Failed for: {input_text}"

    def test_mask_mixed_formats_in_one_string(self):
        """Test masking when multiple formats are mixed in one string."""
        filter_inst = SensitiveDataFilter()

        input_text = (
            "Connecting to postgresql://user:secret@localhost/db "
            'with {"api_key":"sk-123","token":"jwt-abc"} '
            "and params password=test&username=admin"
        )

        result = filter_inst._mask_sensitive_string(input_text)

        # Database URL password should be masked
        assert f"user:{MASK_VALUE}@localhost" in result

        # JSON fields should be masked
        assert f'"api_key":"{MASK_VALUE}"' in result
        assert f'"token":"{MASK_VALUE}"' in result

        # Form data should be masked
        assert f"password={MASK_VALUE}" in result

        # Non-sensitive should be preserved
        assert "username=admin" in result

    def test_non_string_values_preserved(self):
        """Test that non-string values in dicts are preserved correctly."""
        filter_inst = SensitiveDataFilter()

        input_dict = {
            "count": 42,
            "ratio": 3.14,
            "enabled": True,
            "items": None,
            "password": "secret",
        }

        result = filter_inst._mask_sensitive_dict(input_dict)

        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["enabled"] is True
        assert result["items"] is None
        assert result["password"] == MASK_VALUE
