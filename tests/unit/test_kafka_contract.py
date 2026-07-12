# Project:   scalo
# File:      tests/unit/test_kafka_contract.py
# Purpose:   Unit tests for the opt-in STRICT Kafka credential profile
#            (scalo.kafka.contract) - blessed set + never-weakened auth.
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for scalo.kafka.contract - the opt-in DFE credential contract
(dfe-engine#98) framed generically. No broker is touched.
"""

from __future__ import annotations

import pytest

from scalo.kafka import contract
from scalo.kafka.providers import KafkaProviderError


class TestDefaultAllowed:
    def test_blessed_set_excludes_msk_iam(self):
        assert "msk_iam" not in contract.DEFAULT_ALLOWED

    def test_blessed_set_is_exactly_six_providers(self):
        assert (
            frozenset(
                {
                    "strimzi",
                    "redpanda",
                    "msk",
                    "redpanda-cloud",
                    "confluent-cloud",
                    "plaintext",
                }
            )
            == contract.DEFAULT_ALLOWED
        )


class TestRequire:
    def test_blessed_provider_returns_derived_auth(self):
        assert contract.require("strimzi") == ("SASL_SSL", "SCRAM-SHA-512")
        assert contract.require("confluent-cloud") == ("SASL_SSL", "PLAIN")
        assert contract.require("plaintext") == ("PLAINTEXT", "")

    def test_msk_iam_refused_under_default_allowlist(self):
        with pytest.raises(KafkaProviderError, match="not in the blessed set"):
            contract.require("msk_iam")

    def test_unknown_provider_refused(self):
        with pytest.raises(KafkaProviderError, match="not in the blessed set"):
            contract.require("kinesis")

    def test_custom_allowed_set_narrows_further(self):
        narrow = frozenset({"plaintext"})
        assert contract.require("plaintext", allowed=narrow) == ("PLAINTEXT", "")
        with pytest.raises(KafkaProviderError, match="not in the blessed set"):
            contract.require("strimzi", allowed=narrow)

    def test_custom_allowed_set_can_admit_msk_iam(self):
        # Opt-in escape hatch: a caller who KNOWS they want IAM can widen the
        # allow-list explicitly - the quarantine is a default, not a wall.
        widened = contract.DEFAULT_ALLOWED | {"msk_iam"}
        assert contract.require("msk_iam", allowed=widened) == ("SASL_SSL", "OAUTHBEARER")


class TestAssertNotWeakened:
    def test_matching_auth_passes(self):
        contract.assert_not_weakened("confluent-cloud", "SASL_SSL", "PLAIN")
        contract.assert_not_weakened("strimzi", "SASL_SSL", "SCRAM-SHA-512")
        contract.assert_not_weakened("plaintext", "PLAINTEXT", "")

    def test_downgrade_to_plaintext_is_refused(self):
        with pytest.raises(KafkaProviderError, match="never weaken"):
            contract.assert_not_weakened("strimzi", "PLAINTEXT", "")

    def test_downgrade_scram_to_plain_is_refused(self):
        # A provider that supports SCRAM hand-set to PLAIN - a downgrade.
        with pytest.raises(KafkaProviderError, match="never weaken"):
            contract.assert_not_weakened("redpanda", "SASL_SSL", "PLAIN")

    def test_unknown_provider_propagates(self):
        with pytest.raises(KafkaProviderError, match="unknown kafka provider"):
            contract.assert_not_weakened("kinesis", "SASL_SSL", "PLAIN")
