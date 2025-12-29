# TDD Work Breakdown Structure: hs_pylib.kafka

**Issue:** DFE-553
**Branch:** `feat/DFE-553/add-kafka-library`
**Approach:** Test-Driven Development (Red-Green-Refactor)

---

## TDD Principles for This Implementation

1. **Red**: Write a failing test first
2. **Green**: Write minimal code to pass the test
3. **Refactor**: Clean up while keeping tests green
4. **One test at a time**: Focus on a single failing test before moving on

---

## Phase 0: Setup (No Tests Yet)

### 0.1 Add Dependencies to pyproject.toml
- [ ] Add `confluent-kafka>=2.3` to optional dependencies
- [ ] Add `genson>=1.3` to optional dependencies
- [ ] Create `kafka` extras group
- [ ] Run `uv sync` to install

### 0.2 Create Module Structure
- [ ] Create `src/hs_pylib/kafka/` directory
- [ ] Create `src/hs_pylib/kafka/__init__.py` (empty)
- [ ] Create `tests/unit/test_kafka.py` (empty test file)

---

## Phase 1: Types and Config (Foundation)

Start with types - no Kafka connection needed, pure Python.

### 1.1 Corporate Defaults
```
tests/unit/test_kafka.py::TestDefaults
```
- [ ] **TEST**: `test_producer_defaults_has_acks_all`
- [ ] **TEST**: `test_producer_defaults_has_idempotence`
- [ ] **TEST**: `test_producer_defaults_has_lz4_compression`
- [ ] **TEST**: `test_consumer_defaults_has_earliest_offset`
- [ ] **TEST**: `test_consumer_defaults_has_auto_commit_disabled`
- [ ] **IMPL**: Create `config.py` with `PRODUCER_DEFAULTS`, `CONSUMER_DEFAULTS`, `ADMIN_DEFAULTS`

### 1.2 Message Type
```
tests/unit/test_kafka.py::TestMessage
```
- [ ] **TEST**: `test_message_dataclass_fields`
- [ ] **TEST**: `test_message_from_confluent_message`
- [ ] **TEST**: `test_message_value_as_json`
- [ ] **TEST**: `test_message_value_as_bytes`
- [ ] **IMPL**: Create `types.py` with `Message` dataclass

### 1.3 Topic Info Types
```
tests/unit/test_kafka.py::TestTopicTypes
```
- [ ] **TEST**: `test_topic_info_dataclass`
- [ ] **TEST**: `test_partition_info_dataclass`
- [ ] **TEST**: `test_topic_metadata_dataclass`
- [ ] **IMPL**: Add `TopicInfo`, `PartitionInfo`, `TopicMetadata` to `types.py`

### 1.4 Config Merge Logic
```
tests/unit/test_kafka.py::TestConfigMerge
```
- [ ] **TEST**: `test_merge_config_applies_defaults`
- [ ] **TEST**: `test_merge_config_user_overrides_defaults`
- [ ] **TEST**: `test_merge_config_preserves_user_keys`
- [ ] **TEST**: `test_verify_ssl_false_sets_librdkafka_config`
- [ ] **IMPL**: Add `merge_config()` helper to `config.py`

---

## Phase 2: KafkaClient (Admin Operations)

Test with mocked confluent-kafka AdminClient.

### 2.1 Client Initialization
```
tests/unit/test_kafka.py::TestKafkaClient
```
- [ ] **TEST**: `test_client_init_with_bootstrap_servers`
- [ ] **TEST**: `test_client_init_with_dict_config`
- [ ] **TEST**: `test_client_init_merges_admin_defaults`
- [ ] **TEST**: `test_client_init_verify_ssl_false`
- [ ] **TEST**: `test_client_context_manager`
- [ ] **IMPL**: Create `client.py` with `KafkaClient.__init__`, `__enter__`, `__exit__`

### 2.2 List Topics
```
tests/unit/test_kafka.py::TestKafkaClientListTopics
```
- [ ] **TEST**: `test_list_topics_returns_topic_info_list`
- [ ] **TEST**: `test_list_topics_excludes_internal_by_default`
- [ ] **TEST**: `test_list_topics_includes_internal_when_requested`
- [ ] **TEST**: `test_list_topics_empty_cluster`
- [ ] **IMPL**: Add `list_topics()` method

### 2.3 Describe Topic
```
tests/unit/test_kafka.py::TestKafkaClientDescribeTopic
```
- [ ] **TEST**: `test_describe_topic_returns_metadata`
- [ ] **TEST**: `test_describe_topic_includes_partitions`
- [ ] **TEST**: `test_describe_topic_includes_config`
- [ ] **TEST**: `test_describe_topic_not_found_raises`
- [ ] **IMPL**: Add `describe_topic()` method

### 2.4 Offset Operations
```
tests/unit/test_kafka.py::TestKafkaClientOffsets
```
- [ ] **TEST**: `test_get_offsets_for_times_single_partition`
- [ ] **TEST**: `test_get_offsets_for_times_all_partitions`
- [ ] **TEST**: `test_get_offsets_for_times_no_message_at_time`
- [ ] **IMPL**: Add `get_offsets_for_times()`

### 2.5 Consumer Group Lag (No JMX Required)
```
tests/unit/test_kafka.py::TestKafkaClientConsumerLag
```
Uses AdminClient + watermark offsets - no JMX needed.
- [ ] **TEST**: `test_get_consumer_lag_returns_partition_dict`
- [ ] **TEST**: `test_get_consumer_lag_calculates_correctly` (high_watermark - committed)
- [ ] **TEST**: `test_get_consumer_lag_no_group_raises`
- [ ] **TEST**: `test_get_consumer_lag_no_commits_returns_full_lag`
- [ ] **TEST**: `test_get_consumer_lag_multiple_topics`
- [ ] **TEST**: `test_list_consumer_groups`
- [ ] **TEST**: `test_describe_consumer_group`
- [ ] **IMPL**: Add `get_consumer_lag()`, `list_consumer_groups()`, `describe_consumer_group()`

### 2.6 Topic Statistics
```
tests/unit/test_kafka.py::TestKafkaClientTopicStats
```
- [ ] **TEST**: `test_get_topic_message_count` (sum of partition sizes)
- [ ] **TEST**: `test_get_partition_sizes`
- [ ] **TEST**: `test_get_watermark_offsets`
- [ ] **IMPL**: Add `get_topic_message_count()`, `get_partition_sizes()`, `get_watermark_offsets()`

---

## Phase 3: KafkaConsumer

### 3.1 Consumer Initialization
```
tests/unit/test_kafka.py::TestKafkaConsumer
```
- [ ] **TEST**: `test_consumer_init_with_group_id`
- [ ] **TEST**: `test_consumer_init_merges_defaults`
- [ ] **TEST**: `test_consumer_init_verify_ssl_false`
- [ ] **TEST**: `test_consumer_context_manager`
- [ ] **IMPL**: Create `consumer.py` with `KafkaConsumer.__init__`

### 3.2 Subscribe and Poll
```
tests/unit/test_kafka.py::TestKafkaConsumerPoll
```
- [ ] **TEST**: `test_consumer_subscribe_single_topic`
- [ ] **TEST**: `test_consumer_subscribe_multiple_topics`
- [ ] **TEST**: `test_consumer_poll_returns_message`
- [ ] **TEST**: `test_consumer_poll_timeout_returns_none`
- [ ] **TEST**: `test_consumer_poll_error_raises`
- [ ] **IMPL**: Add `subscribe()`, `poll()` methods

### 3.3 Seek and Position
```
tests/unit/test_kafka.py::TestKafkaConsumerSeek
```
- [ ] **TEST**: `test_consumer_seek_to_offset`
- [ ] **TEST**: `test_consumer_seek_to_beginning`
- [ ] **TEST**: `test_consumer_seek_to_end`
- [ ] **TEST**: `test_consumer_position_returns_offset`
- [ ] **IMPL**: Add `seek()`, `position()` methods

### 3.4 Commit Operations
```
tests/unit/test_kafka.py::TestKafkaConsumerCommit
```
- [ ] **TEST**: `test_consumer_commit_sync`
- [ ] **TEST**: `test_consumer_commit_async`
- [ ] **TEST**: `test_consumer_committed_returns_offsets`
- [ ] **IMPL**: Add `commit()`, `committed()` methods

### 3.5 Iterator Interface
```
tests/unit/test_kafka.py::TestKafkaConsumerIterator
```
- [ ] **TEST**: `test_consumer_iter_yields_messages`
- [ ] **TEST**: `test_consumer_iter_stops_on_close`
- [ ] **IMPL**: Add `__iter__()`, `__next__()` methods

---

## Phase 4: KafkaProducer

### 4.1 Producer Initialization
```
tests/unit/test_kafka.py::TestKafkaProducer
```
- [ ] **TEST**: `test_producer_init_merges_defaults`
- [ ] **TEST**: `test_producer_init_verify_ssl_false`
- [ ] **TEST**: `test_producer_context_manager`
- [ ] **IMPL**: Create `producer.py` with `KafkaProducer.__init__`

### 4.2 Send Messages
```
tests/unit/test_kafka.py::TestKafkaProducerSend
```
- [ ] **TEST**: `test_producer_send_string_value`
- [ ] **TEST**: `test_producer_send_bytes_value`
- [ ] **TEST**: `test_producer_send_json_value`
- [ ] **TEST**: `test_producer_send_with_key`
- [ ] **TEST**: `test_producer_send_with_headers`
- [ ] **TEST**: `test_producer_send_returns_future`
- [ ] **IMPL**: Add `send()` method

### 4.3 Flush
```
tests/unit/test_kafka.py::TestKafkaProducerFlush
```
- [ ] **TEST**: `test_producer_flush_all_messages`
- [ ] **TEST**: `test_producer_flush_with_timeout`
- [ ] **TEST**: `test_producer_flush_returns_unflushed_count`
- [ ] **IMPL**: Add `flush()` method

---

## Phase 5: Sampling Utilities

Pure Python logic, can be tested with mocked consumer.

### 5.1 Time-Bounded Consume
```
tests/unit/test_kafka.py::TestTimeBoundedConsume
```
- [ ] **TEST**: `test_time_bounded_consume_returns_messages_in_range`
- [ ] **TEST**: `test_time_bounded_consume_respects_limit`
- [ ] **TEST**: `test_time_bounded_consume_empty_range`
- [ ] **TEST**: `test_time_bounded_consume_uses_offsets_for_times`
- [ ] **IMPL**: Create `sampling.py` with `time_bounded_consume()`

### 5.2 Reservoir Sampling
```
tests/unit/test_kafka.py::TestReservoirSample
```
- [ ] **TEST**: `test_reservoir_sample_returns_k_messages`
- [ ] **TEST**: `test_reservoir_sample_less_than_k_available`
- [ ] **TEST**: `test_reservoir_sample_uniform_distribution` (statistical)
- [ ] **TEST**: `test_reservoir_sample_deterministic_with_seed`
- [ ] **IMPL**: Add `reservoir_sample()` to `sampling.py`

### 5.3 Partition Sampling
```
tests/unit/test_kafka.py::TestPartitionSample
```
- [ ] **TEST**: `test_partition_sample_n_per_partition`
- [ ] **TEST**: `test_partition_sample_all_partitions`
- [ ] **TEST**: `test_partition_sample_empty_partition`
- [ ] **IMPL**: Add `partition_sample()` to `sampling.py`

---

## Phase 6: Schema Analyser

Pure Python with GenSON, no Kafka needed.

### 6.1 Basic Schema Inference
```
tests/unit/test_kafka.py::TestSchemaAnalyser
```
- [ ] **TEST**: `test_analyser_init`
- [ ] **TEST**: `test_analyser_single_message_schema`
- [ ] **TEST**: `test_analyser_multiple_same_schema`
- [ ] **TEST**: `test_analyser_merged_schema`
- [ ] **IMPL**: Create `schema.py` with `SchemaAnalyser.__init__`, `add_message()`

### 6.2 Multi-Pattern Detection
```
tests/unit/test_kafka.py::TestSchemaAnalyserPatterns
```
- [ ] **TEST**: `test_analyser_detects_single_pattern`
- [ ] **TEST**: `test_analyser_detects_multiple_patterns`
- [ ] **TEST**: `test_analyser_pattern_percentage`
- [ ] **TEST**: `test_analyser_example_message_per_pattern`
- [ ] **IMPL**: Add pattern detection to `SchemaAnalyser`

### 6.3 Field Statistics
```
tests/unit/test_kafka.py::TestSchemaAnalyserFieldStats
```
- [ ] **TEST**: `test_analyser_field_cardinality`
- [ ] **TEST**: `test_analyser_field_types_seen`
- [ ] **TEST**: `test_analyser_field_null_count`
- [ ] **TEST**: `test_analyser_field_sample_values`
- [ ] **IMPL**: Add `FieldStats` calculation

### 6.4 Analysis Result
```
tests/unit/test_kafka.py::TestSchemaAnalysisResult
```
- [ ] **TEST**: `test_analyse_sample_returns_result`
- [ ] **TEST**: `test_result_total_messages`
- [ ] **TEST**: `test_result_schema_consistency_score`
- [ ] **TEST**: `test_result_merged_schema`
- [ ] **IMPL**: Add `analyse_sample()` function

---

## Phase 7: Async Wrappers (ThreadPoolExecutor)

### 7.1 AsyncKafkaClient
```
tests/unit/test_kafka.py::TestAsyncKafkaClient
```
- [ ] **TEST**: `test_async_client_init`
- [ ] **TEST**: `test_async_client_context_manager`
- [ ] **TEST**: `test_async_list_topics`
- [ ] **TEST**: `test_async_describe_topic`
- [ ] **TEST**: `test_async_get_offsets_for_times`
- [ ] **IMPL**: Create `async_client.py` with `AsyncKafkaClient`

### 7.2 AsyncKafkaConsumer
```
tests/unit/test_kafka.py::TestAsyncKafkaConsumer
```
- [ ] **TEST**: `test_async_consumer_init`
- [ ] **TEST**: `test_async_consumer_context_manager`
- [ ] **TEST**: `test_async_consumer_poll`
- [ ] **TEST**: `test_async_consumer_seek`
- [ ] **TEST**: `test_async_consumer_commit`
- [ ] **TEST**: `test_async_consumer_aiter`
- [ ] **IMPL**: Create `async_consumer.py` with `AsyncKafkaConsumer`

### 7.3 AsyncKafkaProducer
```
tests/unit/test_kafka.py::TestAsyncKafkaProducer
```
- [ ] **TEST**: `test_async_producer_init`
- [ ] **TEST**: `test_async_producer_context_manager`
- [ ] **TEST**: `test_async_producer_send`
- [ ] **TEST**: `test_async_producer_flush`
- [ ] **IMPL**: Create `async_producer.py` with `AsyncKafkaProducer`

### 7.4 Async Sampling Functions
```
tests/unit/test_kafka.py::TestAsyncSampling
```
- [ ] **TEST**: `test_atime_bounded_consume`
- [ ] **TEST**: `test_areservoir_sample`
- [ ] **TEST**: `test_apartition_sample`
- [ ] **IMPL**: Add async wrappers to `sampling.py`

---

## Phase 8: Integration (Module Exports)

### 8.1 Public API
```
tests/unit/test_kafka.py::TestKafkaModuleExports
```
- [ ] **TEST**: `test_import_kafka_client`
- [ ] **TEST**: `test_import_kafka_consumer`
- [ ] **TEST**: `test_import_kafka_producer`
- [ ] **TEST**: `test_import_async_variants`
- [ ] **TEST**: `test_import_sampling_functions`
- [ ] **TEST**: `test_import_schema_analyser`
- [ ] **TEST**: `test_import_types`
- [ ] **TEST**: `test_import_defaults`
- [ ] **IMPL**: Update `__init__.py` with public exports

---

## Phase 9: Integration Tests (Real Kafka)

These tests require a Kafka broker. Mark with `@pytest.mark.integration`.

### 9.1 Setup
```
tests/integration/test_kafka_integration.py
```
- [ ] Create Docker Compose for Kafka broker
- [ ] Create pytest fixture for Kafka connection
- [ ] Environment variable: `KAFKA_BOOTSTRAP_SERVERS`

### 9.2 Real Broker Tests
- [ ] **TEST**: `test_real_list_topics`
- [ ] **TEST**: `test_real_produce_consume_roundtrip`
- [ ] **TEST**: `test_real_consumer_group_lag`
- [ ] **TEST**: `test_real_time_bounded_consume`
- [ ] **TEST**: `test_real_reservoir_sample`

---

## Execution Order Summary

```
Phase 0: Setup                    [~30 min]
Phase 1: Types and Config         [~2 hours]
Phase 2: KafkaClient              [~2 hours]
Phase 3: KafkaConsumer            [~2 hours]
Phase 4: KafkaProducer            [~1 hour]
Phase 5: Sampling Utilities       [~2 hours]
Phase 6: Schema Analyser          [~2 hours]
Phase 7: Async Wrappers           [~2 hours]
Phase 8: Integration (Exports)    [~30 min]
Phase 9: Integration Tests        [~2 hours] (optional for local)
```

**Total estimated: ~16 hours**

---

## Test Running Commands

```bash
# Run all Kafka unit tests
pytest tests/unit/test_kafka.py -v

# Run specific test class
pytest tests/unit/test_kafka.py::TestDefaults -v

# Run with coverage
pytest tests/unit/test_kafka.py -v --cov=src/hs_pylib/kafka --cov-report=term-missing

# Run integration tests (requires Kafka)
pytest tests/integration/test_kafka_integration.py -v -m integration
```

---

## Mocking Strategy

For unit tests, mock confluent-kafka at the boundary:

```python
from unittest.mock import Mock, patch

@pytest.fixture
def mock_admin_client():
    with patch('hs_pylib.kafka.client.AdminClient') as mock:
        yield mock

@pytest.fixture
def mock_consumer():
    with patch('hs_pylib.kafka.consumer.Consumer') as mock:
        yield mock

@pytest.fixture
def mock_producer():
    with patch('hs_pylib.kafka.producer.Producer') as mock:
        yield mock
```

---

**Last Updated:** 2025-12-05
