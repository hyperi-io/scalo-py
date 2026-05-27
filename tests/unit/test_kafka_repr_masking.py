#  Project:   hyperi-pylib
#  File:      tests/unit/test_kafka_repr_masking.py
#  Purpose:   Verify Kafka client __repr__ masks SASL/SSL credentials
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""S10 regression: any repr(client) must mask sasl.password and similar
credential keys. Logs, exception traces, and debug dumps frequently
embed repr() output -- raw passwords there leak to disk."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

SECRET = "p@ssw0rd-DO-NOT-LEAK"


def _config_with_creds() -> dict:
    return {
        "bootstrap.servers": "broker:9092",
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "SCRAM-SHA-512",
        "sasl.username": "service-account",
        "sasl.password": SECRET,
        "ssl.key.password": SECRET,
    }


@pytest.fixture
def patched():
    """Patch all confluent_kafka client constructors so we can instantiate
    without a real broker."""
    with (
        patch("hyperi_pylib.kafka.client.AdminClient", return_value=MagicMock()),
        patch("hyperi_pylib.kafka.producer.Producer", return_value=MagicMock()),
        patch("hyperi_pylib.kafka.consumer.Consumer", return_value=MagicMock()),
        patch("hyperi_pylib.kafka.admin.AdminClient", return_value=MagicMock()),
        patch("hyperi_pylib.kafka.async_client.AdminClient", return_value=MagicMock()),
        patch("hyperi_pylib.kafka.async_consumer.Consumer", return_value=MagicMock()),
        patch("hyperi_pylib.kafka.async_producer.Producer", return_value=MagicMock()),
    ):
        yield


def test_kafka_client_repr_masks_creds(patched):
    from hyperi_pylib.kafka.client import KafkaClient

    r = repr(KafkaClient(_config_with_creds()))
    assert SECRET not in r
    assert "***" in r


def test_kafka_producer_repr_masks_creds(patched):
    from hyperi_pylib.kafka.producer import KafkaProducer

    r = repr(KafkaProducer(_config_with_creds()))
    assert SECRET not in r


def test_kafka_consumer_repr_masks_creds(patched):
    from hyperi_pylib.kafka.consumer import KafkaConsumer

    r = repr(KafkaConsumer(_config_with_creds(), group_id="g"))
    assert SECRET not in r


def test_kafka_admin_repr_masks_creds(patched):
    from hyperi_pylib.kafka.admin import KafkaAdmin

    r = repr(KafkaAdmin(_config_with_creds()))
    assert SECRET not in r


def test_async_kafka_client_repr_masks_creds(patched):
    from hyperi_pylib.kafka.async_client import AsyncKafkaClient

    r = repr(AsyncKafkaClient(_config_with_creds()))
    assert SECRET not in r


def test_async_kafka_consumer_repr_masks_creds(patched):
    from hyperi_pylib.kafka.async_consumer import AsyncKafkaConsumer

    r = repr(AsyncKafkaConsumer(_config_with_creds(), group_id="g"))
    assert SECRET not in r


def test_async_kafka_producer_repr_masks_creds(patched):
    from hyperi_pylib.kafka.async_producer import AsyncKafkaProducer

    r = repr(AsyncKafkaProducer(_config_with_creds()))
    assert SECRET not in r


def test_mask_credentials_keeps_non_cred_keys():
    from hyperi_pylib.kafka.config import mask_credentials

    cfg = {
        "bootstrap.servers": "host:9092",
        "sasl.password": "secret",
        "client.id": "test-app",
    }
    masked = mask_credentials(cfg)
    assert masked["bootstrap.servers"] == "host:9092"
    assert masked["client.id"] == "test-app"
    assert masked["sasl.password"] == "***"
    # Original untouched
    assert cfg["sasl.password"] == "secret"
