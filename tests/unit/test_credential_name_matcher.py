#  Project:   scalo
#  File:      tests/unit/test_credential_name_matcher.py
#  Purpose:   The one credential-name matcher every masking path calls
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""A name is a credential when a sensitive term sits anywhere in it, however the name is spelt."""

import pytest

from scalo.logger.filters import SENSITIVE_FIELDS, SensitiveDataFilter, is_credential_name

# Names a credential goes out under, in the spellings apps, brokers, charts and HTTP use.
CREDENTIAL_NAMES = [
    "db_password",
    "PASSWORD",
    "api_token",
    "x-api-key",
    "secretAccessKey",
    "client_secret",
    "sasl_password",
    "KAFKA_SASL_PASSWORD",
    "sasl.password",
    "rootPassword",
    "PGPASSWORD",
    "password_hash",
    "bearer_tokens",
    "refreshToken",
    "privateKey",
    "signingKey",
    "JWT_KEY",
    "s3_secret_key",
    "maxmind_license_key",
    "service_account_key",
    "KAFKA_SASL_JAAS_CONFIG",
    "auth_token",
    "X-Auth-Token",
    "passphrase",
    "credential",
    "ssl.key.password",
    "ssl.key.pem",
    "header_values",
    "connection_string",
    "session_cookie",
]

# Settings an operator reads in a log line, which no sensitive term reaches.
SHOWN_NAMES = [
    "username",
    "host",
    "port",
    "topic",
    "KAFKA_PARTITION_KEY",
    "routing_key",
    "bootstrap.servers",
    "group.id",
    "count",
    "status",
    "key",
    "value",
]

# scalo-rs default_sensitive_fields(): both libraries mask every one of these.
SCALO_RS_DEFAULTS = [
    "password",
    "passwd",
    "pwd",
    "pass",
    "token",
    "secret",
    "api_key",
    "apikey",
    "api-key",
    "access_key",
    "secret_key",
    "private_key",
    "privatekey",
    "auth",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "client_secret",
    "refresh_token",
    "access_token",
    "ssn",
    "credit_card",
    "creditcard",
    "cvv",
    "pin",
]


@pytest.mark.parametrize("name", CREDENTIAL_NAMES)
def test_a_credential_name_matches(name):
    assert is_credential_name(name)


@pytest.mark.parametrize("name", SHOWN_NAMES)
def test_a_setting_name_does_not_match(name):
    assert not is_credential_name(name)


@pytest.mark.parametrize("name", ["api_key", "API_KEY", "apiKey", "ApiKey", "api-key", "api.key", "x-api-key"])
def test_every_spelling_of_a_term_matches(name):
    assert is_credential_name(name)


@pytest.mark.parametrize("name", SCALO_RS_DEFAULTS)
def test_every_scalo_rs_default_is_a_credential_here(name):
    assert name in SENSITIVE_FIELDS
    assert is_credential_name(name)


@pytest.mark.parametrize(
    ("name", "parent"),
    [
        pytest.param("key", "tls", id="tls-key"),
        pytest.param("keys", "ssl", id="ssl-keys"),
        pytest.param("value", "token", id="token-value"),
        pytest.param("values", "accepted_headers", id="accepted-header-values"),
    ],
)
def test_a_bare_key_or_value_is_judged_with_its_parent(name, parent):
    assert is_credential_name(name, parent)


@pytest.mark.parametrize(
    ("name", "parent"),
    [
        pytest.param("key", "kafka", id="kafka-key"),
        pytest.param("key", "", id="no-parent"),
        pytest.param("value", "dlq", id="dlq-value"),
        pytest.param("brokers", "tls", id="named-field-ignores-parent"),
    ],
)
def test_a_parent_qualifies_only_a_bare_key_or_value(name, parent):
    assert not is_credential_name(name, parent)


def test_extra_terms_apply_to_that_call_only():
    assert is_credential_name("okta_user_id", extra={"okta_user_id"})
    assert not is_credential_name("okta_user_id")


def test_a_globally_added_field_reaches_the_matcher():
    SensitiveDataFilter.add_sensitive_fields({"employee_ref"})
    try:
        assert is_credential_name("EmployeeRef")
    finally:
        SensitiveDataFilter._custom_fields.discard("employee_ref")
    assert not is_credential_name("EmployeeRef")


@pytest.mark.parametrize("name", ["", "-", "__", "123"])
def test_a_name_with_no_term_does_not_match(name):
    assert not is_credential_name(name)
