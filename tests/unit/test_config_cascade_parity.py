"""Parity tests for config cascade alignment with scalo-rs.

These tests verify that scalo's config cascade behaviour matches
scalo-rs's implementation per the unified spec.
"""

import os
import subprocess
import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import patch

import pytest


class TestAppEnvDetection:
    """Test get_app_env() matches scalo-rs's detection chain."""

    def test_app_env_from_app_env_var(self, monkeypatch):
        """APP_ENV takes highest priority."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_from_environment_var(self, monkeypatch):
        """ENVIRONMENT is second priority."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "staging"

    def test_app_env_from_env_var(self, monkeypatch):
        """ENV is third priority."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("ENV", "testing")

        from scalo.config.config import get_app_env

        assert get_app_env() == "testing"

    def test_app_env_default_development(self, monkeypatch):
        """Default falls back to 'development'."""
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "development"

    def test_app_env_priority_order(self, monkeypatch):
        """APP_ENV wins over ENVIRONMENT and ENV."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("ENV", "testing")

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_strips_leading_whitespace(self, monkeypatch):
        """A padded value is trimmed, matching scalo-rs."""
        monkeypatch.setenv("APP_ENV", " production")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_strips_trailing_whitespace(self, monkeypatch):
        """A trailing newline is trimmed, matching scalo-rs."""
        monkeypatch.setenv("APP_ENV", "production\n")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_blank_falls_through(self, monkeypatch):
        """A blank APP_ENV is treated as unset, falling through to ENVIRONMENT."""
        monkeypatch.setenv("APP_ENV", "")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_whitespace_only_falls_through(self, monkeypatch):
        """A whitespace-only APP_ENV is treated as unset."""
        monkeypatch.setenv("APP_ENV", "   ")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ENV", raising=False)

        from scalo.config.config import get_app_env

        assert get_app_env() == "production"

    def test_app_env_all_blank_defaults_to_development(self, monkeypatch):
        """All three variables blank still defaults to 'development'."""
        monkeypatch.setenv("APP_ENV", "")
        monkeypatch.setenv("ENVIRONMENT", "  ")
        monkeypatch.setenv("ENV", "")

        from scalo.config.config import get_app_env

        assert get_app_env() == "development"


def _set_invocation(monkeypatch, argv, orig_argv=None, main_spec_name=None):
    """Make the interpreter look as if it was started with ``argv``."""
    main = types.ModuleType("__main__")
    main.__spec__ = ModuleSpec(main_spec_name, None) if main_spec_name else None
    monkeypatch.setitem(sys.modules, "__main__", main)
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "orig_argv", orig_argv if orig_argv is not None else ["/usr/bin/python3", *argv])


class TestAppNameDetection:
    """Test get_app_name(): explicit name first, then the program name, never an import scan."""

    @pytest.fixture(autouse=True)
    def _no_app_name(self, monkeypatch):
        monkeypatch.delenv("APP_NAME", raising=False)

    def test_app_name_from_env(self, monkeypatch):
        """APP_NAME takes highest priority."""
        monkeypatch.setenv("APP_NAME", "myapp")
        _set_invocation(monkeypatch, ["/opt/tools/other_tool.py"])

        from scalo.config.config import get_app_name

        assert get_app_name() == "myapp"

    def test_prefixed_app_name(self, monkeypatch):
        """<PREFIX>_APP_NAME is used when APP_NAME is unset."""
        from scalo._env_compat import set_env_prefix
        from scalo.config.config import get_app_name

        set_env_prefix("MYAPP")
        monkeypatch.setenv("MYAPP_APP_NAME", "prefixed")
        _set_invocation(monkeypatch, ["/opt/tools/other_tool.py"])

        assert get_app_name() == "prefixed"

    def test_python_dash_c_gives_default(self, monkeypatch):
        """``python -c`` names no program, so the default applies and ``-c`` never becomes a name."""
        _set_invocation(monkeypatch, ["-c"])

        from scalo.config.config import get_app_name

        assert get_app_name() == "app"

    def test_empty_argv0_gives_default(self, monkeypatch):
        """An interactive or embedded interpreter has an empty argv[0]."""
        _set_invocation(monkeypatch, [""])

        from scalo.config.config import get_app_name

        assert get_app_name() == "app"

    def test_dash_m_while_the_package_imports(self, monkeypatch):
        """While ``python -m my_pkg.cli`` locates the module, argv[0] is ``-m`` and argv holds only user args."""
        _set_invocation(
            monkeypatch,
            ["-m", "serve", "--port", "1"],
            orig_argv=["/usr/bin/python3", "-X", "utf8", "-m", "my_pkg.cli", "serve", "--port", "1"],
        )

        from scalo.config.config import get_app_name

        assert get_app_name() == "my-pkg"

    def test_dash_m_joined_form(self, monkeypatch):
        """``-Bmmy_pkg`` names the module in the same token as the flag."""
        _set_invocation(monkeypatch, ["-m", "serve"], orig_argv=["/usr/bin/python3", "-Bmmy_pkg", "serve"])

        from scalo.config.config import get_app_name

        assert get_app_name() == "my-pkg"

    def test_dash_m_while_main_runs(self, monkeypatch):
        """Once ``__main__.py`` runs, argv[0] is its path and ``__main__.__spec__`` names the package."""
        _set_invocation(
            monkeypatch,
            ["/srv/my_pkg/__main__.py", "serve"],
            orig_argv=["/usr/bin/python3", "-m", "my_pkg", "serve"],
            main_spec_name="my_pkg.__main__",
        )

        from scalo.config.config import get_app_name

        assert get_app_name() == "my-pkg"

    def test_script_path_gives_stem(self, monkeypatch):
        """A script or console entry point is named by its stem."""
        _set_invocation(monkeypatch, ["/opt/tools/data_sync.py", "--once"])

        from scalo.config.config import get_app_name

        assert get_app_name() == "data-sync"

    def test_pytest_is_not_an_app_name(self, monkeypatch):
        """Test runners and the bare interpreter are skipped."""
        _set_invocation(monkeypatch, ["/venv/bin/pytest", "tests/"])

        from scalo.config.config import get_app_name

        assert get_app_name() == "app"

    def test_imports_nothing_to_guess_a_name(self, monkeypatch):
        """No installed distribution is listed or imported to guess a name."""
        import importlib.metadata

        def _refuse(*args, **kwargs):
            raise AssertionError("get_app_name() must not list installed distributions")

        monkeypatch.setattr(importlib.metadata, "distributions", _refuse)
        _set_invocation(monkeypatch, ["-c"])

        from scalo.config.config import get_app_name

        before = set(sys.modules)
        assert get_app_name() == "app"
        assert set(sys.modules) - before == set()


class TestAppNameFromRealInterpreter:
    """Run a real interpreter, so argv, orig_argv and __main__ are what CPython sets."""

    @staticmethod
    def _minimal_env(home: Path, extra_path: Path | None = None) -> dict[str, str]:
        env = {"HOME": str(home), "PATH": os.defpath}
        if extra_path is not None:
            env["PYTHONPATH"] = str(extra_path)
        return env

    def test_python_dash_m_package(self, tmp_path):
        """``python -m my_pkg`` resolves to my-pkg from the package import and from __main__."""
        pkg = tmp_path / "src" / "my_pkg"
        pkg.mkdir(parents=True)
        probe = "from scalo.config.config import get_app_name\nprint(get_app_name())\n"
        (pkg / "__init__.py").write_text(probe, encoding="utf-8")
        (pkg / "__main__.py").write_text(probe, encoding="utf-8")
        home = tmp_path / "home"
        home.mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "my_pkg", "serve"],
            cwd=home,
            env=self._minimal_env(home, tmp_path / "src"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

        assert result.returncode == 0, result.stderr[-2000:]
        assert result.stdout.split() == ["my-pkg", "my-pkg"]

    def test_import_with_dash_c_writes_nothing_under_home(self, tmp_path):
        """``python -c 'import scalo.config'`` with no APP_NAME names the app "app" and leaves HOME empty."""
        home = tmp_path / "home"
        home.mkdir()

        result = subprocess.run(
            [sys.executable, "-c", "import scalo.config.config as c; print(c.APP_NAME)"],
            cwd=home,
            env=self._minimal_env(home),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

        assert result.returncode == 0, result.stderr[-2000:]
        assert result.stdout.strip() == "app"
        assert sorted(p.name for p in home.iterdir()) == []


class TestLogFormatDefault:
    """Test log_format default matches scalo-rs's 'auto'."""

    def test_log_format_default_is_auto(self, monkeypatch):
        """Default log_format should be 'auto' (matches scalo-rs)."""
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        from scalo.config.config import get_logging_config

        config = get_logging_config()
        assert config["format"] == "auto"

    def test_log_format_env_override(self, monkeypatch):
        """LOG_FORMAT env var overrides default."""
        monkeypatch.setenv("LOG_FORMAT", "json")

        from scalo.config.config import get_logging_config

        config = get_logging_config()
        assert config["format"] == "json"


class TestLogLevelDefault:
    """Test log_level default matches scalo-rs's 'info'."""

    def test_log_level_default_is_info(self, monkeypatch):
        """Default log_level should be 'INFO' (matches scalo-rs 'info')."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        from scalo.config.config import get_logging_config

        config = get_logging_config()
        assert config["level"].lower() == "info"


class TestDotenvCascadeDefault:
    """Test .env cascade is opt-in (disabled by default)."""

    def test_dotenv_cascade_disabled_by_default(self, monkeypatch):
        """Home .env loading must be opt-in (matches scalo-rs load_home_dotenv=false)."""
        monkeypatch.delenv("DOTENV_CASCADE", raising=False)

        from scalo.config.config import _DOTENV_CASCADE_ENABLED

        assert not _DOTENV_CASCADE_ENABLED


class TestMultiLayerFileDiscovery:
    """Test that config file discovery searches multiple locations."""

    def test_find_config_files_searches_cwd(self, tmp_path, monkeypatch):
        """Should find config files in current directory."""
        monkeypatch.chdir(tmp_path)
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert str(defaults_file.resolve()) in found

    def test_find_config_files_searches_config_subdir(self, tmp_path, monkeypatch):
        """Should find config files in ./config/ subdirectory."""
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        settings_file = config_dir / "settings.yaml"
        settings_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("settings")
        assert str(settings_file.resolve()) in found

    def test_find_config_files_checks_both_extensions(self, tmp_path, monkeypatch):
        """Should check both .yaml and .yml extensions."""
        monkeypatch.chdir(tmp_path)
        yml_file = tmp_path / "defaults.yml"
        yml_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert str(yml_file.resolve()) in found

    def test_find_config_files_no_duplicates(self, tmp_path, monkeypatch):
        """Should not include duplicate paths."""
        monkeypatch.chdir(tmp_path)
        defaults_file = tmp_path / "defaults.yaml"
        defaults_file.write_text("key: value\n")

        from scalo.config.config import _find_config_files

        found = _find_config_files("defaults")
        assert len(found) == len(set(found))


class TestGetAppEnvExport:
    """Test that get_app_env is properly exported."""

    def test_get_app_env_importable(self):
        """get_app_env should be importable from scalo.config."""
        from scalo.config import get_app_env

        assert callable(get_app_env)
