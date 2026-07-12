# Project:   scalo
# File:      src/scalo/kafka/toolconfig.py
# Purpose:   Kafka tool config emission - given a provider + connection, emit
#            ready-to-use config for kafbat-ui / kcat / librdkafka .properties.
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tool config emission: "you are running provider X in way Y, here is the
config for tool Z".

A control-plane feature (not on the hot data path) - given a provider key and
a live ``Connection``, emit ready-to-use config for whichever Kafka tool is
pointed at it: a kafbat-ui cluster config, a kcat ``-F`` config file, or a
plain librdkafka ``.properties`` file. One source of provider auth truth
(``scalo.kafka.providers.derive``), many targets.

Every emitter runs ``validate()`` on the derived auth first and refuses a
broken combination rather than emit it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .providers import KnownProvider, SchemaRegistry, derive, validate


@dataclass
class Connection:
    """A live Kafka connection's runtime details - what an emitter needs to
    wire up a tool config. Provider identity is a separate argument
    (``provider_key``), not part of this dataclass.
    """

    bootstrap_servers: str
    username: str = ""
    password: str = ""
    schema_registry_url: str = ""


def _validated_auth(provider_key: str) -> tuple[str, str]:
    """Derive + validate a provider's auth shape; refuse a broken combo."""
    proto, mech = derive(provider_key)
    validate(security_protocol=proto, sasl_mechanism=mech)
    return proto, mech


def emit_librdkafka_properties(provider_key: str, conn: Connection) -> str:
    """Emit a librdkafka ``.properties`` file body for ``provider_key``.

    Used by any librdkafka-based tool that reads ``key=value`` lines.
    Plaintext providers emit bootstrap.servers + security.protocol only (no
    sasl.* keys).
    """
    proto, mech = _validated_auth(provider_key)
    lines = [
        f"bootstrap.servers={conn.bootstrap_servers}",
        f"security.protocol={proto}",
    ]
    if mech:
        lines.append(f"sasl.mechanisms={mech}")
        lines.append(f"sasl.username={conn.username}")
        lines.append(f"sasl.password={conn.password}")
    return "\n".join(lines) + "\n"


def emit_kcat(provider_key: str, conn: Connection) -> str:
    """Emit a kcat ``-F`` config file body for ``provider_key``.

    kcat reads the same librdkafka ``key=value`` lines via ``-F <file>``, so
    this is the same body as ``emit_librdkafka_properties``.
    """
    return emit_librdkafka_properties(provider_key, conn)


def emit_kafbat_cluster(provider_key: str, conn: Connection) -> dict[str, Any]:
    """Emit a kafbat-ui cluster config dict for ``provider_key``.

    ``sasl.jaas.config`` is built per mechanism (SCRAM -> ScramLoginModule,
    PLAIN -> PlainLoginModule); a plaintext provider omits the
    security/sasl keys from ``properties`` entirely. ``schemaRegistry`` is
    included only when the provider ships a registry AND
    ``conn.schema_registry_url`` is set.
    """
    proto, mech = _validated_auth(provider_key)
    provider = KnownProvider.parse(provider_key)

    properties: dict[str, str] = {}
    if mech:
        properties["security.protocol"] = proto
        properties["sasl.mechanism"] = mech
        properties["sasl.jaas.config"] = _jaas_config(mech, conn.username, conn.password)

    cluster: dict[str, Any] = {
        "name": provider_key,
        "bootstrapServers": conn.bootstrap_servers,
        "properties": properties,
    }
    if provider.schema_registry() != SchemaRegistry.NONE and conn.schema_registry_url:
        cluster["schemaRegistry"] = conn.schema_registry_url

    return cluster


def _jaas_config(mechanism: str, username: str, password: str) -> str:
    """Build the ``sasl.jaas.config`` line for a SCRAM or PLAIN mechanism."""
    if mechanism.startswith("SCRAM"):
        module = "org.apache.kafka.common.security.scram.ScramLoginModule"
    elif mechanism == "PLAIN":
        module = "org.apache.kafka.common.security.plain.PlainLoginModule"
    else:
        raise ValueError(
            f"no JAAS module known for sasl mechanism {mechanism!r} "
            "(IAM-family mechanisms need their own callback handler, not JAAS)"
        )
    return f'{module} required username="{username}" password="{password}";'
