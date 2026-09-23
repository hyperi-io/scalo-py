# Project:   scalo
# File:      tests/unit/test_kafka_internal_group_ids.py
# Purpose:   Unit tests for the group ids scalo derives for its own Kafka consumers
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""The offset-query consumers take a group id under the prefix the broker grants.

librdkafka looks up the coordinator for a consumer's ``group.id`` as soon as it
connects, whether or not it ever subscribes. A broker that grants groups by
prefix (DFE grants ``dfe-``) refuses any group outside it and logs
``GroupAuthorizationFailed``, so these ids derive from the caller's config.
"""

import ast
from pathlib import Path

import pytest
from confluent_kafka import Consumer

import scalo.kafka
from scalo.kafka import AsyncKafkaClient, KafkaClient, ReadOnlyKafkaClient
from scalo.kafka.config import _internal_group_id, _offset_query_consumer_config

# Nothing listens on port 1, and librdkafka connects lazily, so no test here reaches a broker.
_NO_BROKER = "127.0.0.1:1"

# The prefix a DFE broker grants its apps' consumer groups.
_GRANTED_PREFIX = "dfe-"


class TestInternalGroupId:
    def test_group_anchors_the_id(self):
        assert _internal_group_id({"group.id": "dfe-loader"}, "admin") == "dfe-loader-admin"

    def test_group_wins_over_client_id(self):
        config = {"group.id": "dfe-archiver", "client.id": "archiver-pod-7"}
        assert _internal_group_id(config, "admin") == "dfe-archiver-admin"

    def test_client_id_anchors_a_config_with_no_group(self):
        assert _internal_group_id({"client.id": "dfe-fetcher"}, "admin") == "dfe-fetcher-admin"

    def test_empty_group_falls_back_to_client_id(self):
        config = {"group.id": "", "client.id": "dfe-fetcher"}
        assert _internal_group_id(config, "admin") == "dfe-fetcher-admin"

    def test_bare_config_falls_back_to_the_default_client_id(self):
        # Never empty: librdkafka refuses to build a consumer with an empty group.id.
        assert _internal_group_id({"bootstrap.servers": _NO_BROKER}, "admin") == "scalo-admin"
        assert _internal_group_id({"group.id": "", "client.id": ""}, "admin") == "scalo-admin"


class TestOffsetQueryConsumerConfig:
    @pytest.mark.parametrize(
        ("identity", "expected"),
        [
            ({"group.id": "dfe-engine"}, "dfe-engine-admin"),
            ({"client.id": "dfe-engine"}, "dfe-engine-admin"),
            ({"group.id": "dfe-engine", "client.id": "engine-pod-3"}, "dfe-engine-admin"),
        ],
    )
    def test_group_id_falls_under_the_granted_prefix(self, identity, expected):
        built = _offset_query_consumer_config({"bootstrap.servers": _NO_BROKER, **identity}, verify_ssl=True)
        assert built["group.id"] == expected
        assert built["group.id"].startswith(_GRANTED_PREFIX)

    def test_callers_own_group_is_the_anchor_not_the_id(self):
        # The caller's group belongs to its real consumers; the offset-query consumer stays out of it.
        built = _offset_query_consumer_config({"group.id": "dfe-engine"}, verify_ssl=True)
        assert built["group.id"] != "dfe-engine"

    def test_inherits_the_callers_auth_and_consumer_defaults(self):
        user_config = {
            "bootstrap.servers": _NO_BROKER,
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "SCRAM-SHA-512",
            "sasl.username": "svc-engine",
            "sasl.password": "not-a-real-password",
            "client.id": "dfe-engine",
        }
        built = _offset_query_consumer_config(user_config, verify_ssl=True)
        assert built["security.protocol"] == "SASL_SSL"
        assert built["sasl.username"] == "svc-engine"
        assert built["enable.auto.commit"] is False
        assert "enable.ssl.certificate.verification" not in built

    def test_verify_ssl_false_disables_verification(self):
        built = _offset_query_consumer_config({"client.id": "dfe-engine"}, verify_ssl=False)
        assert built["enable.ssl.certificate.verification"] == "false"

    def test_leaves_the_callers_config_untouched(self):
        user_config = {"bootstrap.servers": _NO_BROKER, "group.id": "dfe-engine"}
        _offset_query_consumer_config(user_config, verify_ssl=True)
        assert user_config == {"bootstrap.servers": _NO_BROKER, "group.id": "dfe-engine"}

    def test_librdkafka_builds_a_consumer_from_it(self):
        consumer = Consumer(_offset_query_consumer_config({"bootstrap.servers": _NO_BROKER}, verify_ssl=True))
        consumer.close()


class TestClientsKeepTheCallersIdentity:
    """Each client hands the config it was given to the offset-query consumer."""

    @pytest.mark.parametrize("client_class", [KafkaClient, AsyncKafkaClient, ReadOnlyKafkaClient])
    def test_offset_query_group_derives_from_the_client_config(self, client_class):
        client = client_class({"bootstrap.servers": _NO_BROKER, "client.id": "dfe-engine"})
        built = _offset_query_consumer_config(client._user_config, client._verify_ssl)
        assert built["group.id"] == "dfe-engine-admin"


def _is_group_id_key(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "group.id"


def _group_id_values(tree: ast.Module) -> list[ast.expr]:
    """Return every expression the module writes to a ``group.id`` key."""
    values: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            subscripts = [target for target in node.targets if isinstance(target, ast.Subscript)]
            values.extend(node.value for target in subscripts if _is_group_id_key(target.slice))
        elif isinstance(node, ast.Dict):
            pairs = zip(node.keys, node.values, strict=True)
            values.extend(value for key, value in pairs if key is not None and _is_group_id_key(key))
    return values


def test_no_group_id_in_the_kafka_package_is_a_literal():
    # Catches the removed scalo-offset-lookup-*, scalo-watermark-*, scalo-async-*,
    # scalo-async-wm-* and scalo-readonly-* ids, and any literal added after them.
    package_dir = Path(scalo.kafka.__file__).parent
    values_seen = 0
    for source in sorted(package_dir.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for value in _group_id_values(tree):
            values_seen += 1
            assert not isinstance(value, ast.Constant | ast.JoinedStr), (
                f"{source.name}:{value.lineno} sets group.id to a literal the broker's group ACLs may refuse"
            )
    # The consumer, admin and lag paths set a caller-named group, so an empty scan is a broken scan.
    assert values_seen
