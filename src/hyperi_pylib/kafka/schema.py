# Project:   hyperi-pylib
# File:      src/hyperi_pylib/kafka/schema.py
# Purpose:   JSON schema inference for Kafka messages
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
JSON schema inference for Kafka messages.

Uses GenSON to infer JSON schemas from message samples,
with additional field statistics tracking.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from genson import SchemaBuilder

from .types import Message


@dataclass
class FieldStats:
    """Statistics for a single field."""

    types: set[str] = field(default_factory=set)
    null_count: int = 0
    sample_values: list[Any] = field(default_factory=list)
    count: int = 0


@dataclass
class AnalysisResult:
    """Result of schema analysis."""

    total_messages: int
    skipped_messages: int
    schema: dict[str, Any]
    field_stats: dict[str, dict[str, Any]]


class SchemaAnalyser:
    """
    JSON schema inference for Kafka messages.

    Uses GenSON to build a merged JSON schema from message samples,
    and tracks additional field statistics.

    Example:
        analyser = SchemaAnalyser()
        for msg in messages:
            analyser.add_message(msg)
        result = analyser.analyse()
        print(result.schema)
        print(result.field_stats)
    """

    MAX_SAMPLE_VALUES = 5

    def __init__(self):
        self._builder = SchemaBuilder()
        self._field_stats: dict[str, FieldStats] = defaultdict(FieldStats)
        self._message_count = 0
        self._skipped_count = 0

    @property
    def message_count(self) -> int:
        """Number of successfully processed messages."""
        return self._message_count

    @property
    def skipped_count(self) -> int:
        """Number of skipped (non-JSON) messages."""
        return self._skipped_count

    def add_message(self, msg: Message) -> bool:
        """
        Add a message to the analysis.

        Args:
            msg: Kafka message with JSON value

        Returns:
            True if message was processed, False if skipped
        """
        data = msg.value_as_json()
        if data is None:
            self._skipped_count += 1
            return False

        # Add to schema builder
        self._builder.add_object(data)
        self._message_count += 1

        # Track field stats (only for dict/object types)
        if isinstance(data, dict):
            self._track_field_stats(data)

        return True

    def _track_field_stats(self, data: dict[str, Any], prefix: str = "") -> None:
        """Track statistics for each field."""
        for key, value in data.items():
            field_name = f"{prefix}{key}" if prefix else key
            stats = self._field_stats[field_name]
            stats.count += 1

            # Track type
            if value is None:
                stats.null_count += 1
                stats.types.add("null")
            elif isinstance(value, bool):
                stats.types.add("boolean")
            elif isinstance(value, int):
                stats.types.add("integer")
            elif isinstance(value, float):
                stats.types.add("number")
            elif isinstance(value, str):
                stats.types.add("string")
            elif isinstance(value, list):
                stats.types.add("array")
            elif isinstance(value, dict):
                stats.types.add("object")
                # Recursively track nested fields
                self._track_field_stats(value, f"{field_name}.")

            # Track sample values (non-null, non-complex)
            if (
                value is not None
                and not isinstance(value, (dict, list))
                and len(stats.sample_values) < self.MAX_SAMPLE_VALUES
                and value not in stats.sample_values
            ):
                stats.sample_values.append(value)

    def get_schema(self) -> dict[str, Any]:
        """
        Get the merged JSON schema.

        Returns:
            JSON Schema dict
        """
        return self._builder.to_schema()

    def get_field_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get field statistics.

        Returns:
            Dict of field_name -> stats dict
        """
        return {
            name: {
                "types": list(stats.types),
                "null_count": stats.null_count,
                "sample_values": stats.sample_values,
                "count": stats.count,
            }
            for name, stats in self._field_stats.items()
        }

    def analyse(self) -> AnalysisResult:
        """
        Get complete analysis result.

        Returns:
            AnalysisResult with schema and stats
        """
        return AnalysisResult(
            total_messages=self._message_count,
            skipped_messages=self._skipped_count,
            schema=self.get_schema(),
            field_stats=self.get_field_stats(),
        )
