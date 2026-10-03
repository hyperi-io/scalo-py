# Project:   scalo
# File:      src/scalo/kafka/config.py
# Purpose:   Kafka corporate defaults and configuration utilities
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka configuration defaults and utilities.

Uses librdkafka configuration names directly:
https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md

Supports loading configuration from common file formats:
- .properties - Java-style properties (standard Kafka format)
- .json - JSON format
- .yaml / .yml - YAML format
- .ini - INI format with [kafka] section
"""

from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any, Literal

# librdkafka config keys whose VALUES are credentials. Any repr/dump of
# a config dict must replace these with a sentinel before emission.
_CREDENTIAL_KEYS: frozenset[str] = frozenset(
    {
        "sasl.password",
        "sasl.username",
        "ssl.key.password",
        "ssl.keystore.password",
        "ssl.truststore.password",
        "schema.registry.basic.auth.user.info",
        "schema.registry.ssl.key.password",
    }
)


def mask_credentials(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``config`` with credential values masked.

    Use when emitting a Kafka client config to logs, repr, or any
    other surface a human or aggregator might read. The original dict
    is not mutated.
    """
    out: dict[str, Any] = {}
    for k, v in config.items():
        if k in _CREDENTIAL_KEYS and v not in (None, ""):
            out[k] = "***"
        else:
            out[k] = v
    return out


# =============================================================================
# Corporate Defaults
# =============================================================================

PRODUCER_DEFAULTS: dict[str, Any] = {
    # Delivery guarantees (at-least-once)
    "acks": "all",  # Wait for all replicas (ensures durability)
    "retries": 5,  # Retry on transient failures
    "retry.backoff.ms": 100,  # Backoff between retries
    # Timeouts
    "delivery.timeout.ms": 120000,  # 2 minutes max delivery time
    "request.timeout.ms": 30000,  # 30 seconds per request
    # Batching and compression
    "linger.ms": 5,  # Small delay for batching
    "compression.type": "zstd",  # Corporate default -- see merge_config for the level pairing
    "compression.level": 3,  # zstd only; dropped by merge_config if the codec is overridden
    "batch.size": 16384,  # 16KB batch size
}

CONSUMER_DEFAULTS: dict[str, Any] = {
    # Offset management
    "auto.offset.reset": "earliest",  # Start from beginning if no offset
    "enable.auto.commit": False,  # Manual commit for control
    # Session management
    "session.timeout.ms": 45000,  # 45 seconds session timeout
    "heartbeat.interval.ms": 3000,  # 3 seconds heartbeat
    "max.poll.interval.ms": 300000,  # 5 minutes max poll interval
    # Fetch settings
    "fetch.min.bytes": 1,  # Return immediately with any data
    "fetch.wait.max.ms": 500,  # Max wait for fetch.min.bytes (librdkafka naming)
}

ADMIN_DEFAULTS: dict[str, Any] = {
    # Admin client defaults
    "request.timeout.ms": 30000,  # 30 seconds for admin operations
}

# librdkafka accepts each of these settings under either name, the same pairs as scalo-rs's LIBRDKAFKA_ALIASES.
_LIBRDKAFKA_ALIASES: tuple[tuple[str, str], ...] = (
    ("bootstrap.servers", "metadata.broker.list"),
    ("max.in.flight", "max.in.flight.requests.per.connection"),
    ("sasl.mechanism", "sasl.mechanisms"),
    ("sasl.oauthbearer.client.credentials.client.id", "sasl.oauthbearer.client.id"),
    ("sasl.oauthbearer.client.credentials.client.secret", "sasl.oauthbearer.client.secret"),
    ("max.partition.fetch.bytes", "fetch.message.max.bytes"),
    ("linger.ms", "queue.buffering.max.ms"),
    ("retries", "message.send.max.retries"),
    ("compression.type", "compression.codec"),
    ("acks", "request.required.acks"),
)


# =============================================================================
# Configuration Utilities
# =============================================================================


def merge_config(
    user_config: dict[str, Any],
    defaults: dict[str, Any],
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """
    Merge user configuration with defaults.

    User configuration takes precedence over defaults. If verify_ssl is False,
    sets the librdkafka config to disable SSL certificate verification.

    Args:
        user_config: User-provided configuration
        defaults: Default configuration to apply
        verify_ssl: If False, disable SSL certificate verification

    Returns:
        Merged configuration dictionary
    """
    # Start with defaults, then overlay user config
    merged = {**defaults, **user_config}

    # A user setting under one librdkafka name replaces our default under the other rather than racing it.
    for name, alias in _LIBRDKAFKA_ALIASES:
        for ours, theirs in ((name, alias), (alias, name)):
            if theirs in user_config and ours not in user_config and ours in defaults:
                del merged[ours]

    # compression.level=3 only tunes zstd. lz4 treats any level above 0 as
    # its slow high-compression mode, so a codec override without an
    # explicit level must not inherit ours.
    codec = merged.get("compression.type", merged.get("compression.codec"))
    if "compression.level" in defaults and "compression.level" not in user_config and str(codec).lower() != "zstd":
        del merged["compression.level"]

    # Handle SSL verification
    if not verify_ssl:
        merged["enable.ssl.certificate.verification"] = "false"

    return merged


# =============================================================================
# Internal consumer group ids
# =============================================================================

# Anchors scalo's own group ids when a config names neither a group nor a client, as scalo-rs does.
_DEFAULT_CLIENT_ID = "scalo"

# Names the offset-query consumer in its derived group id, the same role scalo-rs's KafkaAdmin uses.
_OFFSET_QUERY_GROUP_ROLE = "admin"


def _internal_group_id(config: dict[str, Any], role: str) -> str:
    """Return the group id for one of scalo's own consumers, ``role`` naming it.

    librdkafka looks up the coordinator for a consumer's ``group.id`` as soon as it
    connects, and a broker that grants groups by prefix refuses any group outside
    the prefix. So the id is ``<group.id>-<role>``, falling back to
    ``<client.id>-<role>`` and, with neither set, ``scalo-<role>``.

    Args:
        config: The caller's librdkafka config.
        role: What the consumer is for, appended to the anchor.

    Returns:
        The derived group id, never empty.
    """
    anchor = config.get("group.id") or config.get("client.id") or _DEFAULT_CLIENT_ID
    return f"{anchor}-{role}"


def _offset_query_consumer_config(user_config: dict[str, Any], verify_ssl: bool) -> dict[str, Any]:
    """Build the config for a consumer that only reads watermarks and offsets.

    The consumer inherits the caller's SASL/SSL settings, never subscribes, assigns
    or commits, and takes a group id derived from ``user_config`` (see
    ``_internal_group_id``).

    Args:
        user_config: The caller's librdkafka config; not modified.
        verify_ssl: If False, disable SSL certificate verification.

    Returns:
        The caller's config over ``CONSUMER_DEFAULTS``, with the derived ``group.id``.
    """
    base_config = user_config.copy()
    base_config["group.id"] = _internal_group_id(user_config, _OFFSET_QUERY_GROUP_ROLE)
    return merge_config(base_config, CONSUMER_DEFAULTS, verify_ssl=verify_ssl)


def config_from_env(prefix: str = "KAFKA_") -> dict[str, Any]:
    """
    Build Kafka configuration from environment variables.

    Reads environment variables and converts them to librdkafka config names.

    Environment variables:
        KAFKA_BOOTSTRAP_SERVERS -> bootstrap.servers
        KAFKA_SECURITY_PROTOCOL -> security.protocol
        KAFKA_SASL_MECHANISM -> sasl.mechanism
        KAFKA_SASL_USERNAME -> sasl.username
        KAFKA_SASL_PASSWORD -> sasl.password
        KAFKA_SSL_ENDPOINT_IDENTIFICATION_ALGORITHM -> ssl.endpoint.identification.algorithm

    Args:
        prefix: Environment variable prefix (default: "KAFKA_")

    Returns:
        Configuration dictionary with librdkafka keys
    """
    # Mapping from env var suffix to librdkafka config name
    env_to_librdkafka = {
        "BOOTSTRAP_SERVERS": "bootstrap.servers",
        "SECURITY_PROTOCOL": "security.protocol",
        "SASL_MECHANISM": "sasl.mechanism",
        "SASL_USERNAME": "sasl.username",
        "SASL_PASSWORD": "sasl.password",
        "SSL_ENDPOINT_IDENTIFICATION_ALGORITHM": "ssl.endpoint.identification.algorithm",
        "CLIENT_ID": "client.id",
        "GROUP_ID": "group.id",
    }

    config: dict[str, Any] = {}

    for env_suffix, librdkafka_key in env_to_librdkafka.items():
        env_var = f"{prefix}{env_suffix}"
        value = os.environ.get(env_var)
        if value is not None:
            config[librdkafka_key] = value

    return config


def get_default_config(verify_ssl: bool = True) -> dict[str, Any]:
    """
    Get default Kafka configuration from environment.

    Combines environment variables with admin defaults.

    Args:
        verify_ssl: If False, disable SSL certificate verification

    Returns:
        Configuration dictionary ready for KafkaClient
    """
    env_config = config_from_env()
    return merge_config(env_config, ADMIN_DEFAULTS, verify_ssl=verify_ssl)


# =============================================================================
# SASL-SCRAM helpers
# =============================================================================
#
# Generic builders for the two common SCRAM shapes: SCRAM over SASL_SSL for
# external brokers that speak SCRAM (self-hosted Apache Kafka, Redpanda, AWS MSK
# provisioned), and SCRAM over SASL_PLAINTEXT for in-cluster brokers where TLS is
# already terminated by the network mesh. They save per-project hand-rolling of
# security.protocol + sasl.* fields.
#
# NOTE: not every managed provider speaks SCRAM - Confluent Cloud is API-key
# PLAIN over TLS, AWS MSK Serverless is IAM-only. For a provider-driven config
# that picks the right mechanism automatically, use scalo.kafka.providers.


def _reject_plain_over_plaintext(security_protocol: str, mechanism: str) -> None:
    """The one hard floor: PLAIN must ride TLS - never send the password in clear."""
    if mechanism == "PLAIN" and security_protocol != "SASL_SSL":
        raise ValueError(
            "SASL PLAIN requires security.protocol=SASL_SSL (never send a PLAIN password over a plaintext transport)"
        )


def external_sasl_scram(
    brokers: str,
    username: str,
    password: str,
    *,
    mechanism: str = "SCRAM-SHA-512",
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """
    Build a Kafka client config for an external broker using SASL_SSL + SCRAM.

    The common shape for internet-facing brokers that speak SCRAM: self-hosted
    Apache Kafka, Redpanda, AWS MSK provisioned. NOT Confluent Cloud (API-key
    PLAIN) or MSK Serverless (IAM) - use scalo.kafka.providers for those.

    Args:
        brokers: Bootstrap servers (e.g. "broker1:9093,broker2:9093")
        username: SASL username
        password: SASL password
        mechanism: SCRAM variant; defaults to ``SCRAM-SHA-512``
        verify_ssl: TLS certificate verification; default True

    Returns:
        Configuration dict ready to merge with PRODUCER/CONSUMER/ADMIN_DEFAULTS

    Example:
        >>> base = external_sasl_scram("kafka.prod:9093", "svc-loader", "***")
        >>> config = merge_config(base, PRODUCER_DEFAULTS)
    """
    _reject_plain_over_plaintext("SASL_SSL", mechanism)
    config: dict[str, Any] = {
        "bootstrap.servers": brokers,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": mechanism,
        "sasl.username": username,
        "sasl.password": password,
    }
    if not verify_ssl:
        config["enable.ssl.certificate.verification"] = "false"
    return config


def internal_sasl_scram(
    brokers: str,
    username: str,
    password: str,
    *,
    mechanism: str = "SCRAM-SHA-512",
) -> dict[str, Any]:
    """
    Build a Kafka client config for an internal broker using SASL_PLAINTEXT + SCRAM.

    Used when TLS is terminated upstream (mTLS service mesh, in-cluster Kafka)
    so wire encryption is already provided by the network layer.

    Args:
        brokers: Bootstrap servers (e.g. "kafka.svc:9092")
        username: SASL username
        password: SASL password
        mechanism: SCRAM variant; defaults to ``SCRAM-SHA-512`` (the strongest
            commonly available mechanism)

    Returns:
        Configuration dict ready to merge with PRODUCER/CONSUMER/ADMIN_DEFAULTS
    """
    _reject_plain_over_plaintext("SASL_PLAINTEXT", mechanism)
    return {
        "bootstrap.servers": brokers,
        "security.protocol": "SASL_PLAINTEXT",
        "sasl.mechanisms": mechanism,
        "sasl.username": username,
        "sasl.password": password,
    }


# =============================================================================
# File-based Configuration
# =============================================================================

ConfigFormat = Literal["properties", "json", "yaml", "ini"]


def config_from_file(
    path: str,
    format: ConfigFormat | None = None,
    section: str = "kafka",
) -> dict[str, Any]:
    """
    Load Kafka configuration from a file.

    Supports common configuration file formats used with Kafka:
    - .properties - Java-style properties (key=value, # comments)
    - .json - JSON format
    - .yaml / .yml - YAML format
    - .ini - INI format (uses [kafka] section by default)

    Args:
        path: Path to configuration file
        format: Explicit format override (auto-detected from extension if None)
        section: INI section name (default: "kafka")

    Returns:
        Configuration dictionary with librdkafka keys

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is unsupported

    Example:
        # Load from properties file (standard Kafka format)
        config = config_from_file("kafka.properties")

        # Load from JSON
        config = config_from_file("kafka.json")

        # Use with KafkaClient
        client = KafkaClient(config_from_file("kafka.properties"))
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    # Determine format from extension if not specified
    if format is None:
        ext = file_path.suffix.lower()
        format_map = {
            ".properties": "properties",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".ini": "ini",
        }
        format = format_map.get(ext)
        if format is None:
            raise ValueError(
                f"Unsupported configuration file extension: {ext}. Supported: .properties, .json, .yaml, .yml, .ini"
            )

    content = file_path.read_text(encoding="utf-8")

    if format == "properties":
        return _parse_properties(content)
    elif format == "json":
        return _parse_json(content)
    elif format == "yaml":
        return _parse_yaml(content)
    elif format == "ini":
        return _parse_ini(content, section)
    else:
        raise ValueError(f"Unsupported format: {format}")


def _parse_properties(content: str) -> dict[str, Any]:
    """
    Parse Java-style properties format.

    Handles:
    - key=value pairs
    - # and ! comments
    - Values containing = signs
    - Empty lines
    """
    config: dict[str, Any] = {}

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#") or line.startswith("!"):
            continue

        # Split on first = only (values may contain =)
        if "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

    return config


def _parse_json(content: str) -> dict[str, Any]:
    """Parse JSON configuration."""
    return json.loads(content)


def _parse_yaml(content: str) -> dict[str, Any]:
    """Parse YAML configuration."""
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required for YAML configuration files. Install with: pip install pyyaml")

    return yaml.safe_load(content) or {}


def _parse_ini(content: str, section: str) -> dict[str, Any]:
    """Parse INI configuration from specified section."""
    parser = configparser.ConfigParser()
    parser.read_string(content)

    if section not in parser:
        raise ValueError(f"Section [{section}] not found in INI file")

    return dict(parser[section])
