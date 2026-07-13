#  Project:   scalo
#  File:      tests/smoke/test_startup.py
#  Purpose:   Startup smoke test -- catches init panics, broken imports, missing defaults
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""Smoke tests for scalo core module imports and basic functionality.

These run on every push. If any of these fail, something fundamental is broken.
"""

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.smoke
class TestCoreImports:
    """Verify all core modules import without error."""

    def test_import_root(self):
        import scalo

        assert hasattr(scalo, "__version__")

    def test_import_logger(self):
        from scalo.logger import logger

        assert logger is not None

    def test_import_config(self):
        from scalo.config import settings

        assert settings is not None

    def test_import_runtime(self):
        from scalo.runtime import get_runtime_paths

        try:
            paths = get_runtime_paths("smoke-test")
            assert paths is not None
        except RuntimeError:
            pytest.skip("Runtime paths require writable /app/data (CI container)")

    def test_import_cli(self):
        from scalo.cli import DfeApp, VersionInfo

        assert DfeApp is not None
        assert VersionInfo is not None


@pytest.mark.smoke
class TestCoreDefaults:
    """Verify core components work with default configuration."""

    def test_logger_emits_without_crash(self):
        from scalo.logger import logger

        logger.debug("Smoke test log entry")

    def test_config_has_defaults(self):
        from scalo.config import settings

        assert settings is not None

    def test_runtime_paths_resolve(self):
        from scalo.runtime import get_runtime_paths

        try:
            paths = get_runtime_paths("smoke-test")
            assert paths.cache_dir is not None
            assert paths.config_dir is not None
        except RuntimeError:
            pytest.skip("Runtime paths require writable /app/data (CI container)")

    def test_version_info_from_env(self):
        from scalo.cli import VersionInfo

        vi = VersionInfo.from_env("test-service", "0.0.1")
        assert vi.name == "test-service"
        assert vi.version == "0.0.1"


@pytest.mark.smoke
class TestOptionalExtras:
    """Verify optional extras import without error when installed."""

    def test_import_metrics(self):
        try:
            from scalo.metrics import create_metrics

            assert callable(create_metrics)
        except ImportError:
            pytest.skip("metrics extra not installed")

    def test_import_http(self):
        try:
            from scalo.http import create_client

            assert callable(create_client)
        except ImportError:
            pytest.skip("http extra not installed")

    def test_import_expression(self):
        try:
            from scalo.expression import evaluate

            assert callable(evaluate)
        except ImportError:
            pytest.skip("expression extra not installed")


@pytest.mark.smoke
class TestImportWithoutMetricsExtra:
    """`import scalo` must survive an ABSENT `[metrics]` extra (regression).

    The top-level package eagerly imports the metrics submodule, and its
    prometheus.py once did a BARE `import psutil`. psutil ships only in the
    optional `[metrics]` extra, so any consumer installing scalo without it (a CLI
    wanting just config/logging, say) could not `import scalo` at all -- the whole
    package was un-importable. prometheus_client was already guarded; psutil was
    not. This locks the fix in.

    Runs in a subprocess with both metrics deps blocked, so it holds even in a dev
    venv where psutil/prometheus_client are installed. If the guard is reverted,
    `import scalo` crashes here.
    """

    def _run_with_blocked(self, *blocked: str) -> subprocess.CompletedProcess[str]:
        code = textwrap.dedent(
            f"""
            import sys
            import importlib.abc

            _BLOCKED = {blocked!r}

            class _Blocker(importlib.abc.MetaPathFinder):
                def find_spec(self, name, path=None, target=None):
                    root = name.split(".", 1)[0]
                    if root in _BLOCKED:
                        raise ImportError(root + " blocked (simulating no [metrics] extra)")
                    return None

            sys.meta_path.insert(0, _Blocker())
            for _m in _BLOCKED:
                sys.modules.pop(_m, None)

            import scalo
            assert scalo.__version__, "scalo imported but has no __version__"

            # The metrics manager must degrade to disabled, never crash.
            from scalo.metrics import create_metrics
            m = create_metrics("regression", enable_auto_update=False)
            assert m.enabled is False, "metrics should be disabled without the extra"
            print("OK")
            """
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_import_scalo_without_psutil(self):
        # Block psutil specifically -- the exact dep the bare import needed.
        result = self._run_with_blocked("psutil", "prometheus_client")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        assert "OK" in result.stdout
