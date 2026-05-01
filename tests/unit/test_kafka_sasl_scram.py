# Project:   hyperi-pylib
# File:      tests/unit/test_kafka_sasl_scram.py
# Purpose:   Unit tests for Kafka SASL-SCRAM helper functions
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for kafka.config.external_sasl_scram / internal_sasl_scram."""

from __future__ import annotations

import pytest

from hyperi_pylib.kafka import (
    CONSUMER_DEFAULTS,
    PRODUCER_DEFAULTS,
    external_sasl_scram,
    internal_sasl_scram,
    merge_config,
)


class TestExternalSaslScram:
    def test_default_mechanism_is_scram_sha_512(self):
        cfg = external_sasl_scram("kafka.prod:9093", "user", "pass")
        assert cfg["sasl.mechanisms"] == "SCRAM-SHA-512"

    def test_uses_sasl_ssl(self):
        cfg = external_sasl_scram("kafka.prod:9093", "user", "pass")
        assert cfg["security.protocol"] == "SASL_SSL"

    def test_includes_credentials(self):
        cfg = external_sasl_scram("kafka:9093", "svc-loader", "secret-pw")
        assert cfg["sasl.username"] == "svc-loader"
        assert cfg["sasl.password"] == "secret-pw"
        assert cfg["bootstrap.servers"] == "kafka:9093"

    def test_custom_mechanism(self):
        cfg = external_sasl_scram("kafka:9093", "u", "p", mechanism="SCRAM-SHA-256")
        assert cfg["sasl.mechanisms"] == "SCRAM-SHA-256"

    def test_verify_ssl_true_omits_disable_flag(self):
        cfg = external_sasl_scram("kafka:9093", "u", "p", verify_ssl=True)
        assert "enable.ssl.certificate.verification" not in cfg

    def test_verify_ssl_false_disables_verification(self):
        cfg = external_sasl_scram("kafka:9093", "u", "p", verify_ssl=False)
        assert cfg["enable.ssl.certificate.verification"] == "false"

    def test_merges_with_producer_defaults(self):
        base = external_sasl_scram("kafka:9093", "u", "p")
        merged = merge_config(base, PRODUCER_DEFAULTS)
        assert merged["security.protocol"] == "SASL_SSL"
        assert merged["acks"] == "all"  # PRODUCER_DEFAULTS preserved
        assert merged["compression.type"] == "lz4"


class TestInternalSaslScram:
    def test_uses_sasl_plaintext(self):
        cfg = internal_sasl_scram("kafka.svc:9092", "user", "pass")
        assert cfg["security.protocol"] == "SASL_PLAINTEXT"

    def test_default_mechanism_is_scram_sha_512(self):
        cfg = internal_sasl_scram("kafka.svc:9092", "user", "pass")
        assert cfg["sasl.mechanisms"] == "SCRAM-SHA-512"

    def test_includes_credentials(self):
        cfg = internal_sasl_scram("k:9092", "u", "p")
        assert cfg["sasl.username"] == "u"
        assert cfg["sasl.password"] == "p"
        assert cfg["bootstrap.servers"] == "k:9092"

    def test_no_ssl_verify_flag_for_internal(self):
        # internal flavour doesn't speak SSL, so the flag should never appear
        cfg = internal_sasl_scram("k:9092", "u", "p")
        assert "enable.ssl.certificate.verification" not in cfg

    def test_merges_with_consumer_defaults(self):
        base = internal_sasl_scram("k:9092", "u", "p")
        merged = merge_config(base, CONSUMER_DEFAULTS)
        assert merged["security.protocol"] == "SASL_PLAINTEXT"
        assert merged["enable.auto.commit"] is False  # CONSUMER_DEFAULTS preserved
        assert merged["auto.offset.reset"] == "earliest"


class TestExportedFromPackage:
    """Verify both helpers are reachable from ``hyperi_pylib.kafka``."""

    def test_external_importable(self):
        from hyperi_pylib.kafka import external_sasl_scram as ext

        assert callable(ext)

    def test_internal_importable(self):
        from hyperi_pylib.kafka import internal_sasl_scram as itn

        assert callable(itn)
