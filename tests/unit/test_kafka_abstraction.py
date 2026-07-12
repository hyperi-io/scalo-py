# Project:   scalo
# File:      tests/unit/test_kafka_abstraction.py
# Purpose:   Unit tests for the full KafkaProvider abstraction - KnownProvider
#            mirrors the scalo-rs canonical table exactly.
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for scalo.kafka.providers - the full KafkaProvider abstraction.

CANONICAL_TABLE is the cross-language contract (dfe-engine#98), mirrored in
scalo-rs (Rust) and dfe-engine (Python). No broker is touched.
"""

from __future__ import annotations

import pytest

from scalo.kafka.providers import (
    AuthKind,
    KafkaProvider,
    KafkaProviderError,
    KnownProvider,
    MetadataMode,
    ProviderCapabilities,
    SchemaRegistry,
    validate,
)

# The cross-language contract (dfe-engine#98). scalo-rs + scalo-py + dfe-engine
# MUST produce this exact table: (provider_key, security_protocol, sasl_mechanism).
CANONICAL_TABLE = [
    ("strimzi", "SASL_SSL", "SCRAM-SHA-512"),
    ("redpanda", "SASL_SSL", "SCRAM-SHA-512"),
    ("msk", "SASL_SSL", "SCRAM-SHA-512"),
    ("redpanda-cloud", "SASL_SSL", "SCRAM-SHA-512"),
    ("confluent-cloud", "SASL_SSL", "PLAIN"),
    ("plaintext", "PLAINTEXT", ""),
    ("msk_iam", "SASL_SSL", "OAUTHBEARER"),
]


class TestCanonicalTable:
    @pytest.mark.parametrize(("key", "proto", "mech"), CANONICAL_TABLE)
    def test_auth_matches_canonical_table(self, key, proto, mech):
        provider = KnownProvider.parse(key)
        assert provider.auth() == (proto, mech)
        assert provider.name() == key

    def test_confluent_is_the_only_plain(self):
        plain = [key for key, _, mech in CANONICAL_TABLE if mech == "PLAIN"]
        assert plain == ["confluent-cloud"]

    def test_unknown_provider_is_rejected(self):
        with pytest.raises(KafkaProviderError, match="unknown kafka provider"):
            KnownProvider.parse("kinesis")

    def test_every_derived_pair_passes_validation(self):
        for key, _, _ in CANONICAL_TABLE:
            proto, mech = KnownProvider.parse(key).auth()
            validate(security_protocol=proto, sasl_mechanism=mech)


class TestCapabilities:
    def test_managed_providers_are_always_on(self):
        for key in ("msk", "confluent-cloud", "redpanda-cloud", "msk_iam"):
            caps = KnownProvider.parse(key).capabilities()
            assert caps.managed, f"{key} is managed"
            assert caps.always_on, f"{key} bills continuously"
            assert caps.requires_tls, f"{key} mandates TLS"

    def test_self_hosted_is_not_managed(self):
        for key in ("strimzi", "redpanda", "plaintext"):
            caps = KnownProvider.parse(key).capabilities()
            assert not caps.managed, f"{key} is self-hosted"
            assert not caps.always_on

    def test_confluent_has_billable_side_resources(self):
        # The Flink compute pool auto-provisioned on cluster-create.
        assert KnownProvider.CONFLUENT_CLOUD.capabilities().has_billable_side_resources
        assert not KnownProvider.REDPANDA_CLOUD.capabilities().has_billable_side_resources

    def test_msk_provisioned_is_not_serverless(self):
        assert not KnownProvider.MSK.capabilities().serverless
        assert KnownProvider.REDPANDA_CLOUD.capabilities().serverless

    def test_auth_kind_reflects_credential_family(self):
        assert KnownProvider.MSK_IAM.capabilities().auth_kind == AuthKind.IAM
        assert KnownProvider.STRIMZI.capabilities().auth_kind == AuthKind.USER_PASSWORD
        assert KnownProvider.PLAINTEXT.capabilities().auth_kind == AuthKind.NONE

    def test_capabilities_is_frozen(self):
        caps = KnownProvider.STRIMZI.capabilities()
        with pytest.raises(AttributeError):
            caps.managed = True  # type: ignore[misc]


class TestMetadataMode:
    def test_kraft_native_and_self_hosted(self):
        assert KnownProvider.REDPANDA.metadata_mode() == MetadataMode.KRAFT
        assert KnownProvider.STRIMZI.metadata_mode() == MetadataMode.KRAFT
        assert KnownProvider.MSK.metadata_mode() == MetadataMode.KRAFT
        assert KnownProvider.PLAINTEXT.metadata_mode() == MetadataMode.KRAFT

    def test_clouds_are_managed_hidden(self):
        for key in ("confluent-cloud", "redpanda-cloud", "msk_iam"):
            assert KnownProvider.parse(key).metadata_mode() == MetadataMode.MANAGED, f"{key} is managed-hidden"


class TestSchemaRegistry:
    def test_schema_registry_kind_per_provider(self):
        assert KnownProvider.CONFLUENT_CLOUD.schema_registry() == SchemaRegistry.CONFLUENT
        assert KnownProvider.REDPANDA_CLOUD.schema_registry() == SchemaRegistry.REDPANDA
        assert KnownProvider.REDPANDA.schema_registry() == SchemaRegistry.REDPANDA
        assert KnownProvider.STRIMZI.schema_registry() == SchemaRegistry.NONE
        assert KnownProvider.MSK.schema_registry() == SchemaRegistry.NONE
        assert KnownProvider.PLAINTEXT.schema_registry() == SchemaRegistry.NONE


class TestKnownProviderIsAKafkaProvider:
    """KnownProvider satisfies the KafkaProvider Protocol via duck typing -
    no inheritance required. That is the OPEN part of the abstraction.
    """

    @pytest.mark.parametrize("provider", list(KnownProvider))
    def test_isinstance_check(self, provider):
        assert isinstance(provider, KafkaProvider)

    def test_transport_overrides_default_empty(self):
        assert KnownProvider.STRIMZI.transport_overrides() == {}


# A third-party provider with its own weirdness plugs in by implementing the
# Protocol - no change to this module needed. (Illustrative: NOT a blessed
# provider - mirrors scalo-rs's DemoProvider test.)
class DemoProvider(KafkaProvider):
    """A demo AutoMQ-shaped provider - only the mandatory concerns
    implemented; metadata_mode / schema_registry / transport_overrides fall
    back to the Protocol's defaults (KRaft / none / empty).
    """

    def name(self) -> str:
        return "demo"

    def auth(self) -> tuple[str, str]:
        return ("SASL_SSL", "SCRAM-SHA-256")

    def capabilities(self) -> ProviderCapabilities:
        return KnownProvider.REDPANDA.capabilities()


class TestThirdPartyProvider:
    def test_implements_the_protocol(self):
        demo = DemoProvider()
        assert isinstance(demo, KafkaProvider)
        assert demo.name() == "demo"
        proto, mech = demo.auth()
        validate(security_protocol=proto, sasl_mechanism=mech)

    def test_falls_back_to_protocol_defaults(self):
        demo = DemoProvider()
        assert demo.metadata_mode() == MetadataMode.KRAFT
        assert demo.schema_registry() == SchemaRegistry.NONE
        assert demo.transport_overrides() == {}
