#  Project:   scalo
#  File:      tests/smoke/test_import_isolation.py
#  Purpose:   Circular-import guard -- every module must import first, alone
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""Startup import guards.

A circular import between two scalo modules does not fail consistently -- it
fails only when the cycle is entered from the wrong side, so it hides until a
consumer imports a submodule directly and gets a half-built module. These tests
cover both halves of that:

- a structural pass over every module, so a cycle is reported as a cycle rather
  than as whichever ImportError it happens to produce, and
- a runtime pass that imports each subpackage FIRST in a fresh interpreter, so
  entering from any side is exercised.

Lazy imports (inside a function or method) are fine and are not reported -- they
are how the config/logger cycle is deliberately broken.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PKG = "scalo"
SRC = Path(__file__).resolve().parents[2] / "src" / PKG

# Every subpackage plus the standalone modules a consumer can import directly.
ENTRY_MODULES = [
    "scalo",
    "scalo.cli",
    "scalo.concurrency",
    "scalo.config",
    "scalo.crypto",
    "scalo.deployment",
    "scalo.expression",
    "scalo.health",
    "scalo.http",
    "scalo.kafka",
    "scalo.logger",
    "scalo.metrics",
    "scalo.otel_backoff",
    "scalo.otel_tracing",
    "scalo.resilience",
    "scalo.runtime",
    "scalo.scaling",
    "scalo.secrets",
    "scalo.version_check",
]


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join([PKG, *parts])


def _eager_imports(path: Path, this_module: str) -> set[str]:
    """scalo imports that run at module import time, excluding lazy ones."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), str(path))
    is_package = path.name == "__init__.py"
    found: set[str] = set()

    for node in tree.body:  # top level only -- anything nested is lazy by design
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = this_module.split(".")
                # Inside a package __init__, level 1 already means the package.
                strip = node.level - 1 if is_package else node.level
                base = base[: len(base) - strip] if strip else base
                prefix = ".".join(base)
                targets = [f"{prefix}.{node.module}" if node.module else prefix]
            elif node.module:
                targets = [node.module]
        found.update(t for t in targets if t == PKG or t.startswith(f"{PKG}."))
    return found


def _owning_module(target: str, known: set[str]) -> str | None:
    """Map an imported name onto the module that defines it."""
    while target and target not in known:
        target = target.rpartition(".")[0]
    return target or None


def _import_graph() -> dict[str, set[str]]:
    files = sorted(SRC.rglob("*.py"))
    known = {_module_name(f) for f in files}
    graph: dict[str, set[str]] = {}
    for path in files:
        me = _module_name(path)
        edges = set()
        for target in _eager_imports(path, me):
            owner = _owning_module(target, known)
            if owner and owner != me:
                edges.add(owner)
        graph[me] = edges
    return graph


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Every strongly-connected component with more than one module."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    found: list[list[str]] = []

    for root in graph:
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            descended = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph.get(child, set())))))
                    descended = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if descended:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                if len(component) > 1:
                    found.append(sorted(component))
    return found


@pytest.mark.smoke
class TestNoCircularImports:
    """No module-level import cycle anywhere in the package."""

    def test_no_eager_import_cycles(self):
        graph = _import_graph()
        assert graph, "the import graph is empty -- the source tree was not found"

        cycles = _cycles(graph)
        detail = "; ".join(" -> ".join(cycle) for cycle in cycles)
        assert not cycles, f"module-level import cycle(s): {detail}"

        self_imports = sorted(name for name, edges in graph.items() if name in edges)
        assert not self_imports, f"modules importing themselves: {self_imports}"

    def test_the_detector_would_report_a_cycle(self):
        """A guard that cannot fail proves nothing, so prove it can."""
        cycles = _cycles({"a": {"b"}, "b": {"a"}, "c": set()})
        assert cycles == [["a", "b"]], f"the cycle detector missed an obvious cycle: {cycles}"


@pytest.mark.smoke
class TestImportsFirstInAFreshInterpreter:
    """Each subpackage must import when it is the FIRST scalo module loaded.

    A cycle broken by import order passes the ordinary suite, because something
    earlier has already imported the other half. Running each one alone is what
    catches it.
    """

    @pytest.mark.parametrize("module", ENTRY_MODULES)
    def test_module_imports_alone(self, module):
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0 and "No module named" in result.stderr:
            pytest.skip(f"{module} needs an extra that is not installed")
        assert result.returncode == 0, f"`import {module}` failed alone:\n{result.stderr}"
