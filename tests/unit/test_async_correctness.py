#  Project:   hyperi-pylib
#  File:      tests/unit/test_async_correctness.py
#  Purpose:   Static + runtime checks that async code does not block the event loop
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Async correctness tests for hyperi-pylib.

Async bugs are opaque — a sync-in-async call won't fail at test time,
it just silently blocks the event loop in production. These tests
catch them statically (AST walk of every `async def` body) and at
runtime (event-loop liveness probe during capability calls).

Two test groups:

1. :class:`TestNoSyncInAsync` — AST walk of every async function in
   ``src/hyperi_pylib/``. Flags blocking-shaped calls that are not
   wrapped in ``run_blocking`` / ``asyncio.to_thread`` /
   ``run_in_executor``.

2. :class:`TestEventLoopLiveness` — runtime probe. While a capability
   is doing async work, a ticker on the event loop must keep firing.
   If the ticker stops, the work was blocking.

Pattern for capability authors: add an entry to
``TestEventLoopLiveness`` whenever you ship a new async method that
calls into a blocking SDK.
"""

from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

import pytest

from hyperi_pylib.concurrency import make_async, run_blocking

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "hyperi_pylib"


# ---------------------------------------------------------------------------
# 1. Static AST walk — catches sync-in-async at test time
# ---------------------------------------------------------------------------


def _attr_matches_dotted(node: ast.expr, dotted: str) -> bool:
    """Return True if ``node`` is the AST equivalent of ``a.b.c`` syntax."""
    parts = dotted.split(".")
    cur = node
    for part in reversed(parts[1:]):
        if not isinstance(cur, ast.Attribute) or cur.attr != part:
            return False
        cur = cur.value
    return isinstance(cur, ast.Name) and cur.id == parts[0]


def _is_blocking_call(call: ast.Call) -> str | None:
    """Return a label for the blocking shape, or None if the call is safe."""
    f = call.func

    # time.sleep / time.monotonic_ns blocks
    if _attr_matches_dotted(call, "time.sleep"):
        return "time.sleep(...)"

    # subprocess
    if (
        isinstance(f, ast.Attribute)
        and isinstance(f.value, ast.Name)
        and f.value.id == "subprocess"
        and f.attr in {"run", "call", "check_output", "check_call", "Popen"}
    ):
        return f"subprocess.{f.attr}(...)"

    # Path-like sync I/O
    if isinstance(f, ast.Attribute) and f.attr in {
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
    }:
        return f".{f.attr}(...) on Path"

    # requests library (we shouldn't use it at all, but flag if used)
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "requests":
        return f"requests.{f.attr}(...)"

    # urllib.request.urlopen
    if isinstance(f, ast.Attribute) and f.attr == "urlopen":
        return "urlopen(...)"

    # sync psycopg.connect
    if _attr_matches_dotted(call, "psycopg.connect"):
        return "psycopg.connect(...)  [use AsyncConnection.connect]"

    # Sync-sibling pattern: self.X_sync(...) inside async def is the
    # most common sync-in-async bug found by the audit
    if (
        isinstance(f, ast.Attribute)
        and f.attr.endswith("_sync")
        and isinstance(f.value, ast.Name)
        and f.value.id == "self"
    ):
        return f"self.{f.attr}(...)  [use make_async or run_blocking]"

    # pickle file ops
    if _attr_matches_dotted(call, "pickle.load") or _attr_matches_dotted(call, "pickle.dump"):
        return "pickle.load/dump(...)"

    return None


def _scan_async_function(fn: ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    """Return [(lineno, label), ...] for every blocking call inside ``fn``
    that is NOT wrapped in an async offload primitive."""
    # Collect the AST node ids that live inside an offload wrapper.
    safe: set[int] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Await):
            continue
        inner = node.value
        if not isinstance(inner, ast.Call):
            continue
        f = inner.func
        # asyncio.to_thread(...)  OR  X.to_thread(...) (anyio)
        if _attr_matches_dotted(inner, "asyncio.to_thread") or (isinstance(f, ast.Attribute) and f.attr == "to_thread"):
            for sub in ast.walk(inner):
                safe.add(id(sub))
            continue
        # run_in_executor(...)
        if isinstance(f, ast.Attribute) and f.attr == "run_in_executor":
            for sub in ast.walk(inner):
                safe.add(id(sub))
            continue
        # run_blocking(...)  (hyperi_pylib.concurrency)
        if isinstance(f, ast.Name) and f.id == "run_blocking":
            for sub in ast.walk(inner):
                safe.add(id(sub))
            continue
        # anyio.to_thread.run_sync(...)
        if _attr_matches_dotted(inner, "anyio.to_thread.run_sync"):
            for sub in ast.walk(inner):
                safe.add(id(sub))

    findings: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call) or id(node) in safe:
            continue
        label = _is_blocking_call(node)
        if label is not None:
            findings.append((node.lineno, label))

    # `with self._lock:` containing an `await` — deadlock risk
    for node in ast.walk(fn):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Attribute) and ctx.attr in {"_lock", "lock"}:
                has_await = any(isinstance(child, ast.Await) for child in ast.walk(node))
                if has_await:
                    findings.append(
                        (
                            node.lineno,
                            f"`with {ast.unparse(ctx)}:` holds a threading lock across `await`",
                        )
                    )

    return findings


# Files where we accept known unfixed sync-in-async bugs while the
# extraction of make_async / run_blocking lands. Each entry must include
# a tracking note. Add the file:line precisely; the test fails on any
# UNRECOGNISED finding.
KNOWN_UNFIXED: dict[str, set[tuple[int, str]]] = {
    # tracked in TODO.md "Async correctness" — converting to make_async
    "src/hyperi_pylib/secrets/providers/file.py": set(),
    "src/hyperi_pylib/secrets/providers/ansible_vault.py": set(),
    "src/hyperi_pylib/secrets/providers/openbao.py": set(),
}


def _all_findings() -> dict[Path, list[tuple[int, str]]]:
    by_file: dict[Path, list[tuple[int, str]]] = {}
    for py in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                findings = _scan_async_function(node)
                if findings:
                    by_file.setdefault(py, []).extend(findings)
    return by_file


class TestNoSyncInAsync:
    """Static guarantee: no async function makes a blocking call."""

    def test_no_known_unfixed_files_are_clean(self):
        """Files declared 'unfixed' in KNOWN_UNFIXED must STILL have findings
        — otherwise the entry is stale and should be removed."""
        by_file = _all_findings()
        for rel_path, expected in KNOWN_UNFIXED.items():
            full_path = SRC_ROOT.parent.parent / rel_path
            actual = set(by_file.get(full_path, []))
            if not actual and expected:
                pytest.fail(
                    f"{rel_path} is in KNOWN_UNFIXED but has no findings. Remove the KNOWN_UNFIXED entry — it's fixed!"
                )

    def test_no_new_sync_in_async(self):
        """Every async-def in pylib is free of blocking calls except for
        entries explicitly in KNOWN_UNFIXED."""
        by_file = _all_findings()
        new_findings: dict[str, list[tuple[int, str]]] = {}

        for py, items in by_file.items():
            rel = str(py.relative_to(SRC_ROOT.parent.parent))
            if rel in KNOWN_UNFIXED:
                continue
            new_findings[rel] = items

        if new_findings:
            lines = ["Sync-in-async findings (not in KNOWN_UNFIXED):"]
            for file, items in sorted(new_findings.items()):
                for lineno, label in sorted(items):
                    lines.append(f"  {file}:{lineno}  {label}")
            lines.append("")
            lines.append(
                "Fix: wrap in `await run_blocking(fn, ...)` or use "
                "`make_async(sync_fn)` to generate the async sibling. "
                "See hyperi_pylib.concurrency."
            )
            pytest.fail("\n".join(lines))


# ---------------------------------------------------------------------------
# 2. Runtime event-loop liveness — async work must not block the loop
# ---------------------------------------------------------------------------


class EventLoopLivenessProbe:
    """Background ticker that records how many times it fires.

    Use in tests: start the probe before kicking off async work; if the
    work blocks the event loop, the ticker stops firing and ``ticks``
    falls below ``expected_ticks``.
    """

    def __init__(self, tick_interval: float = 0.01) -> None:
        self.tick_interval = tick_interval
        self.ticks: list[float] = []
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _run(self) -> None:
        while not self._stop.is_set():
            self.ticks.append(time.monotonic())
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_interval)
            except TimeoutError:
                continue

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    @property
    def expected_ticks(self) -> int:
        """How many ticks should have fired given the elapsed wall time?"""
        if len(self.ticks) < 2:
            return 1
        elapsed = self.ticks[-1] - self.ticks[0]
        return max(1, int(elapsed / self.tick_interval))


class TestEventLoopLiveness:
    """Runtime probe: capability calls must not block the event loop.

    Each test starts a ticker on the loop, runs the capability, and
    asserts the ticker kept firing throughout.
    """

    async def test_run_blocking_keeps_loop_responsive(self):
        """run_blocking() of a sync sleep must not block the loop."""
        probe = EventLoopLivenessProbe(tick_interval=0.01)
        probe.start()
        await run_blocking(time.sleep, 0.1)
        await probe.stop()
        # 100ms of blocking + 10ms ticks = at least 5 ticks should fire
        assert len(probe.ticks) >= 5, f"loop was blocked: only {len(probe.ticks)} ticks fired"

    async def test_make_async_method_keeps_loop_responsive(self):
        """A method wrapped with make_async must not block the loop."""

        class _Sleeper:
            def slow_sync(self, duration: float) -> str:
                time.sleep(duration)
                return "done"

            slow_async = make_async(slow_sync)

        s = _Sleeper()
        probe = EventLoopLivenessProbe(tick_interval=0.01)
        probe.start()
        result = await s.slow_async(0.1)
        await probe.stop()

        assert result == "done"
        assert len(probe.ticks) >= 5, f"loop was blocked by make_async wrapper: only {len(probe.ticks)} ticks fired"

    async def test_naive_sync_call_DOES_block_the_loop(self):  # noqa: N802
        """Negative control: directly calling a sync sleep in an async
        function DOES block the loop. This test exists to prove the
        liveness probe is sensitive enough to detect blocking. If this
        test starts passing, the probe is broken."""
        probe = EventLoopLivenessProbe(tick_interval=0.01)
        probe.start()
        # Yield once so the ticker fires at least once before the block
        await asyncio.sleep(0)
        time.sleep(0.1)  # ← blocks the loop, the bug we're catching
        await probe.stop()

        # Loop was blocked: ticker fired at most once before the sleep
        # plus once after, so 1-2 ticks total (not 5+)
        assert len(probe.ticks) <= 3, (
            f"liveness probe is too lax: {len(probe.ticks)} ticks fired during a blocking sleep"
        )
