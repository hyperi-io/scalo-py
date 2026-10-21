#  Project:   scalo
#  File:      tests/smoke/test_cli_openapi_extra.py
#  Purpose:   scalo.cli.openapi reads a spec alone: no FastAPI, uvicorn or mcp, and names its extra
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The generated CLI is a light install: the spec is its only input.

Each case runs in a fresh interpreter, so nothing this test process imported
earlier can hide an eager import. A package is blocked on ``sys.meta_path`` to
stand in for an install without it, the pattern ``test_api_extra`` uses.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Server-side packages the CLI must never load: the spec is all it reads.
_SERVER_MODULES = ("fastapi", "starlette", "uvicorn", "mcp", "pydantic")

_WIDGETS_SPEC = Path(__file__).resolve().parents[1] / "fixtures" / "openapi" / "widgets.yaml"

_BLOCKER = """
import importlib.abc
import sys

class _Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".", 1)[0] in {blocked!r}:
            raise ImportError(name + " blocked (simulating an install without it)")
        return None

sys.meta_path.insert(0, _Blocker())
"""


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


@pytest.mark.smoke
class TestCliOpenapiReadsOnlyTheSpec:
    def test_importing_it_loads_no_server_module(self):
        pytest.importorskip("fastapi", reason="the check needs FastAPI installed to prove it stays unloaded")
        result = _run(
            f"""
            import sys
            import scalo.cli.openapi
            loaded = sorted(m for m in sys.modules if m.split(".", 1)[0] in {_SERVER_MODULES!r})
            assert not loaded, f"import scalo.cli.openapi imported {{loaded}}"
            print("OK")
            """
        )

        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_a_cli_builds_and_runs_with_every_server_module_blocked(self):
        result = _run(
            _BLOCKER.format(blocked=set(_SERVER_MODULES))
            + f"""
from typer.testing import CliRunner
from scalo.cli.openapi import SpecCli, load_spec

cli = SpecCli(load_spec({str(_WIDGETS_SPEC)!r}), name="w")
args = ["widgets", "parts", "list", "--help"]
result = CliRunner().invoke(cli.app(args), args, prog_name="w")
assert result.exit_code == 0, result.output
print("OK", len(cli.command_paths()))
"""
        )

        assert result.returncode == 0, result.stderr
        assert "OK 9" in result.stdout

    def test_without_the_extra_it_names_it(self):
        result = _run(
            _BLOCKER.format(blocked={"jmespath"})
            + """
try:
    import scalo.cli.openapi
except ImportError as exc:
    print("MESSAGE", exc)
else:
    print("IMPORTED")
"""
        )

        assert result.returncode == 0, result.stderr
        assert "MESSAGE scalo.cli.openapi needs the 'cli' extra: pip install 'scalo[cli]'" in result.stdout

    def test_base_scalo_and_the_service_framework_need_neither(self):
        result = _run(
            _BLOCKER.format(blocked={"jmespath"})
            + """
import sys
import scalo
from scalo.cli import ServiceApp
assert "scalo.cli.openapi" not in sys.modules
print("OK", ServiceApp is not None)
"""
        )

        assert result.returncode == 0, result.stderr
        assert "OK True" in result.stdout
