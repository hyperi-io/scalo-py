# Project:   hs-pylib
# File:      src/hs_pylib/kafka/health.py
# Purpose:   Kafka consumer health monitoring with rate-limited warnings
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Kafka consumer health monitoring.

Detects common Kafka consumer issues and logs rate-limited warnings.
Also exposes health metrics for Prometheus/OTEL.

Common issues detected:
- No partitions assigned (consumer idle)
- Insufficient partitions (fewer partitions than consumers)
- Frequent rebalances (instability)
- Consumer lag growing (can't keep up with producers)
- Partition imbalance (uneven load distribution)
- Fetch errors (connection or auth issues)

Configuration (via hs_pylib.config cascade):
    kafka:
      health:
        warning_rate_limit_sec: 60    # Seconds between identical warnings
        lag_threshold: 10000          # Consumer lag warning threshold
        lag_growth_threshold: 1000    # Lag growth rate threshold
        rebalance_threshold: 3        # Max rebalances in window
        rebalance_window_sec: 300     # Rebalance counting window
        imbalance_ratio: 3.0          # Partition imbalance ratio

    Or via environment variables:
        KAFKA_HEALTH_WARNING_RATE_LIMIT_SEC=60
        KAFKA_HEALTH_LAG_THRESHOLD=10000

Usage:
    from hs_pylib.kafka.health import KafkaConsumerHealth
    from hs_pylib.kafka.metrics import KafkaMetricsCollector, create_stats_callback

    collector = KafkaMetricsCollector()
    health = KafkaConsumerHealth(collector, consumer_count=3)

    # Configure consumer with stats callback
    config = {
        "bootstrap.servers": "localhost:9092",
        "statistics.interval.ms": 5000,
        "stats_cb": create_stats_callback(collector),
    }

    # Periodically check health (e.g., after each stats update)
    issues = health.check_health()
    # Issues are logged automatically with rate limiting

    # Get health metrics for Prometheus
    metrics = health.get_health_metrics()

Sources:
- https://www.meshiq.com/blog/common-kafka-performance-issues-and-how-to-fix-them/
- https://www.redpanda.com/guides/kafka-performance-kafka-lag
- https://www.confluent.io/blog/debug-apache-kafka-pt-3/
- https://risingwave.com/blog/fixing-kafka-rebalancing-a-step-by-step-guide/
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from hs_pylib import logger

if TYPE_CHECKING:
    from .metrics import KafkaMetricsCollector


def _get_health_config() -> dict:
    """
    Get Kafka health configuration from config cascade.

    Priority: ENV > .env > settings.yaml > defaults

    Returns:
        Dict with health configuration values
    """
    try:
        from hs_pylib.config import settings

        health_config = settings.get("kafka.health", {})
        if hasattr(health_config, "to_dict"):
            health_config = health_config.to_dict()
        elif not isinstance(health_config, dict):
            health_config = {}
    except Exception:
        health_config = {}

    # Support direct KAFKA_HEALTH_* environment variables
    def _get_env_int(key: str, default: int) -> int:
        val = os.getenv(f"KAFKA_HEALTH_{key.upper()}")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return health_config.get(key, default)

    def _get_env_float(key: str, default: float) -> float:
        val = os.getenv(f"KAFKA_HEALTH_{key.upper()}")
        if val:
            try:
                return float(val)
            except ValueError:
                pass
        return health_config.get(key, default)

    return {
        "warning_rate_limit_sec": _get_env_int("warning_rate_limit_sec", 60),
        "lag_threshold": _get_env_int("lag_threshold", 10000),
        "lag_growth_threshold": _get_env_int("lag_growth_threshold", 1000),
        "rebalance_threshold": _get_env_int("rebalance_threshold", 3),
        "rebalance_window_sec": _get_env_int("rebalance_window_sec", 300),
        "imbalance_ratio": _get_env_float("imbalance_ratio", 3.0),
    }


class HealthIssue(Enum):
    """Kafka consumer health issues."""

    NO_PARTITIONS = "no_partitions_assigned"
    INSUFFICIENT_PARTITIONS = "insufficient_partitions"
    FREQUENT_REBALANCES = "frequent_rebalances"
    LAG_GROWING = "consumer_lag_growing"
    PARTITION_IMBALANCE = "partition_imbalance"
    FETCH_ERRORS = "fetch_errors"
    BROKER_DISCONNECTED = "broker_disconnected"
    HIGH_LAG = "high_consumer_lag"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    issue: HealthIssue
    severity: str  # "warning" or "critical"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class KafkaConsumerHealth:
    """
    Monitors Kafka consumer health and logs rate-limited warnings.

    Detects common issues by analysing librdkafka statistics and
    consumer group state. Warnings are rate-limited to prevent
    log spam during persistent issues.

    Configuration is read from the hs_pylib.config cascade:
        kafka.health.warning_rate_limit_sec (ENV: KAFKA_HEALTH_WARNING_RATE_LIMIT_SEC)
        kafka.health.lag_threshold (ENV: KAFKA_HEALTH_LAG_THRESHOLD)
        kafka.health.lag_growth_threshold (ENV: KAFKA_HEALTH_LAG_GROWTH_THRESHOLD)
        kafka.health.rebalance_threshold (ENV: KAFKA_HEALTH_REBALANCE_THRESHOLD)
        kafka.health.rebalance_window_sec (ENV: KAFKA_HEALTH_REBALANCE_WINDOW_SEC)
        kafka.health.imbalance_ratio (ENV: KAFKA_HEALTH_IMBALANCE_RATIO)

    Args:
        collector: KafkaMetricsCollector to get stats from
        consumer_count: Number of consumers in the group (for partition ratio)
        warning_rate_limit_sec: Override seconds between identical warnings (default: from config, 60)
        lag_threshold: Override consumer lag threshold (default: from config, 10000)
        lag_growth_threshold: Override lag growth rate threshold (default: from config, 1000)
        rebalance_threshold: Override max rebalances in window (default: from config, 3)
        rebalance_window_sec: Override rebalance counting window (default: from config, 300)
        imbalance_ratio: Override partition imbalance ratio (default: from config, 3.0)

    Example:
        # Use config cascade defaults
        health = KafkaConsumerHealth.from_config(collector, consumer_count=3)

        # Or override specific values
        health = KafkaConsumerHealth(collector, consumer_count=3, warning_rate_limit_sec=120)
    """

    collector: KafkaMetricsCollector
    consumer_count: int = 1
    warning_rate_limit_sec: int | None = None
    lag_threshold: int | None = None
    lag_growth_threshold: int | None = None
    rebalance_threshold: int | None = None
    rebalance_window_sec: int | None = None
    imbalance_ratio: float | None = None

    # Internal state (not configurable)
    _last_warnings: dict[HealthIssue, float] = field(default_factory=dict, init=False)
    _rebalance_times: deque = field(default_factory=lambda: deque(maxlen=20), init=False)
    _last_rebalance_cnt: int = field(default=0, init=False)
    _last_lag: dict[str, dict[int, int]] = field(default_factory=dict, init=False)
    _last_check_time: float = field(default=0, init=False)
    _config: dict = field(default_factory=dict, init=False, repr=False)

    # Metrics counters
    _issues_detected: dict[HealthIssue, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Apply config cascade defaults for any None values."""
        self._config = _get_health_config()

        # Apply defaults from config cascade if not explicitly set
        if self.warning_rate_limit_sec is None:
            self.warning_rate_limit_sec = self._config["warning_rate_limit_sec"]
        if self.lag_threshold is None:
            self.lag_threshold = self._config["lag_threshold"]
        if self.lag_growth_threshold is None:
            self.lag_growth_threshold = self._config["lag_growth_threshold"]
        if self.rebalance_threshold is None:
            self.rebalance_threshold = self._config["rebalance_threshold"]
        if self.rebalance_window_sec is None:
            self.rebalance_window_sec = self._config["rebalance_window_sec"]
        if self.imbalance_ratio is None:
            self.imbalance_ratio = self._config["imbalance_ratio"]

    @classmethod
    def from_config(
        cls,
        collector: KafkaMetricsCollector,
        consumer_count: int = 1,
    ) -> KafkaConsumerHealth:
        """
        Create a KafkaConsumerHealth using config cascade defaults.

        All thresholds are read from the config cascade:
        - settings.yaml: kafka.health.*
        - Environment: KAFKA_HEALTH_*

        Args:
            collector: KafkaMetricsCollector to get stats from
            consumer_count: Number of consumers in the group

        Returns:
            KafkaConsumerHealth with config cascade defaults
        """
        return cls(collector=collector, consumer_count=consumer_count)

    def check_health(self) -> list[HealthCheckResult]:
        """
        Check consumer health and log rate-limited warnings.

        Returns:
            List of detected health issues

        Side effects:
            - Logs warnings for detected issues (rate-limited)
            - Updates internal metrics counters
        """
        issues: list[HealthCheckResult] = []
        now = time.time()
        self._last_check_time = now

        # Get current stats
        cgrp = self.collector.get_cgrp_metrics()
        partitions = self.collector.get_partition_metrics()
        brokers = self.collector.get_broker_metrics()
        lag = self.collector.get_consumer_lag()

        # Check each issue type
        issues.extend(self._check_no_partitions(cgrp))
        issues.extend(self._check_insufficient_partitions(partitions))
        issues.extend(self._check_frequent_rebalances(cgrp, now))
        issues.extend(self._check_lag_growing(lag, now))
        issues.extend(self._check_high_lag(lag))
        issues.extend(self._check_partition_imbalance(partitions))
        issues.extend(self._check_broker_issues(brokers))

        # Log issues with rate limiting
        for issue in issues:
            self._log_issue(issue, now)

        return issues

    def _check_no_partitions(self, cgrp: dict) -> list[HealthCheckResult]:
        """Check if consumer has no partitions assigned."""
        issues: list[HealthCheckResult] = []
        assignment_size = cgrp.get("assignment_size", 0)
        state = cgrp.get("state", "")

        # Only warn if state indicates we should have partitions
        if assignment_size == 0 and state in ("up", "steady"):
            issues.append(
                HealthCheckResult(
                    issue=HealthIssue.NO_PARTITIONS,
                    severity="critical",
                    message="Consumer has no partitions assigned - no data will be consumed",
                    details={"state": state, "assignment_size": assignment_size},
                )
            )

        return issues

    def _check_insufficient_partitions(self, partitions: dict) -> list[HealthCheckResult]:
        """Check if there are fewer partitions than consumers."""
        issues: list[HealthCheckResult] = []

        # Count total partitions across all topics
        total_partitions = sum(len(parts) for parts in partitions.values())

        if total_partitions > 0 and total_partitions < self.consumer_count:
            issues.append(
                HealthCheckResult(
                    issue=HealthIssue.INSUFFICIENT_PARTITIONS,
                    severity="warning",
                    message=(
                        f"Fewer partitions ({total_partitions}) than consumers ({self.consumer_count}) - "
                        f"some consumers will be idle"
                    ),
                    details={
                        "total_partitions": total_partitions,
                        "consumer_count": self.consumer_count,
                        "idle_consumers": self.consumer_count - total_partitions,
                    },
                )
            )

        return issues

    def _check_frequent_rebalances(self, cgrp: dict, now: float) -> list[HealthCheckResult]:
        """Check for frequent consumer group rebalances."""
        issues: list[HealthCheckResult] = []

        rebalance_cnt = cgrp.get("rebalance_cnt", 0)

        # Detect new rebalance
        if rebalance_cnt > self._last_rebalance_cnt:
            self._rebalance_times.append(now)
            self._last_rebalance_cnt = rebalance_cnt

        # Count rebalances in window
        window_start = now - self.rebalance_window_sec
        recent_rebalances = sum(1 for t in self._rebalance_times if t >= window_start)

        if recent_rebalances >= self.rebalance_threshold:
            issues.append(
                HealthCheckResult(
                    issue=HealthIssue.FREQUENT_REBALANCES,
                    severity="warning",
                    message=(
                        f"Frequent rebalances detected: {recent_rebalances} in last "
                        f"{self.rebalance_window_sec}s - causes processing delays"
                    ),
                    details={
                        "rebalances_in_window": recent_rebalances,
                        "window_seconds": self.rebalance_window_sec,
                        "rebalance_reason": cgrp.get("rebalance_reason", ""),
                        "total_rebalances": rebalance_cnt,
                    },
                )
            )

        return issues

    def _check_lag_growing(self, lag: dict, now: float) -> list[HealthCheckResult]:
        """Check if consumer lag is growing over time."""
        issues: list[HealthCheckResult] = []

        # Calculate lag growth per topic/partition
        for topic, partitions in lag.items():
            for partition, current_lag in partitions.items():
                if current_lag < 0:  # -1 means unknown
                    continue

                # Get previous lag
                prev_lag = self._last_lag.get(topic, {}).get(partition, current_lag)

                # Check if lag is growing significantly
                lag_growth = current_lag - prev_lag
                if lag_growth >= self.lag_growth_threshold:
                    issues.append(
                        HealthCheckResult(
                            issue=HealthIssue.LAG_GROWING,
                            severity="warning",
                            message=(
                                f"Consumer lag growing on {topic}[{partition}]: "
                                f"+{lag_growth} (now {current_lag}) - consumer can't keep up"
                            ),
                            details={
                                "topic": topic,
                                "partition": partition,
                                "current_lag": current_lag,
                                "previous_lag": prev_lag,
                                "lag_growth": lag_growth,
                            },
                        )
                    )

        # Update last lag for next check
        self._last_lag = {topic: dict(parts) for topic, parts in lag.items()}

        return issues

    def _check_high_lag(self, lag: dict) -> list[HealthCheckResult]:
        """Check if consumer lag exceeds threshold."""
        issues: list[HealthCheckResult] = []

        for topic, partitions in lag.items():
            for partition, current_lag in partitions.items():
                if current_lag >= self.lag_threshold:
                    issues.append(
                        HealthCheckResult(
                            issue=HealthIssue.HIGH_LAG,
                            severity="warning",
                            message=(
                                f"High consumer lag on {topic}[{partition}]: {current_lag} "
                                f"(threshold: {self.lag_threshold})"
                            ),
                            details={
                                "topic": topic,
                                "partition": partition,
                                "lag": current_lag,
                                "threshold": self.lag_threshold,
                            },
                        )
                    )

        return issues

    def _check_partition_imbalance(self, partitions: dict) -> list[HealthCheckResult]:
        """Check for uneven partition distribution."""
        issues: list[HealthCheckResult] = []

        if not partitions:
            return issues

        # This check is more relevant for the whole consumer group
        # Here we can only detect if THIS consumer has many more partitions
        # than expected (suggesting imbalance)
        total_partitions = sum(len(parts) for parts in partitions.values())

        if self.consumer_count > 1 and total_partitions > 0:
            expected_per_consumer = total_partitions / self.consumer_count
            # If this consumer has significantly more than expected
            if total_partitions > expected_per_consumer * self.imbalance_ratio:
                issues.append(
                    HealthCheckResult(
                        issue=HealthIssue.PARTITION_IMBALANCE,
                        severity="warning",
                        message=(
                            f"Partition imbalance: this consumer has {total_partitions} partitions "
                            f"(expected ~{expected_per_consumer:.0f} with {self.consumer_count} consumers)"
                        ),
                        details={
                            "assigned_partitions": total_partitions,
                            "expected_per_consumer": expected_per_consumer,
                            "consumer_count": self.consumer_count,
                        },
                    )
                )

        return issues

    def _check_broker_issues(self, brokers: dict) -> list[HealthCheckResult]:
        """Check for broker connection issues."""
        issues: list[HealthCheckResult] = []

        for broker_name, stats in brokers.items():
            # Skip internal/bootstrap brokers
            if stats.get("nodeid", -1) < 0:
                continue

            state = stats.get("state", "")

            # Check for disconnected brokers
            if state in ("INIT", "DOWN"):
                issues.append(
                    HealthCheckResult(
                        issue=HealthIssue.BROKER_DISCONNECTED,
                        severity="warning",
                        message=f"Broker {broker_name} disconnected (state: {state})",
                        details={
                            "broker": broker_name,
                            "state": state,
                            "disconnects": stats.get("disconnects", 0),
                            "connects": stats.get("connects", 0),
                        },
                    )
                )

            # Check for high error rates
            tx_errs = stats.get("tx_errs", 0)
            rx_errs = stats.get("rx_errs", 0)
            req_timeouts = stats.get("req_timeouts", 0)

            total_errors = tx_errs + rx_errs + req_timeouts
            if total_errors > 0:
                issues.append(
                    HealthCheckResult(
                        issue=HealthIssue.FETCH_ERRORS,
                        severity="warning",
                        message=(f"Broker {broker_name} errors: tx={tx_errs}, rx={rx_errs}, timeouts={req_timeouts}"),
                        details={
                            "broker": broker_name,
                            "tx_errors": tx_errs,
                            "rx_errors": rx_errs,
                            "request_timeouts": req_timeouts,
                        },
                    )
                )

        return issues

    def _log_issue(self, issue: HealthCheckResult, now: float) -> None:
        """Log an issue with rate limiting."""
        last_warn = self._last_warnings.get(issue.issue, 0)

        # Check rate limit
        if now - last_warn < self.warning_rate_limit_sec:
            return

        # Update metrics counter
        self._issues_detected[issue.issue] = self._issues_detected.get(issue.issue, 0) + 1

        # Log the warning with structured data via Loguru's bind
        log_func = logger.logger.error if issue.severity == "critical" else logger.logger.warning
        log_func(issue.message, **issue.details)

        self._last_warnings[issue.issue] = now

    def get_health_metrics(self) -> dict:
        """
        Get health metrics for Prometheus/OTEL.

        Returns:
            Dict of metric name -> value
        """
        cgrp = self.collector.get_cgrp_metrics()
        lag = self.collector.get_consumer_lag()

        # Calculate total lag
        total_lag = sum(sum(parts.values()) for parts in lag.values() if parts)
        total_lag = max(0, total_lag)  # Handle -1 unknown values

        # Count partitions
        partitions = self.collector.get_partition_metrics()
        total_partitions = sum(len(parts) for parts in partitions.values())

        return {
            # Health state
            "kafka_consumer_healthy": 1 if not self._issues_detected else 0,
            "kafka_consumer_issues_total": sum(self._issues_detected.values()),
            # Issue counts by type
            **{f"kafka_consumer_issue_{issue.value}_total": count for issue, count in self._issues_detected.items()},
            # Current state
            "kafka_consumer_partitions_assigned": total_partitions,
            "kafka_consumer_lag_total": total_lag,
            "kafka_consumer_rebalance_total": cgrp.get("rebalance_cnt", 0),
            "kafka_consumer_state": cgrp.get("state", "unknown"),
            # Configuration
            "kafka_consumer_count_expected": self.consumer_count,
        }

    def reset_metrics(self) -> None:
        """Reset issue counters (useful for testing)."""
        self._issues_detected.clear()
        self._last_warnings.clear()
        self._rebalance_times.clear()
        self._last_lag.clear()
