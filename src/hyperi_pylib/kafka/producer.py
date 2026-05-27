# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/producer.py
# Purpose:   Kafka producer with corporate defaults
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Kafka producer with corporate defaults.

Provides a high-level producer that wraps confluent-kafka
with sensible defaults for enterprise use.
"""

from __future__ import annotations

import json
from typing import Any

from confluent_kafka import Producer

from .config import PRODUCER_DEFAULTS, merge_config


class KafkaProducer:
    """
    Kafka producer with corporate defaults.

    Wraps confluent-kafka Producer with sensible defaults
    and a simplified API.

    Args:
        config: Either bootstrap.servers string or full config dict
        verify_ssl: If False, disable SSL certificate verification

    Example:
        with KafkaProducer("localhost:9092") as producer:
            producer.send("my-topic", {"event": "user_created", "user_id": 123})
            producer.send("my-topic", "plain text message", key="user-123")
    """

    def __init__(
        self,
        config: str | dict[str, Any],
        verify_ssl: bool = True,
    ):
        # Normalize config to dict
        if isinstance(config, str):
            config = {"bootstrap.servers": config}

        # Merge with defaults
        self._config = merge_config(config, PRODUCER_DEFAULTS, verify_ssl=verify_ssl)

        # Create producer
        self._producer = Producer(self._config)

    def __repr__(self) -> str:
        from .config import mask_credentials

        return f"KafkaProducer(config={mask_credentials(self._config)!r})"

    def __enter__(self) -> KafkaProducer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.flush()

    # =========================================================================
    # Send Messages
    # =========================================================================

    def send(
        self,
        topic: str,
        value: str | bytes | dict | list,
        key: str | bytes | None = None,
        partition: int | None = None,
        headers: dict[str, str] | None = None,
        on_delivery: Any = None,
    ) -> None:
        """
        Send a message to Kafka.

        Args:
            topic: Target topic name
            value: Message value (str, bytes, or JSON-serializable dict/list)
            key: Optional message key
            partition: Optional target partition
            headers: Optional headers dict
            on_delivery: Optional callback(err, msg) for delivery report
        """
        # Serialize value
        if isinstance(value, (dict, list)):
            value_bytes = json.dumps(value).encode("utf-8")
        elif isinstance(value, str):
            value_bytes = value.encode("utf-8")
        else:
            value_bytes = value

        # Serialize key
        key_bytes = None
        if key is not None:
            if isinstance(key, str):
                key_bytes = key.encode("utf-8")
            else:
                key_bytes = key

        # Convert headers
        headers_list = None
        if headers:
            headers_list = [(k, v.encode("utf-8") if isinstance(v, str) else v) for k, v in headers.items()]

        # Build produce kwargs
        kwargs: dict[str, Any] = {
            "topic": topic,
            "value": value_bytes,
        }
        if key_bytes is not None:
            kwargs["key"] = key_bytes
        if partition is not None:
            kwargs["partition"] = partition
        if headers_list is not None:
            kwargs["headers"] = headers_list
        if on_delivery is not None:
            kwargs["on_delivery"] = on_delivery

        # Send
        self._producer.produce(**kwargs)

        # Poll to trigger callbacks (non-blocking)
        self._producer.poll(0)

    # =========================================================================
    # Flush and Poll
    # =========================================================================

    def flush(self, timeout: float | None = None) -> int:
        """
        Wait for all messages to be delivered.

        Args:
            timeout: Maximum wait time in seconds (None = infinite)

        Returns:
            Number of messages still in queue (0 if all delivered)
        """
        if timeout is not None:
            return self._producer.flush(timeout)
        return self._producer.flush()

    def poll(self, timeout: float = 0) -> int:
        """
        Poll for delivery callbacks.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            Number of events processed
        """
        return self._producer.poll(timeout)
