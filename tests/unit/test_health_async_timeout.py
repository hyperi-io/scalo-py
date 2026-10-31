#  Project:   scalo
#  File:      tests/unit/test_health_async_timeout.py
#  Purpose:   Verify async probes apply per-check timeout + offload sync checks
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Async health probes must:
- run sync checks via ``run_blocking`` so they don't stall the event loop;
- enforce per-check timeouts so a hung check can't stall the kubelet probe;
- support async checks natively;
- serialise concurrent registration safely.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from scalo.health.manager import HealthManager


@pytest.mark.asyncio
async def test_per_check_timeout_marks_slow_check_as_failed():
    mgr = HealthManager(default_check_timeout=0.05)
    release = threading.Event()
    finished = threading.Event()

    def hung():
        # Held until the test lets go. The 5 s wait only keeps a missing timeout from hanging the suite.
        release.wait(5)
        finished.set()
        return True

    mgr.register_ready_check("slow_db", hung)
    mgr.set_ready()

    try:
        resp = await mgr.readiness_response_async()
        answered_while_hung = not finished.is_set()
    finally:
        release.set()

    assert answered_while_hung, "the response waited for the check instead of timing it out"
    assert resp["status"] == "not_ready"
    assert resp["checks"]["slow_db"] is False


@pytest.mark.asyncio
async def test_async_check_supported():
    mgr = HealthManager()

    async def ping():
        await asyncio.sleep(0.01)
        return True

    mgr.register_ready_check("kafka", ping)
    mgr.set_ready()

    resp = await mgr.readiness_response_async()
    assert resp["status"] == "ready"
    assert resp["checks"]["kafka"] is True


@pytest.mark.asyncio
async def test_one_slow_check_does_not_block_others():
    """Checks run concurrently: each one waits for the other two, which only passes when all three are running at once."""
    mgr = HealthManager(default_check_timeout=5)
    meeting = asyncio.Barrier(3)

    async def meets_the_others():
        await meeting.wait()
        return True

    mgr.register_ready_check("a", meets_the_others)
    mgr.register_ready_check("b", meets_the_others)
    mgr.register_ready_check("c", meets_the_others)
    mgr.set_ready()

    resp = await mgr.readiness_response_async()

    assert resp["status"] == "ready"
    assert resp["checks"] == {"a": True, "b": True, "c": True}


@pytest.mark.asyncio
async def test_raising_check_is_treated_as_failure():
    mgr = HealthManager()

    def boom():
        raise RuntimeError("downstream exploded")

    mgr.register_ready_check("flaky", boom)
    mgr.set_ready()

    resp = await mgr.readiness_response_async()
    assert resp["status"] == "not_ready"
    assert resp["checks"]["flaky"] is False


def test_concurrent_registration_is_safe():
    """Registering checks from multiple threads doesn't corrupt the list."""
    mgr = HealthManager()

    def register_many(prefix: str):
        for i in range(50):
            mgr.register_ready_check(f"{prefix}_{i}", lambda: True)

    threads = [threading.Thread(target=register_many, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 4 threads x 50 checks = 200 entries, no duplicates corrupting the list
    assert len(mgr._ready_checks) == 200
    names = {name for name, _, _ in mgr._ready_checks}
    assert len(names) == 200  # all unique
