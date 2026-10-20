#  Project:   scalo
#  File:      tests/smoke/test_api_extra.py
#  Purpose:   Base scalo never imports FastAPI, and scalo.api without the extra names it
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The ``api`` extra is optional: ``pip install scalo`` pulls no FastAPI and imports none.

Each case runs in a fresh interpreter, so nothing this test process imported earlier can hide an eager
import. The extra's packages are blocked on ``sys.meta_path`` to stand in for a base-only install, the
pattern ``test_startup.TestImportWithoutMetricsExtra`` uses for ``[metrics]``.
"""

import subprocess
import sys
import textwrap

import pytest

# Import roots that only the api extra brings in.
_API_EXTRA_MODULES = ("fastapi", "starlette", "pydantic", "pydantic_core")

_BLOCKER = """
import importlib.abc
import sys

class _Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".", 1)[0] in {blocked!r}:
            raise ImportError(name + " blocked (simulating no [api] extra)")
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
class TestApiExtraIsOptional:
    def test_import_scalo_loads_no_api_extra_module_even_when_installed(self):
        pytest.importorskip("fastapi", reason="the check needs FastAPI installed to prove it stays unloaded")
        result = _run(
            f"""
            import sys
            import scalo
            loaded = sorted(m for m in sys.modules if m.split(".", 1)[0] in {_API_EXTRA_MODULES!r})
            assert "scalo.api" not in sys.modules, "import scalo imported scalo.api"
            assert not loaded, f"import scalo imported {{loaded}}"
            print("OK")
            """
        )

        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout

    def test_import_scalo_works_without_the_api_extra(self):
        result = _run(
            _BLOCKER.format(blocked=set(_API_EXTRA_MODULES))
            + """
import scalo
from scalo.cli import ServiceApp
from scalo.health import HealthManager
print("OK", scalo.__version__ is not None, ServiceApp is not None, HealthManager is not None)
"""
        )

        assert result.returncode == 0, result.stderr
        assert "OK True True True" in result.stdout

    def test_scalo_api_without_the_extra_names_it(self):
        result = _run(
            _BLOCKER.format(blocked=set(_API_EXTRA_MODULES))
            + """
try:
    import scalo.api
except ImportError as exc:
    print("MESSAGE", exc)
else:
    print("IMPORTED")
"""
        )

        assert result.returncode == 0, result.stderr
        assert "MESSAGE scalo.api needs the 'api' extra: pip install 'scalo[api]'" in result.stdout
