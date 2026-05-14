#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/concurrency.py
#  Purpose:   Generic async primitives — the small set every capability uses
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Generic async primitives for at-scale Python services.

Four building blocks that every HyperI capability composes:

- :func:`run_blocking` — sync-to-async bridge (offload to worker thread).
- :func:`make_async` — generate the async sibling of a sync method.
- :class:`Bulkhead` — bounded concurrency limit per downstream dependency.
- :func:`gather_with_timeouts` — parallel exec with per-task timeout.

Composable resilience (timeout + retry + circuit breaker + bulkhead)
lives in :mod:`hyperi_pylib.resilience` via ``with_resilience()``.

Discipline
----------
- Never call ``loop.run_in_executor`` directly. Use :func:`run_blocking`.
- Never write ``async def foo_async(...): return self.foo_sync(...)``.
  That blocks the event loop. Use :func:`make_async` or the audit will
  catch you.
- Never share a global ``ThreadPoolExecutor`` for many downstream deps.
  Use one :class:`Bulkhead` per dep — that's what bulkhead means.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

import anyio

__all__ = [
    "Bulkhead",
    "gather_with_timeouts",
    "make_async",
    "run_blocking",
]


T = TypeVar("T")
P = ParamSpec("P")


async def run_blocking[**P, T](
    fn: Callable[P, T],
    *args: P.args,
    abandon_on_cancel: bool = False,
    limiter: anyio.CapacityLimiter | None = None,
    **kwargs: P.kwargs,
) -> T:
    """Run a sync function on a worker thread; never block the event loop.

    Replaces every ad-hoc ``await loop.run_in_executor(None, fn, *args)``.
    Built on ``anyio.to_thread.run_sync`` for portable cancellation
    semantics across asyncio and trio.

    Args:
        fn: The blocking function to execute on a worker thread.
        *args: Positional arguments passed to ``fn``.
        abandon_on_cancel: If False (default), the task waits for the
            worker thread to finish even if the calling task is
            cancelled — Python cannot interrupt a running thread, so
            ignoring the outcome is the safest option. Set True to
            abandon and ignore the result.
        limiter: Optional ``anyio.CapacityLimiter`` to bound concurrency
            for this specific call. By default the AnyIO global limiter
            (40 threads) applies. For per-dependency bounds use a
            :class:`Bulkhead` instead.
        **kwargs: Keyword arguments passed to ``fn``.

    Returns:
        Whatever ``fn`` returned.

    Example:
        >>> async def read_config(path: Path) -> bytes:
        ...     return await run_blocking(path.read_bytes)
    """
    import functools

    if kwargs:
        return await anyio.to_thread.run_sync(
            functools.partial(fn, *args, **kwargs),
            abandon_on_cancel=abandon_on_cancel,
            limiter=limiter,
        )
    return await anyio.to_thread.run_sync(
        fn,
        *args,
        abandon_on_cancel=abandon_on_cancel,
        limiter=limiter,
    )


def make_async[**P, T](
    sync_fn: Callable[P, T],
    *,
    abandon_on_cancel: bool = False,
    limiter: anyio.CapacityLimiter | None = None,
) -> Callable[P, Coroutine[Any, Any, T]]:
    """Generate the async sibling of a sync function.

    Use the dual-API pattern: implement ``X_sync()`` only, then bind
    ``X_async = make_async(X_sync)`` at class level. The async version
    offloads to a worker thread, so it's safe to ``await`` from any
    async caller — no blocking the event loop.

    Built on ``asyncer.asyncify`` (which is itself built on AnyIO) for
    type-checker visibility into the wrapped callable's signature.

    Args:
        sync_fn: The sync function to wrap.
        abandon_on_cancel: If True, async cancellation discards the
            wrapped call's outcome. The thread itself keeps running —
            Python cannot interrupt threads. Default False matches
            AnyIO's shield-by-default: the caller waits for the thread
            to finish even if cancelled.
        limiter: Optional ``anyio.CapacityLimiter`` for per-function
            concurrency bounds.

    Returns:
        An async function with the same signature as ``sync_fn``.

    Example:
        >>> class FileProvider:
        ...     def get_sync(self, path: str) -> bytes: ...
        ...     get_async = make_async(get_sync)
    """
    from asyncer import asyncify

    return asyncify(sync_fn, abandon_on_cancel=abandon_on_cancel, limiter=limiter)


class Bulkhead:
    """Bounded concurrency limit for a single downstream dependency.

    Pattern: one ``Bulkhead`` instance per (service, endpoint). When
    ``limit`` tasks are already in flight, the next one waits. Prevents
    a single slow downstream from starving every other coroutine in the
    process.

    Use as an async context manager around the call to the dependency.

    Args:
        name: Human-readable label (used in observability hooks later).
        limit: Maximum concurrent calls. Must be >= 1.

    Example:
        >>> aws_secrets_bulkhead = Bulkhead("aws-secrets", limit=32)
        >>> async with aws_secrets_bulkhead:
        ...     value = await secrets_client.get(path)
    """

    def __init__(self, name: str, limit: int) -> None:
        if limit < 1:
            raise ValueError(f"Bulkhead limit must be >= 1, got {limit}")
        self.name = name
        self.limit = limit
        self._sem = anyio.Semaphore(limit)

    async def __aenter__(self) -> Bulkhead:
        await self._sem.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._sem.release()

    def __repr__(self) -> str:
        return f"Bulkhead(name={self.name!r}, limit={self.limit})"


async def gather_with_timeouts[T](
    tasks: dict[str, Callable[[], Awaitable[T]]],
    *,
    per_task_timeout: float,
) -> dict[str, T | Exception]:
    """Run async tasks in parallel with a per-task timeout.

    Each task gets its own ``asyncio.timeout(per_task_timeout)`` budget.
    Exceptions (including ``TimeoutError``) are captured per task — one
    slow check does not fail the others.

    Args:
        tasks: Mapping of task name -> zero-arg coroutine factory.
            Each value is a callable that returns a fresh coroutine.
            Passing ``Coroutine`` objects directly would couple their
            lifetimes; factories let each task be cancelled cleanly.
        per_task_timeout: Per-task timeout in seconds.

    Returns:
        Dict mapping the original task names to either the task's
        result or the exception it raised.

    Example:
        >>> results = await gather_with_timeouts(
        ...     {
        ...         "db": lambda: db.ping(),
        ...         "kafka": lambda: producer.health_check(),
        ...         "redis": lambda: redis.ping(),
        ...     },
        ...     per_task_timeout=1.0,
        ... )
        >>> healthy = {k: v for k, v in results.items() if not isinstance(v, Exception)}
    """

    async def _run_one(name: str, fn: Callable[[], Awaitable[T]]) -> tuple[str, T | Exception]:
        try:
            async with asyncio.timeout(per_task_timeout):
                return (name, await fn())
        except Exception as e:
            return (name, e)

    results = await asyncio.gather(*(_run_one(name, fn) for name, fn in tasks.items()))
    return dict(results)
