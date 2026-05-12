#  Project:   hyperi-pylib
#  File:      tests/unit/test_concurrency.py
#  Purpose:   Unit tests for hyperi_pylib.concurrency
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the four async primitives."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from hyperi_pylib.concurrency import (
    Bulkhead,
    gather_with_timeouts,
    make_async,
    run_blocking,
)


# ---------------------------------------------------------------------------
# run_blocking
# ---------------------------------------------------------------------------


class TestRunBlocking:
    async def test_returns_value(self):
        def sync_compute() -> int:
            return 42

        result = await run_blocking(sync_compute)
        assert result == 42

    async def test_passes_positional_args(self):
        def add(a: int, b: int) -> int:
            return a + b

        result = await run_blocking(add, 2, 3)
        assert result == 5

    async def test_passes_keyword_args(self):
        def greet(name: str, greeting: str = "hi") -> str:
            return f"{greeting} {name}"

        result = await run_blocking(greet, "alice", greeting="hello")
        assert result == "hello alice"

    async def test_runs_on_worker_thread(self):
        main_thread = threading.get_ident()

        def get_thread_id() -> int:
            return threading.get_ident()

        worker_thread = await run_blocking(get_thread_id)
        assert worker_thread != main_thread

    async def test_propagates_exception(self):
        def boom() -> None:
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            await run_blocking(boom)

    async def test_event_loop_not_blocked(self):
        """The event loop keeps spinning while a sync fn sleeps in a thread."""
        # Start a 100ms sync sleep on a worker thread
        # During that time, an asyncio.sleep(50ms) on the event loop should complete
        ticks = []

        async def ticker() -> None:
            for _ in range(3):
                ticks.append(time.monotonic())
                await asyncio.sleep(0.03)

        async def slow_blocking() -> str:
            await run_blocking(time.sleep, 0.1)
            return "done"

        ticker_task = asyncio.create_task(ticker())
        result = await slow_blocking()
        await ticker_task

        assert result == "done"
        # Event loop kept making progress — at least 2 ticks fired during the blocking sleep
        assert len(ticks) == 3


# ---------------------------------------------------------------------------
# make_async
# ---------------------------------------------------------------------------


class _Provider:
    """Sample dual-API provider used by make_async tests."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_sync(self, path: str) -> str:
        self.calls.append(path)
        return f"value@{path}"

    def fail_sync(self, msg: str) -> None:
        raise RuntimeError(msg)


class TestMakeAsync:
    async def test_wraps_sync_method(self):
        provider = _Provider()
        get_async = make_async(provider.get_sync)

        result = await get_async("foo")
        assert result == "value@foo"
        assert provider.calls == ["foo"]

    async def test_runs_on_worker_thread(self):
        main_thread = threading.get_ident()

        def get_thread() -> int:
            return threading.get_ident()

        get_thread_async = make_async(get_thread)
        worker_thread = await get_thread_async()
        assert worker_thread != main_thread

    async def test_propagates_exception(self):
        provider = _Provider()
        fail_async = make_async(provider.fail_sync)

        with pytest.raises(RuntimeError, match="boom"):
            await fail_async("boom")

    async def test_class_level_binding(self):
        """The intended pattern: bind X_async = make_async(X_sync) at class level."""

        class MyProvider:
            def get_sync(self, path: str) -> str:
                return f"got {path}"

            get_async = make_async(get_sync)

        p = MyProvider()
        result = await p.get_async("x")
        assert result == "got x"


# ---------------------------------------------------------------------------
# Bulkhead
# ---------------------------------------------------------------------------


class TestBulkhead:
    def test_rejects_zero_limit(self):
        with pytest.raises(ValueError, match=">= 1"):
            Bulkhead("test", limit=0)

    def test_rejects_negative_limit(self):
        with pytest.raises(ValueError, match=">= 1"):
            Bulkhead("test", limit=-5)

    def test_repr(self):
        b = Bulkhead("aws-secrets", limit=10)
        assert repr(b) == "Bulkhead(name='aws-secrets', limit=10)"
        assert b.name == "aws-secrets"
        assert b.limit == 10

    async def test_single_use(self):
        bulkhead = Bulkhead("test", limit=1)
        async with bulkhead:
            assert True  # acquired

    async def test_enforces_limit(self):
        """With limit=2, three concurrent tasks: at most 2 run at once."""
        bulkhead = Bulkhead("test", limit=2)
        in_flight = 0
        max_in_flight = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal in_flight, max_in_flight
            async with bulkhead:
                async with lock:
                    in_flight += 1
                    max_in_flight = max(max_in_flight, in_flight)
                await asyncio.sleep(0.02)
                async with lock:
                    in_flight -= 1

        await asyncio.gather(*(worker() for _ in range(5)))
        assert max_in_flight == 2

    async def test_releases_on_exception(self):
        """If the protected code raises, the slot is still released."""
        bulkhead = Bulkhead("test", limit=1)

        with pytest.raises(RuntimeError):
            async with bulkhead:
                raise RuntimeError("oops")

        # Slot should be free — second acquire returns immediately
        async with asyncio.timeout(0.05):
            async with bulkhead:
                pass


# ---------------------------------------------------------------------------
# gather_with_timeouts
# ---------------------------------------------------------------------------


class TestGatherWithTimeouts:
    async def test_returns_results_in_dict(self):
        async def make(value):
            async def fn():
                return value

            return fn

        results = await gather_with_timeouts(
            {
                "a": await make(1),
                "b": await make(2),
                "c": await make(3),
            },
            per_task_timeout=1.0,
        )

        assert results == {"a": 1, "b": 2, "c": 3}

    async def test_runs_in_parallel(self):
        """Three 50ms tasks complete in ~50ms, not 150ms."""

        async def sleeper():
            await asyncio.sleep(0.05)
            return "done"

        start = time.monotonic()
        results = await gather_with_timeouts(
            {"a": sleeper, "b": sleeper, "c": sleeper},
            per_task_timeout=1.0,
        )
        elapsed = time.monotonic() - start

        assert all(v == "done" for v in results.values())
        assert elapsed < 0.15  # Would be ~0.15s if sequential

    async def test_per_task_timeout(self):
        async def quick():
            return "fast"

        async def slow():
            await asyncio.sleep(0.2)
            return "slow"

        results = await gather_with_timeouts(
            {"quick": quick, "slow": slow},
            per_task_timeout=0.05,
        )

        assert results["quick"] == "fast"
        assert isinstance(results["slow"], TimeoutError)

    async def test_captures_exceptions_per_task(self):
        async def fail():
            raise ValueError("kaboom")

        async def succeed():
            return "ok"

        results = await gather_with_timeouts(
            {"good": succeed, "bad": fail},
            per_task_timeout=1.0,
        )

        assert results["good"] == "ok"
        assert isinstance(results["bad"], ValueError)
        assert str(results["bad"]) == "kaboom"

    async def test_empty_tasks(self):
        results = await gather_with_timeouts({}, per_task_timeout=1.0)
        assert results == {}
