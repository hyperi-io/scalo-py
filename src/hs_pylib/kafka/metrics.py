# Project:   hs-pylib
# File:      src/hs_pylib/kafka/metrics.py
# Purpose:   Kafka metrics collection from librdkafka stats
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""
Kafka metrics collection from librdkafka statistics.

Provides a collector for librdkafka statistics JSON and functions
to expose metrics to Prometheus/OTEL.

Usage:
    from hs_pylib.kafka.metrics import KafkaMetricsCollector, create_stats_callback

    collector = KafkaMetricsCollector()
    callback = create_stats_callback(collector)

    # Configure consumer/producer with stats callback
    config = {
        "bootstrap.servers": "localhost:9092",
        "statistics.interval.ms": 5000,  # Collect every 5 seconds
        "stats_cb": callback,
    }

    # Later, get metrics for Prometheus
    metrics = collector.get_metrics()
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class KafkaMetricsCollector:
    """
    Collector for librdkafka statistics.

    Parses librdkafka stats JSON and provides metrics in a format
    suitable for Prometheus/OTEL export.

    Collects ALL available metrics from librdkafka statistics:
    - Client-level: message counts, bytes, queue sizes
    - Broker-level: connection state, errors, latency percentiles
    - Topic-level: batch sizes, metadata age
    - Partition-level: offsets, consumer lag, fetch state
    - Consumer group: state, rebalances, assignment

    Note: Disk usage is NOT available via librdkafka stats (requires JMX).

    Thread-safe - can be used with multiple consumers/producers.

    Reference: https://github.com/confluentinc/librdkafka/blob/master/STATISTICS.md
    """

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _stats: dict[str, Any] = field(default_factory=dict, init=False)
    _broker_stats: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _topic_stats: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _partition_stats: dict[str, dict[int, dict[str, Any]]] = field(
        default_factory=dict, init=False
    )
    _cgrp_stats: dict[str, Any] = field(default_factory=dict, init=False)
    _eos_stats: dict[str, Any] = field(default_factory=dict, init=False)
    _consumer_lag: dict[str, dict[int, int]] = field(default_factory=dict, init=False)

    def update_from_stats(self, stats_json: str) -> None:
        """
        Update metrics from librdkafka stats JSON.

        Captures ALL available metrics from librdkafka statistics callback.
        See: https://github.com/confluentinc/librdkafka/blob/master/STATISTICS.md

        Args:
            stats_json: Raw JSON string from librdkafka stats callback
        """
        try:
            stats = json.loads(stats_json)
        except json.JSONDecodeError:
            return

        with self._lock:
            # Top-level stats (full set)
            self._stats = {
                "name": stats.get("name", ""),
                "client_id": stats.get("client_id", ""),
                "type": stats.get("type", ""),
                "ts": stats.get("ts", 0),
                "time": stats.get("time", 0),
                "age": stats.get("age", 0),
                "replyq": stats.get("replyq", 0),
                "msg_cnt": stats.get("msg_cnt", 0),
                "msg_size": stats.get("msg_size", 0),
                "msg_max": stats.get("msg_max", 0),
                "msg_size_max": stats.get("msg_size_max", 0),
                "simple_cnt": stats.get("simple_cnt", 0),
                "metadata_cache_cnt": stats.get("metadata_cache_cnt", 0),
                # Transfer totals
                "tx": stats.get("tx", 0),
                "tx_bytes": stats.get("tx_bytes", 0),
                "rx": stats.get("rx", 0),
                "rx_bytes": stats.get("rx_bytes", 0),
                "txmsgs": stats.get("txmsgs", 0),
                "txmsg_bytes": stats.get("txmsg_bytes", 0),
                "rxmsgs": stats.get("rxmsgs", 0),
                "rxmsg_bytes": stats.get("rxmsg_bytes", 0),
            }

            # Broker stats (full set with all latency windows)
            if "brokers" in stats:
                for broker_name, broker in stats["brokers"].items():
                    broker_metrics = {
                        # Identity
                        "nodeid": broker.get("nodeid", -1),
                        "nodename": broker.get("nodename", ""),
                        "source": broker.get("source", ""),
                        "state": broker.get("state", "UNKNOWN"),
                        "stateage_us": broker.get("stateage", 0),
                        # Queue metrics
                        "outbuf_cnt": broker.get("outbuf_cnt", 0),
                        "outbuf_msg_cnt": broker.get("outbuf_msg_cnt", 0),
                        "waitresp_cnt": broker.get("waitresp_cnt", 0),
                        "waitresp_msg_cnt": broker.get("waitresp_msg_cnt", 0),
                        # Transfer counters
                        "tx": broker.get("tx", 0),
                        "tx_bytes": broker.get("txbytes", 0),
                        "tx_errs": broker.get("txerrs", 0),
                        "tx_retries": broker.get("txretries", 0),
                        "tx_idle_us": broker.get("txidle", 0),
                        "rx": broker.get("rx", 0),
                        "rx_bytes": broker.get("rxbytes", 0),
                        "rx_errs": broker.get("rxerrs", 0),
                        "rx_corriderrs": broker.get("rxcorriderrs", 0),
                        "rx_partial": broker.get("rxpartial", 0),
                        "rx_idle_us": broker.get("rxidle", 0),
                        # Error tracking (CRITICAL for operations)
                        "req_timeouts": broker.get("req_timeouts", 0),
                        "zbuf_grow": broker.get("zbuf_grow", 0),
                        # Connection health
                        "connects": broker.get("connects", 0),
                        "disconnects": broker.get("disconnects", 0),
                        "wakeups": broker.get("wakeups", 0),
                    }

                    # RTT latency window (full percentiles)
                    if "rtt" in broker:
                        rtt = broker["rtt"]
                        broker_metrics.update({
                            "rtt_min_us": rtt.get("min", 0),
                            "rtt_max_us": rtt.get("max", 0),
                            "rtt_avg_us": rtt.get("avg", 0),
                            "rtt_sum_us": rtt.get("sum", 0),
                            "rtt_cnt": rtt.get("cnt", 0),
                            "rtt_stddev_us": rtt.get("stddev", 0),
                            "rtt_p50_us": rtt.get("p50", 0),
                            "rtt_p75_us": rtt.get("p75", 0),
                            "rtt_p90_us": rtt.get("p90", 0),
                            "rtt_p95_us": rtt.get("p95", 0),
                            "rtt_p99_us": rtt.get("p99", 0),
                            "rtt_p99_99_us": rtt.get("p99_99", 0),
                        })

                    # Throttle latency window
                    if "throttle" in broker:
                        throttle = broker["throttle"]
                        broker_metrics.update({
                            "throttle_min_ms": throttle.get("min", 0),
                            "throttle_max_ms": throttle.get("max", 0),
                            "throttle_avg_ms": throttle.get("avg", 0),
                            "throttle_sum_ms": throttle.get("sum", 0),
                            "throttle_cnt": throttle.get("cnt", 0),
                            "throttle_p99_ms": throttle.get("p99", 0),
                        })

                    # Internal latency (time from produce() to broker send)
                    if "int_latency" in broker:
                        il = broker["int_latency"]
                        broker_metrics.update({
                            "int_latency_min_us": il.get("min", 0),
                            "int_latency_max_us": il.get("max", 0),
                            "int_latency_avg_us": il.get("avg", 0),
                            "int_latency_p99_us": il.get("p99", 0),
                        })

                    # Outbuf latency (time in output buffer)
                    if "outbuf_latency" in broker:
                        ol = broker["outbuf_latency"]
                        broker_metrics.update({
                            "outbuf_latency_min_us": ol.get("min", 0),
                            "outbuf_latency_max_us": ol.get("max", 0),
                            "outbuf_latency_avg_us": ol.get("avg", 0),
                            "outbuf_latency_p99_us": ol.get("p99", 0),
                        })

                    self._broker_stats[broker_name] = broker_metrics

            # Topic stats (full set)
            if "topics" in stats:
                for topic_name, topic in stats["topics"].items():
                    topic_metrics = {
                        "age_ms": topic.get("age", 0),
                        "metadata_age_ms": topic.get("metadata_age", 0),
                    }

                    # Batch size window stats
                    if "batchsize" in topic:
                        bs = topic["batchsize"]
                        topic_metrics.update({
                            "batchsize_min": bs.get("min", 0),
                            "batchsize_max": bs.get("max", 0),
                            "batchsize_avg": bs.get("avg", 0),
                            "batchsize_sum": bs.get("sum", 0),
                            "batchsize_cnt": bs.get("cnt", 0),
                            "batchsize_p99": bs.get("p99", 0),
                        })

                    # Batch count window stats
                    if "batchcnt" in topic:
                        bc = topic["batchcnt"]
                        topic_metrics.update({
                            "batchcnt_min": bc.get("min", 0),
                            "batchcnt_max": bc.get("max", 0),
                            "batchcnt_avg": bc.get("avg", 0),
                            "batchcnt_sum": bc.get("sum", 0),
                            "batchcnt_cnt": bc.get("cnt", 0),
                        })

                    self._topic_stats[topic_name] = topic_metrics

                    # Partition stats (FULL per-partition metrics)
                    if "partitions" in topic:
                        if topic_name not in self._consumer_lag:
                            self._consumer_lag[topic_name] = {}
                        if topic_name not in self._partition_stats:
                            self._partition_stats[topic_name] = {}

                        for part_id_str, part in topic["partitions"].items():
                            part_id = int(part_id_str)
                            if part_id < 0:  # Skip -1 (UA partition)
                                continue

                            # Consumer lag
                            self._consumer_lag[topic_name][part_id] = part.get(
                                "consumer_lag", 0
                            )

                            # Full partition stats
                            self._partition_stats[topic_name][part_id] = {
                                # Identity
                                "broker": part.get("broker", -1),
                                "leader": part.get("leader", -1),
                                "desired": part.get("desired", False),
                                "unknown": part.get("unknown", False),
                                # Queue depths (CRITICAL for monitoring)
                                "msgq_cnt": part.get("msgq_cnt", 0),
                                "msgq_bytes": part.get("msgq_bytes", 0),
                                "xmit_msgq_cnt": part.get("xmit_msgq_cnt", 0),
                                "xmit_msgq_bytes": part.get("xmit_msgq_bytes", 0),
                                "fetchq_cnt": part.get("fetchq_cnt", 0),
                                "fetchq_size": part.get("fetchq_size", 0),
                                # Consumer state (CRITICAL for operations)
                                "fetch_state": part.get("fetch_state", "none"),
                                "query_offset": part.get("query_offset", -1),
                                "next_offset": part.get("next_offset", -1),
                                "app_offset": part.get("app_offset", -1),
                                "stored_offset": part.get("stored_offset", -1),
                                "committed_offset": part.get("committed_offset", -1),
                                "eof_offset": part.get("eof_offset", -1),
                                # Watermarks (CRITICAL for lag calculation)
                                "lo_offset": part.get("lo_offset", -1),
                                "hi_offset": part.get("hi_offset", -1),
                                "ls_offset": part.get("ls_offset", -1),
                                # Lag metrics
                                "consumer_lag": part.get("consumer_lag", -1),
                                "consumer_lag_stored": part.get(
                                    "consumer_lag_stored", -1
                                ),
                                # Message counts
                                "txmsgs": part.get("txmsgs", 0),
                                "txbytes": part.get("txbytes", 0),
                                "rxmsgs": part.get("rxmsgs", 0),
                                "rxbytes": part.get("rxbytes", 0),
                                "msgs": part.get("msgs", 0),
                                "msgs_inflight": part.get("msgs_inflight", 0),
                                "rx_ver_drops": part.get("rx_ver_drops", 0),
                                # Leader epoch (for fencing)
                                "leader_epoch": part.get("leader_epoch", -1),
                            }

            # Consumer group stats (full set)
            if "cgrp" in stats:
                cgrp = stats["cgrp"]
                self._cgrp_stats = {
                    "state": cgrp.get("state", ""),
                    "stateage_ms": cgrp.get("stateage", 0),
                    "join_state": cgrp.get("join_state", ""),
                    "rebalance_age_ms": cgrp.get("rebalance_age", 0),
                    "rebalance_cnt": cgrp.get("rebalance_cnt", 0),
                    "rebalance_reason": cgrp.get("rebalance_reason", ""),
                    "assignment_size": cgrp.get("assignment_size", 0),
                }

            # EOS/Idempotent producer stats (for transactional producers)
            if "eos" in stats:
                eos = stats["eos"]
                self._eos_stats = {
                    "idemp_state": eos.get("idemp_state", ""),
                    "idemp_stateage_ms": eos.get("idemp_stateage", 0),
                    "txn_state": eos.get("txn_state", ""),
                    "txn_stateage_ms": eos.get("txn_stateage", 0),
                    "txn_may_enq": eos.get("txn_may_enq", False),
                    "producer_id": eos.get("producer_id", -1),
                    "producer_epoch": eos.get("producer_epoch", -1),
                    "epoch_cnt": eos.get("epoch_cnt", 0),
                }

    def get_metrics(self) -> dict[str, Any]:
        """
        Get current metrics in Prometheus-friendly format.

        Returns:
            Dict of metric_name -> value
        """
        with self._lock:
            return {
                "kafka_client_name": self._stats.get("name", ""),
                "kafka_client_id": self._stats.get("client_id", ""),
                "kafka_client_type": self._stats.get("type", ""),
                "kafka_messages_queued": self._stats.get("msg_cnt", 0),
                "kafka_messages_queued_bytes": self._stats.get("msg_size", 0),
                "kafka_messages_queued_max": self._stats.get("msg_max", 0),
                "kafka_messages_queued_bytes_max": self._stats.get("msg_size_max", 0),
                "kafka_requests_total": self._stats.get("tx", 0),
                "kafka_requests_bytes_total": self._stats.get("tx_bytes", 0),
                "kafka_responses_total": self._stats.get("rx", 0),
                "kafka_responses_bytes_total": self._stats.get("rx_bytes", 0),
                "kafka_messages_produced_total": self._stats.get("txmsgs", 0),
                "kafka_messages_produced_bytes_total": self._stats.get("txmsg_bytes", 0),
                "kafka_messages_consumed_total": self._stats.get("rxmsgs", 0),
                "kafka_messages_consumed_bytes_total": self._stats.get("rxmsg_bytes", 0),
                "kafka_reply_queue_size": self._stats.get("replyq", 0),
                "kafka_metadata_cache_topics": self._stats.get("metadata_cache_cnt", 0),
            }

    def get_broker_metrics(self) -> dict[str, dict[str, Any]]:
        """
        Get per-broker metrics.

        Returns:
            Dict of broker_name -> metrics dict
        """
        with self._lock:
            return dict(self._broker_stats)

    def get_topic_metrics(self) -> dict[str, dict[str, Any]]:
        """
        Get per-topic metrics.

        Returns:
            Dict of topic_name -> metrics dict
        """
        with self._lock:
            return dict(self._topic_stats)

    def get_consumer_lag(self) -> dict[str, dict[int, int]]:
        """
        Get consumer lag per topic/partition.

        Returns:
            Dict of topic_name -> {partition: lag}
        """
        with self._lock:
            return {topic: dict(partitions) for topic, partitions in self._consumer_lag.items()}

    def get_cgrp_metrics(self) -> dict[str, Any]:
        """
        Get consumer group metrics.

        Returns:
            Dict of cgrp metric name -> value
        """
        with self._lock:
            return dict(self._cgrp_stats)

    def get_partition_metrics(self) -> dict[str, dict[int, dict[str, Any]]]:
        """
        Get per-partition metrics for all topics.

        Returns:
            Dict of topic_name -> {partition_id: metrics dict}

        Includes critical operational metrics:
        - fetch_state: Consumer fetch state (none, stopping, stopped, offset-query, active)
        - lo_offset, hi_offset, ls_offset: Watermarks
        - consumer_lag, consumer_lag_stored: Lag metrics
        - committed_offset, stored_offset: Offset tracking
        - msgq_cnt, fetchq_cnt: Queue depths
        """
        with self._lock:
            return {
                topic: {p: dict(stats) for p, stats in partitions.items()}
                for topic, partitions in self._partition_stats.items()
            }

    def get_eos_metrics(self) -> dict[str, Any]:
        """
        Get EOS (Exactly-Once Semantics) / Idempotent producer metrics.

        Returns:
            Dict of EOS metric name -> value

        Includes:
        - idemp_state: Idempotent producer state
        - txn_state: Transaction state
        - producer_id, producer_epoch: Producer identity
        """
        with self._lock:
            return dict(self._eos_stats)

    def get_all_metrics(self) -> dict[str, Any]:
        """
        Get all metrics in a single dict.

        Returns:
            Complete metrics dict with ALL available data:
            - client: Top-level client metrics
            - brokers: Per-broker metrics with latency percentiles
            - topics: Per-topic batch stats
            - partitions: Per-partition state and offsets
            - consumer_lag: Simple lag per partition
            - cgrp: Consumer group state
            - eos: Transactional producer state (if applicable)
        """
        return {
            "client": self.get_metrics(),
            "brokers": self.get_broker_metrics(),
            "topics": self.get_topic_metrics(),
            "partitions": self.get_partition_metrics(),
            "consumer_lag": self.get_consumer_lag(),
            "cgrp": self.get_cgrp_metrics(),
            "eos": self.get_eos_metrics(),
        }


def create_stats_callback(
    collector: KafkaMetricsCollector,
) -> Callable[[str], None]:
    """
    Create a stats callback function for librdkafka.

    Args:
        collector: KafkaMetricsCollector to receive stats

    Returns:
        Callback function suitable for stats_cb config

    Example:
        collector = KafkaMetricsCollector()
        config = {
            "bootstrap.servers": "localhost:9092",
            "statistics.interval.ms": 5000,
            "stats_cb": create_stats_callback(collector),
        }
    """

    def stats_callback(stats_json: str) -> None:
        collector.update_from_stats(stats_json)

    return stats_callback
