# Project:   scalo
# File:      tests/unit/test_kafka_toolconfig.py
# Purpose:   Unit tests for Kafka tool config emission (kafbat-ui / kcat /
#            librdkafka .properties).
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Unit tests for scalo.kafka.toolconfig - provider + connection -> tool
config emission. No broker is touched.
"""

from __future__ import annotations

import pytest

from scalo.kafka.providers import KafkaProviderError
from scalo.kafka.toolconfig import (
    Connection,
    emit_kafbat_cluster,
    emit_kcat,
    emit_librdkafka_properties,
)


class TestEmitLibrdkafkaProperties:
    def test_confluent_cloud_plain_case(self):
        conn = Connection(
            bootstrap_servers="pkc-xxxx.confluent.cloud:9092",
            username="API_KEY",
            password="API_SECRET",
        )
        body = emit_librdkafka_properties("confluent-cloud", conn)
        assert body == (
            "bootstrap.servers=pkc-xxxx.confluent.cloud:9092\n"
            "security.protocol=SASL_SSL\n"
            "sasl.mechanisms=PLAIN\n"
            "sasl.username=API_KEY\n"
            "sasl.password=API_SECRET\n"
        )

    def test_redpanda_scram_case(self):
        conn = Connection(bootstrap_servers="redpanda:9093", username="svc", password="pw")
        body = emit_librdkafka_properties("redpanda", conn)
        assert body == (
            "bootstrap.servers=redpanda:9093\n"
            "security.protocol=SASL_SSL\n"
            "sasl.mechanisms=SCRAM-SHA-512\n"
            "sasl.username=svc\n"
            "sasl.password=pw\n"
        )

    def test_plaintext_no_sasl_case(self):
        conn = Connection(bootstrap_servers="localhost:9092")
        body = emit_librdkafka_properties("plaintext", conn)
        assert body == ("bootstrap.servers=localhost:9092\nsecurity.protocol=PLAINTEXT\n")
        assert "sasl" not in body

    def test_unknown_provider_refused(self):
        conn = Connection(bootstrap_servers="b:9092")
        with pytest.raises(KafkaProviderError, match="unknown kafka provider"):
            emit_librdkafka_properties("kinesis", conn)


class TestEmitKcat:
    def test_kcat_matches_librdkafka_properties_body(self):
        conn = Connection(bootstrap_servers="redpanda:9093", username="svc", password="pw")
        assert emit_kcat("redpanda", conn) == emit_librdkafka_properties("redpanda", conn)

    def test_kcat_plaintext_no_sasl_case(self):
        conn = Connection(bootstrap_servers="localhost:9092")
        body = emit_kcat("plaintext", conn)
        assert body == ("bootstrap.servers=localhost:9092\nsecurity.protocol=PLAINTEXT\n")


class TestEmitKafbatCluster:
    def test_confluent_cloud_plain_case(self):
        conn = Connection(
            bootstrap_servers="pkc-xxxx.confluent.cloud:9092",
            username="API_KEY",
            password="API_SECRET",
        )
        cluster = emit_kafbat_cluster("confluent-cloud", conn)
        assert cluster == {
            "name": "confluent-cloud",
            "bootstrapServers": "pkc-xxxx.confluent.cloud:9092",
            "properties": {
                "security.protocol": "SASL_SSL",
                "sasl.mechanism": "PLAIN",
                "sasl.jaas.config": (
                    "org.apache.kafka.common.security.plain.PlainLoginModule "
                    'required username="API_KEY" password="API_SECRET";'
                ),
            },
        }

    def test_confluent_cloud_includes_schema_registry_when_url_set(self):
        conn = Connection(
            bootstrap_servers="pkc-xxxx.confluent.cloud:9092",
            username="API_KEY",
            password="API_SECRET",
            schema_registry_url="https://psrc-xxxx.confluent.cloud",
        )
        cluster = emit_kafbat_cluster("confluent-cloud", conn)
        assert cluster["schemaRegistry"] == "https://psrc-xxxx.confluent.cloud"

    def test_redpanda_scram_case(self):
        conn = Connection(
            bootstrap_servers="redpanda:9093",
            username="svc",
            password="pw",
            schema_registry_url="http://redpanda:8081",
        )
        cluster = emit_kafbat_cluster("redpanda", conn)
        assert cluster == {
            "name": "redpanda",
            "bootstrapServers": "redpanda:9093",
            "properties": {
                "security.protocol": "SASL_SSL",
                "sasl.mechanism": "SCRAM-SHA-512",
                "sasl.jaas.config": (
                    'org.apache.kafka.common.security.scram.ScramLoginModule required username="svc" password="pw";'
                ),
            },
            "schemaRegistry": "http://redpanda:8081",
        }

    def test_strimzi_scram_has_no_schema_registry(self):
        # strimzi has no bundled schema registry, even if a URL is passed.
        conn = Connection(bootstrap_servers="b:9092", username="u", password="p", schema_registry_url="http://sr:8081")
        cluster = emit_kafbat_cluster("strimzi", conn)
        assert "schemaRegistry" not in cluster

    def test_plaintext_no_sasl_case(self):
        conn = Connection(bootstrap_servers="localhost:9092")
        cluster = emit_kafbat_cluster("plaintext", conn)
        assert cluster == {
            "name": "plaintext",
            "bootstrapServers": "localhost:9092",
            "properties": {},
        }
        assert "schemaRegistry" not in cluster

    def test_unknown_provider_refused(self):
        conn = Connection(bootstrap_servers="b:9092")
        with pytest.raises(KafkaProviderError, match="unknown kafka provider"):
            emit_kafbat_cluster("kinesis", conn)


class TestExportedFromPackage:
    """Verify the toolconfig emitters are reachable from ``scalo.kafka``."""

    def test_emitters_importable(self):
        from scalo.kafka import Connection as PkgConnection
        from scalo.kafka import emit_kafbat_cluster as pkg_kafbat
        from scalo.kafka import emit_kcat as pkg_kcat
        from scalo.kafka import emit_librdkafka_properties as pkg_props

        assert callable(pkg_kafbat)
        assert callable(pkg_kcat)
        assert callable(pkg_props)
        assert PkgConnection is Connection
