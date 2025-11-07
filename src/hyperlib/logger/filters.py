"""
Logging filters for hyperlib logger.

This module provides logging filters for common use cases like masking
sensitive data in log records.
"""

import logging
import re
from typing import Any, Dict, Set, Tuple


# Sensitive fields that should be masked in logs
SENSITIVE_FIELDS: Set[str] = {
    # Passwords
    "password",
    "passwd",
    "pwd",
    # Tokens
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "session_token",
    "api_token",
    "bearer",
    # API Keys
    "api_key",
    "apikey",
    "api_secret",
    # Secrets
    "secret",
    "client_secret",
    "secret_key",
    "private_key",
    "secret_access_key",
    "aws_secret_access_key",
    # Auth
    "authorization",
    "auth",
    # Session
    "session_id",
    "sessionid",
    # Certificates
    "certificate",
    "cert",
    "ssl_cert",
    # Credentials
    "credentials",
    "creds",
    # Database
    "db_password",
    "database_password",
    "connection_string",
}

MASK_VALUE = "***REDACTED***"


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that masks sensitive data in log records.

    This filter intercepts all log records and masks sensitive information
    like passwords, tokens, API keys, secrets, etc. to prevent them from
    being written to logs.

    **Supported formats:**
    - JSON: `{"password": "secret"}` → `{"password": "***REDACTED***"}`
    - Form data: `password=secret&token=abc` → `password=***REDACTED***&token=***REDACTED***`
    - Key-value: `password: secret` → `password: ***REDACTED***`
    - Database URLs: `postgres://user:pass@host` → `postgres://user:***REDACTED***@host`

    **Usage:**

    The filter is automatically applied to all handlers when you use hyperlib's
    default logger configuration. No manual setup required.

    **Customization:**

    You can add custom sensitive fields:

    ```python
    from hyperlib.logger.filters import SensitiveDataFilter

    # Add custom fields
    SensitiveDataFilter.add_sensitive_fields({"employee_id", "ssn"})

    # Or create a custom instance
    custom_filter = SensitiveDataFilter(
        extra_fields={"custom_secret", "internal_token"}
    )
    logger.addHandler(handler)
    handler.addFilter(custom_filter)
    ```

    **Disable masking (NOT recommended):**

    Set environment variable:
    ```bash
    export HYPERLIB_LOGGING__MASK_SENSITIVE_DATA=false
    ```
    """

    # Class-level set for global custom fields
    _custom_fields: Set[str] = set()

    def __init__(self, extra_fields: Set[str] | None = None):
        """
        Initialize the sensitive data filter.

        Args:
            extra_fields: Additional fields to mask (optional)
        """
        super().__init__()
        self._instance_fields = extra_fields or set()

    @classmethod
    def add_sensitive_fields(cls, fields: Set[str]) -> None:
        """
        Add custom sensitive fields to mask globally.

        Args:
            fields: Set of field names to mask (case-insensitive)
        """
        cls._custom_fields.update(f.lower() for f in fields)

    def _get_all_sensitive_fields(self) -> Set[str]:
        """Get combined set of all sensitive fields."""
        return SENSITIVE_FIELDS | self._custom_fields | self._instance_fields

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record to mask sensitive data.

        Args:
            record: The log record to filter

        Returns:
            True to allow the record to be logged
        """
        # Mask the main message
        if isinstance(record.msg, str):
            record.msg = self._mask_sensitive_string(record.msg)
        elif isinstance(record.msg, dict):
            record.msg = self._mask_sensitive_dict(record.msg)

        # Mask any arguments
        if record.args:
            if isinstance(record.args, dict):
                record.args = self._mask_sensitive_dict(record.args)
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(
                    self._mask_value(arg) for arg in record.args
                )

        return True

    def _mask_value(self, value: Any) -> Any:
        """Mask a single value based on its type."""
        if isinstance(value, str):
            return self._mask_sensitive_string(value)
        elif isinstance(value, dict):
            return self._mask_sensitive_dict(value)
        elif isinstance(value, (list, tuple)):
            return type(value)(self._mask_value(item) for item in value)
        return value

    def _mask_sensitive_string(self, text: str) -> str:
        """
        Mask sensitive fields in a string using regex patterns.

        Handles multiple formats:
        - URL parameters: `field=value&`
        - JSON: `"field":"value"` or `field:"value"`
        - Key-value pairs: `field: value` or `field=value`
        - Database URLs: `://user:password@host`

        Args:
            text: String to mask

        Returns:
            String with sensitive fields masked
        """
        if not isinstance(text, str):
            return text

        masked = text
        fields = self._get_all_sensitive_fields()

        # Database connection strings: ://user:password@host or ://:password@host
        # Pattern matches: postgres://user:secret@localhost and redis://:password@host
        # Must run before field-specific patterns to avoid double-masking
        masked = re.sub(
            r"(://[^:/@]*:)([^@]+)(@)",
            rf"\1{MASK_VALUE}\3",
            masked,
        )

        # Bearer tokens (space-separated): "bearer <token>"
        # Pattern matches: "bearer eyJhbGci..." or "Bearer eyJhbGci..."
        masked = re.sub(
            r"\bbearer\s+([^\s]+)",
            rf"bearer {MASK_VALUE}",
            masked,
            flags=re.IGNORECASE,
        )

        for field in fields:
            # Field names with underscores/hyphens don't need escaping
            # They should be matched literally

            # Pattern 1: JSON with quotes ("field":"value")
            pattern1 = rf'("{field}"\s*:\s*)"([^"]*)"'
            masked = re.sub(pattern1, rf'\1"{MASK_VALUE}"', masked, flags=re.IGNORECASE)

            # Pattern 2: JSON without key quotes (field:"value")
            pattern2 = rf'(\b{field}\s*:\s*)"([^"]*)"'
            masked = re.sub(pattern2, rf'\1"{MASK_VALUE}"', masked, flags=re.IGNORECASE)

            # Pattern 3: Form data (field=value&) or query params
            pattern3 = rf"(\b{field})=([^\s&\n]*)"
            masked = re.sub(pattern3, rf"\1={MASK_VALUE}", masked, flags=re.IGNORECASE)

            # Pattern 4: Key-value in logs without quotes (field: value)
            # Only match if not already quoted (to avoid double-masking)
            pattern4 = rf'(\b{field}\s*:\s*)([^\s\n,"}}]+)(?=[\s\n,}}]|$)'
            masked = re.sub(pattern4, rf"\1{MASK_VALUE}", masked, flags=re.IGNORECASE)

        return masked

    def _mask_sensitive_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively mask sensitive fields in a dictionary.

        Args:
            data: Dictionary potentially containing sensitive fields

        Returns:
            New dictionary with sensitive fields masked
        """
        if not isinstance(data, dict):
            return data

        masked_data = {}
        fields = self._get_all_sensitive_fields()

        for key, value in data.items():
            if key.lower() in fields:
                # Mask this field entirely
                masked_data[key] = MASK_VALUE
            elif isinstance(value, dict):
                # Recursively mask nested dictionaries
                masked_data[key] = self._mask_sensitive_dict(value)
            elif isinstance(value, (list, tuple)):
                # Handle lists/tuples
                masked_data[key] = type(value)(self._mask_value(item) for item in value)
            elif isinstance(value, str):
                # Mask sensitive patterns in strings
                masked_data[key] = self._mask_sensitive_string(value)
            else:
                masked_data[key] = value

        return masked_data
