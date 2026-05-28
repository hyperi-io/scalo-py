#  Project:   hyperi-pylib
#  File:      tests/smoke/test_startup.py
#  Purpose:   Startup smoke test -- catches init panics, broken imports, missing defaults
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED
"""Smoke tests for hyperi-pylib core module imports and basic functionality.

These run on every push. If any of these fail, something fundamental is broken.
"""

import pytest


@pytest.mark.smoke
class TestCoreImports:
    """Verify all core modules import without error."""

    def test_import_root(self):
        import hyperi_pylib

        assert hasattr(hyperi_pylib, "__version__")

    def test_import_logger(self):
        from hyperi_pylib.logger import logger

        assert logger is not None

    def test_import_config(self):
        from hyperi_pylib.config import settings

        assert settings is not None

    def test_import_runtime(self):
        from hyperi_pylib.runtime import get_runtime_paths

        try:
            paths = get_runtime_paths("smoke-test")
            assert paths is not None
        except RuntimeError:
            pytest.skip("Runtime paths require writable /app/data (CI container)")

    def test_import_database(self):
        from hyperi_pylib.database import build_database_url

        assert callable(build_database_url)

    def test_import_cli(self):
        from hyperi_pylib.cli import DfeApp, VersionInfo

        assert DfeApp is not None
        assert VersionInfo is not None


@pytest.mark.smoke
class TestCoreDefaults:
    """Verify core components work with default configuration."""

    def test_logger_emits_without_crash(self):
        from hyperi_pylib.logger import logger

        logger.debug("Smoke test log entry")

    def test_config_has_defaults(self):
        from hyperi_pylib.config import settings

        assert settings is not None

    def test_runtime_paths_resolve(self):
        from hyperi_pylib.runtime import get_runtime_paths

        try:
            paths = get_runtime_paths("smoke-test")
            assert paths.cache_dir is not None
            assert paths.config_dir is not None
        except RuntimeError:
            pytest.skip("Runtime paths require writable /app/data (CI container)")

    def test_version_info_from_env(self):
        from hyperi_pylib.cli import VersionInfo

        vi = VersionInfo.from_env("test-service", "0.0.1")
        assert vi.name == "test-service"
        assert vi.version == "0.0.1"


@pytest.mark.smoke
class TestOptionalExtras:
    """Verify optional extras import without error when installed."""

    def test_import_metrics(self):
        try:
            from hyperi_pylib.metrics import create_metrics

            assert callable(create_metrics)
        except ImportError:
            pytest.skip("metrics extra not installed")

    def test_import_http(self):
        try:
            from hyperi_pylib.http import create_client

            assert callable(create_client)
        except ImportError:
            pytest.skip("http extra not installed")

    def test_import_cache(self):
        try:
            from hyperi_pylib.cache import PostgresCache

            assert PostgresCache is not None
        except ImportError:
            pytest.skip("cache extra not installed")

    def test_import_expression(self):
        try:
            from hyperi_pylib.expression import evaluate

            assert callable(evaluate)
        except ImportError:
            pytest.skip("expression extra not installed")
