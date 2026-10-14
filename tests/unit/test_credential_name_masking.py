#  Project:   scalo
#  File:      tests/unit/test_credential_name_masking.py
#  Purpose:   Every masking path hides a credential named in any spelling
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Log records, dicts, scrubbed text, URLs and Kafka configs all hide a credential by its name.

Every value is built at runtime, so no secret-shaped literal sits in source.
"""

import json
import sys

import pytest
from common.fake_secrets import opaque_secret
from common.log_capture import LOGGER_ENV_VARS, StreamDouble, preserved_stdlib_logging
from loguru import logger

from scalo.kafka.config import mask_credentials
from scalo.logger.filters import MASK_VALUE, SensitiveDataFilter
from scalo.logger.logger import setup
from scalo.logger.scrub import FieldNameScrubber, build_scrubber

SECRET = opaque_secret("credname")

# Credential names that each spelling rule has to reach: exact, case, kebab, camel, run-together, prefixed.
CREDENTIAL_KEYS = [
    "db_password",
    "PASSWORD",
    "api_token",
    "x-api-key",
    "secretAccessKey",
    "client_secret",
    "sasl_password",
    "KAFKA_SASL_PASSWORD",
    "rootPassword",
    "PGPASSWORD",
    "password_hash",
    "bearer_tokens",
    "refreshToken",
    "privateKey",
    "signingKey",
    "JWT_KEY",
    "maxmind_license_key",
    "KAFKA_SASL_JAAS_CONFIG",
    "X-Auth-Token",
    "passphrase",
    "ssl.key.password",
    "header_values",
]

SHOWN_KEYS = ["username", "host", "port", "topic", "KAFKA_PARTITION_KEY", "routing_key", "bootstrap.servers"]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for name in LOGGER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_ENQUEUE", "0")
    with preserved_stdlib_logging():
        yield
        logger.remove()


def _json_logger(monkeypatch) -> StreamDouble:
    stream = StreamDouble(False)
    monkeypatch.setattr(sys, "stderr", stream)
    setup(otel_tracing=False, log_format="json")
    return stream


def _fields(stream: StreamDouble) -> dict:
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1, lines
    return json.loads(lines[0])["fields"]


# ---------------------------------------------------------------------------
# log records
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CREDENTIAL_KEYS)
def test_a_log_field_named_as_a_credential_is_masked(monkeypatch, key):
    stream = _json_logger(monkeypatch)

    logger.warning("connect", **{key: SECRET})

    assert SECRET not in stream.getvalue()
    assert _fields(stream)[key] == MASK_VALUE


@pytest.mark.parametrize("key", SHOWN_KEYS)
def test_a_log_field_named_as_a_setting_is_shown(monkeypatch, key):
    stream = _json_logger(monkeypatch)

    logger.warning("connect", **{key: "plain-setting"})

    assert _fields(stream)[key] == "plain-setting"


def test_a_credential_nested_in_a_log_field_is_masked(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("connect", kafka={"brokers": "b1:9092", "sasl": {"saslPassword": SECRET}})

    kafka = _fields(stream)["kafka"]
    assert SECRET not in stream.getvalue()
    assert kafka["brokers"] == "b1:9092"
    assert kafka["sasl"]["saslPassword"] == MASK_VALUE


def test_a_credential_in_a_list_of_dicts_in_a_log_field_is_masked(monkeypatch):
    stream = _json_logger(monkeypatch)
    other = opaque_secret("second")

    logger.warning("sources", connections=[{"id": "a", "authToken": SECRET}, {"id": "b", "authToken": other}])

    connections = _fields(stream)["connections"]
    assert SECRET not in stream.getvalue()
    assert other not in stream.getvalue()
    assert connections == [{"id": "a", "authToken": MASK_VALUE}, {"id": "b", "authToken": MASK_VALUE}]


def test_a_bare_key_under_tls_in_a_log_field_is_masked(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("listener", tls={"enabled": True, "key": SECRET}, partitioner={"key": "order_id"})

    fields = _fields(stream)
    assert SECRET not in stream.getvalue()
    assert fields["tls"] == {"enabled": True, "key": MASK_VALUE}
    assert fields["partitioner"] == {"key": "order_id"}


def test_header_values_in_a_list_of_entries_are_masked(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("auth", accepted_headers=[{"name": "x-tenant", "values": [SECRET]}])

    assert SECRET not in stream.getvalue()
    assert _fields(stream)["accepted_headers"][0]["name"] == "x-tenant"


def test_a_two_item_pair_named_as_a_credential_masks_its_value(monkeypatch):
    stream = _json_logger(monkeypatch)

    logger.warning("upstream", headers=[("X-Api-Key", SECRET), ("accept", "application/json")])

    headers = _fields(stream)["headers"]
    assert SECRET not in stream.getvalue()
    assert headers == [["X-Api-Key", MASK_VALUE], ["accept", "application/json"]]


def test_a_url_password_holding_an_at_sign_is_masked_in_a_message(monkeypatch):
    stream = _json_logger(monkeypatch)
    password = "p" + "@" + SECRET

    # A dotless host, so L3's email rule cannot be what hides the tail of the password.
    logger.warning(f"connecting to postgres://svc:{password}@db:5432/app")

    assert SECRET not in stream.getvalue()


# ---------------------------------------------------------------------------
# dicts through the legacy SensitiveDataFilter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CREDENTIAL_KEYS)
def test_a_dict_key_named_as_a_credential_is_masked(key):
    masked = SensitiveDataFilter()._mask_sensitive_dict({key: SECRET, "host": "db"})

    assert masked == {key: MASK_VALUE, "host": "db"}


def test_nested_dicts_and_lists_of_dicts_are_masked():
    data = {
        "kafka": {"brokers": "b1:9092", "sasl": {"saslPassword": SECRET}},
        "connections": [{"id": "a", "authToken": SECRET}],
        "tls": {"enabled": True, "key": SECRET},
        "partitioner": {"key": "order_id"},
    }

    masked = SensitiveDataFilter()._mask_sensitive_dict(data)

    assert masked == {
        "kafka": {"brokers": "b1:9092", "sasl": {"saslPassword": MASK_VALUE}},
        "connections": [{"id": "a", "authToken": MASK_VALUE}],
        "tls": {"enabled": True, "key": MASK_VALUE},
        "partitioner": {"key": "order_id"},
    }


def test_a_non_string_dict_key_does_not_break_masking():
    masked = SensitiveDataFilter()._mask_sensitive_dict({1: "one", "apiKey": SECRET})

    assert masked == {1: "one", "apiKey": MASK_VALUE}


# ---------------------------------------------------------------------------
# text through L2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(f"secretAccessKey={SECRET}", f"secretAccessKey={MASK_VALUE}", id="camel-env"),
        pytest.param(f"x-api-key: {SECRET}", f"x-api-key: {MASK_VALUE}", id="kebab-header"),
        pytest.param(f"api_token_value={SECRET}", f"api_token_value={MASK_VALUE}", id="term-mid-key"),
        pytest.param(f'{{"clientSecret": "{SECRET}"}}', f'{{"clientSecret": "{MASK_VALUE}"}}', id="camel-json"),
        pytest.param(f"PGPASSWORD={SECRET}", f"PGPASSWORD={MASK_VALUE}", id="run-together"),
        pytest.param(f"db_password={SECRET}", f"db_password={MASK_VALUE}", id="snake-env"),
        pytest.param(f"ssl.key.pem: {SECRET}", f"ssl.key.pem: {MASK_VALUE}", id="dotted-librdkafka"),
    ],
)
def test_a_credential_key_in_text_is_masked(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("config:password:hunter2", f"config:password:{MASK_VALUE}", id="colon-chain"),
        pytest.param("ctx: a=1 token=abc", f"ctx: a=1 token={MASK_VALUE}", id="pair-after-a-pair"),
        pytest.param("password: token: abc", f"password: {MASK_VALUE} abc", id="value-is-masked-once"),
    ],
)
def test_a_credential_key_inside_another_pair_is_still_judged(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("pin: 1234 5678", f"pin: {MASK_VALUE}", id="colon-digit-groups"),
        pytest.param("password=1234 5678&next=1", f"password={MASK_VALUE}&next=1", id="equals-digit-groups"),
        pytest.param("phone: +61 412 345 678 on file", f"phone: {MASK_VALUE} on file", id="stops-at-a-word"),
    ],
)
def test_an_unquoted_value_runs_across_digit_groups(line, expected):
    assert FieldNameScrubber().scrub(line) == expected


@pytest.mark.parametrize(
    ("line", "digits"),
    [
        pytest.param("TFN: 123 456 782", "456 782", id="tfn"),
        pytest.param("phone: +61 412 345 678", "345 678", id="phone"),
        pytest.param("credit_card: 4111 1111 1111 1111", "1111 1111", id="card"),
    ],
)
def test_the_default_chain_never_leaves_part_of_a_number_under_a_named_key(line, digits):
    assert digits not in build_scrubber().scrub(line)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param(
            "postgres://svc:{pw}@db.internal:5432/app",
            f"postgres://svc:{MASK_VALUE}@db.internal:5432/app",
            id="one-at-sign-in-password",
        ),
        pytest.param(
            "mysql://root:a@b@{pw}@db:3306/app",
            f"mysql://root:{MASK_VALUE}@db:3306/app",
            id="two-at-signs-in-password",
        ),
        pytest.param(
            "amqp://guest:pa/{secret}@broker/vhost",
            f"amqp://guest:{MASK_VALUE}@broker/vhost",
            id="slash-in-password",
        ),
        pytest.param("redis://:{pw}@cache:6379/0", f"redis://:{MASK_VALUE}@cache:6379/0", id="no-user"),
        pytest.param(
            "https://svc:{pw}@api.example.com/v1?notify=ops@example.com",
            f"https://svc:{MASK_VALUE}@api.example.com/v1?notify=ops@example.com",
            id="at-sign-in-query",
        ),
        pytest.param("https://api.example.com:8443/health", "https://api.example.com:8443/health", id="no-userinfo"),
    ],
)
def test_url_userinfo_is_masked_up_to_the_host(line, expected):
    text = line.format(pw="p" + "@" + SECRET, secret=SECRET)

    assert FieldNameScrubber().scrub(text) == expected


# ---------------------------------------------------------------------------
# Kafka client configs
# ---------------------------------------------------------------------------


def test_kafka_config_masks_credentials_by_name():
    config = {
        "bootstrap.servers": "b1:9092",
        "client.id": "orders-api",
        "sasl.username": "svc-orders",
        "sasl.password": SECRET,
        "sasl.oauthbearer.client.secret": SECRET,
        "ssl.key.pem": SECRET,
    }

    masked = mask_credentials(config)

    assert masked == {
        "bootstrap.servers": "b1:9092",
        "client.id": "orders-api",
        "sasl.username": "***",
        "sasl.password": "***",
        "sasl.oauthbearer.client.secret": "***",
        "ssl.key.pem": "***",
    }
