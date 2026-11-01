# Project:   scalo
# File:      tests/unit/test_kafka_call_timeouts.py
# Purpose:   Every blocking Kafka broker call ends within its configured bound
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""A broker that accepts the connection and never answers ends each call in a bounded time.

The listener is a real socket that never reads, so librdkafka connects, sends its
first request and waits. ``socket.timeout.ms`` sets the bound.
"""

import asyncio
import socket
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from scalo.kafka import (
    AsyncKafkaClient,
    KafkaAdmin,
    KafkaClient,
    KafkaConsumer,
    KafkaTimeoutError,
    ReadOnlyKafkaClient,
)
from scalo.kafka.config import call_timeout

_BOUND_MS = 500

# Generous over the bound: a call that is still running at this point never ends.
_GIVE_UP_SECONDS = 15.0


@pytest.fixture(scope="module")
def silent_broker() -> Iterator[dict[str, Any]]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(256)
    try:
        yield {"bootstrap.servers": f"127.0.0.1:{sock.getsockname()[1]}", "socket.timeout.ms": _BOUND_MS}
    finally:
        sock.close()


def _ends(call: Callable[[], object]) -> BaseException | None:
    """Run ``call`` on a daemon thread and return what it raised, failing if it never returns."""
    outcome: list[BaseException | None] = []

    def run() -> None:
        try:
            call()
        except BaseException as exc:
            outcome.append(exc)
        else:
            outcome.append(None)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(_GIVE_UP_SECONDS)
    assert outcome, f"still blocked after {_GIVE_UP_SECONDS}s against a silent broker"
    return outcome[0]


CALLS: list[Any] = [
    pytest.param(lambda c: KafkaClient(c).list_topics(), id="client-list-topics"),
    pytest.param(lambda c: KafkaClient(c).describe_topic("t"), id="client-describe-topic"),
    pytest.param(lambda c: KafkaClient(c).get_watermark_offsets("t"), id="client-watermarks"),
    pytest.param(lambda c: KafkaClient(c).get_consumer_lag("g", "t"), id="client-lag"),
    pytest.param(lambda c: KafkaClient(c).get_offsets_for_times("t", {0: 1}), id="client-offsets-for-times"),
    pytest.param(lambda c: ReadOnlyKafkaClient(c).list_topics(), id="readonly-list-topics"),
    pytest.param(lambda c: ReadOnlyKafkaClient(c).get_consumer_lag("g", "t"), id="readonly-lag"),
    pytest.param(lambda c: asyncio.run(AsyncKafkaClient(c).list_topics()), id="async-list-topics"),
    pytest.param(lambda c: asyncio.run(AsyncKafkaClient(c).describe_topic("t")), id="async-describe-topic"),
    pytest.param(lambda c: KafkaConsumer(c, "g").committed("t", [0]), id="consumer-committed"),
    pytest.param(lambda c: KafkaConsumer(c, "g").seek_to_end("t", 0), id="consumer-seek-to-end"),
    pytest.param(lambda c: KafkaAdmin(c).reset_offsets_to_earliest("g", "t", timeout=0.5), id="admin-reset"),
]


@pytest.mark.parametrize("call", CALLS)
def test_a_silent_broker_ends_the_call_with_a_timeout_error(silent_broker, call):
    raised = _ends(lambda: call(silent_broker))
    assert isinstance(raised, KafkaTimeoutError), f"expected KafkaTimeoutError, got {raised!r}"
    assert isinstance(raised, TimeoutError)


@pytest.mark.parametrize(
    ("config", "seconds"),
    [
        pytest.param({}, 30.0, id="unset-takes-the-default"),
        pytest.param({"socket.timeout.ms": 2500}, 2.5, id="int"),
        pytest.param({"socket.timeout.ms": "750"}, 0.75, id="string-from-a-properties-file"),
    ],
)
def test_the_bound_comes_from_socket_timeout_ms(config, seconds):
    assert call_timeout(config) == seconds


@pytest.mark.parametrize("raw", ["0", "-5", "soon"])
def test_a_bound_that_is_not_a_positive_number_is_refused(raw):
    with pytest.raises(ValueError, match=r"socket\.timeout\.ms"):
        call_timeout({"socket.timeout.ms": raw})
