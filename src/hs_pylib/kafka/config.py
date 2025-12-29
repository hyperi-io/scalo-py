# Project:   hs-pylib
# File:      src/hs_pylib/kafka/config.py
# Purpose:   Kafka corporate defaults and configuration utilities
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

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
    "compression.type": "lz4",  # Fast compression
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

    # Handle SSL verification
    if not verify_ssl:
        merged["enable.ssl.certificate.verification"] = "false"

    return merged


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
                f"Unsupported configuration file extension: {ext}. "
                f"Supported: .properties, .json, .yaml, .yml, .ini"
            )

    content = file_path.read_text()

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
        raise ImportError(
            "PyYAML is required for YAML configuration files. "
            "Install with: pip install pyyaml"
        )

    return yaml.safe_load(content) or {}


def _parse_ini(content: str, section: str) -> dict[str, Any]:
    """Parse INI configuration from specified section."""
    parser = configparser.ConfigParser()
    parser.read_string(content)

    if section not in parser:
        raise ValueError(f"Section [{section}] not found in INI file")

    return dict(parser[section])
