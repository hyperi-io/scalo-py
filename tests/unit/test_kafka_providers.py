# Project:   scalo
# File:      tests/unit/test_kafka_providers.py
# Purpose:   Unit tests for the opt-in managed-Kafka provider auth presets
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for scalo.kafka.providers - provider->mechanism derivation.

CANONICAL_TABLE is the cross-language contract (dfe-engine#98), mirrored in
dfe-engine (Python) and scalo-rs (Rust). No broker is touched.
"""

from __future__ import annotations

import pytest

from scalo.kafka import KafkaProviderError, provider_config
from scalo.kafka.config import external_sasl_scram, internal_sasl_scram
from scalo.kafka.providers import derive, validate

CANONICAL_TABLE = {
    "strimzi": ("SASL_SSL", "SCRAM-SHA-512"),
    "redpanda": ("SASL_SSL", "SCRAM-SHA-512"),
    "msk": ("SASL_SSL", "SCRAM-SHA-512"),
    "redpanda-cloud": ("SASL_SSL", "SCRAM-SHA-512"),
    "confluent-cloud": ("SASL_SSL", "PLAIN"),
    "plaintext": ("PLAINTEXT", ""),
    "msk_iam": ("SASL_SSL", "OAUTHBEARER"),
}


class TestDerive:
    @pytest.mark.parametrize(("provider", "expected"), list(CANONICAL_TABLE.items()))
    def test_table(self, provider, expected):
        assert derive(provider) == expected

    def test_confluent_is_the_only_plain(self):
        plain = [p for p, (_, m) in CANONICAL_TABLE.items() if m == "PLAIN"]
        assert plain == ["confluent-cloud"]

    def test_unknown_provider_raises(self):
        with pytest.raises(KafkaProviderError, match="unknown kafka provider"):
            derive("kinesis")


class TestValidate:
    def test_plain_over_plaintext_refused(self):
        with pytest.raises(KafkaProviderError, match="SASL_SSL"):
            validate(security_protocol="PLAINTEXT", sasl_mechanism="PLAIN")

    def test_sasl_ssl_needs_a_mechanism(self):
        with pytest.raises(KafkaProviderError, match="requires a sasl.mechanism"):
            validate(security_protocol="SASL_SSL", sasl_mechanism="")

    def test_every_derived_pair_passes_validation(self):
        for provider in CANONICAL_TABLE:
            proto, mech = derive(provider)
            validate(security_protocol=proto, sasl_mechanism=mech)


class TestProviderConfig:
    def test_confluent_builds_plain_over_tls(self):
        cfg = provider_config("confluent-cloud", "b:9092", "key", "secret")
        assert cfg["security.protocol"] == "SASL_SSL"
        assert cfg["sasl.mechanisms"] == "PLAIN"
        assert cfg["sasl.username"] == "key"
        assert cfg["sasl.password"] == "secret"

    def test_owned_broker_builds_scram(self):
        cfg = provider_config("strimzi", "b:9092", "u", "p")
        assert cfg["sasl.mechanisms"] == "SCRAM-SHA-512"

    def test_plaintext_has_no_sasl_keys(self):
        cfg = provider_config("plaintext", "b:9092")
        assert cfg["security.protocol"] == "PLAINTEXT"
        assert "sasl.mechanisms" not in cfg
        assert "sasl.username" not in cfg

    def test_verify_ssl_false_disables_verification(self):
        cfg = provider_config("confluent-cloud", "b:9092", "u", "p", verify_ssl=False)
        assert cfg["enable.ssl.certificate.verification"] == "false"


class TestVanillaCoreTlsFloor:
    """The vanilla config builders enforce the same PLAIN-requires-TLS floor."""

    def test_internal_scram_refuses_plain_over_plaintext(self):
        with pytest.raises(ValueError, match="SASL_SSL"):
            internal_sasl_scram("k:9092", "u", "p", mechanism="PLAIN")

    def test_external_plain_over_tls_is_allowed(self):
        cfg = external_sasl_scram("k:9093", "u", "p", mechanism="PLAIN")
        assert cfg["security.protocol"] == "SASL_SSL"
        assert cfg["sasl.mechanisms"] == "PLAIN"
