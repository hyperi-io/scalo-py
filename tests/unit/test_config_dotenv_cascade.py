"""Unit tests for .env cascade functionality."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scalo.cli.app import ServiceApp
from scalo.cli.version_info import VersionInfo

# Prints every os.environ key whose value differs before and after importing the module in argv[1].
_IMPORT_PROBE = """
import importlib, json, os, sys
before = dict(os.environ)
importlib.import_module(sys.argv[1])
after = dict(os.environ)
print(json.dumps({k: [before.get(k), after.get(k)] for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)}))
"""

_IMPORT_PROBE_VARS = ("SCALO_IMPORT_PROBE_CWD", "SCALO_IMPORT_PROBE_HOME")


def _clear_env(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Unset each name and restore its original state at teardown, including absence."""
    for name in names:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def _fresh_interpreter_env(home: Path, extra: dict[str, str]) -> dict[str, str]:
    """Return a child environment without the probe, dotenv control or suite logging variables."""
    env = dict(os.environ)
    for name in (
        *_IMPORT_PROBE_VARS,
        "DOTENV_CASCADE",
        "ENV_PREFIX",
        "AUTO_LOGGER_CONFIG",
        "NO_LOGGER_CONFIG",
        "LOG_LEVEL",
        "DEBUG",
    ):
        env.pop(name, None)
    env["HOME"] = str(home)
    env.update(extra)
    return env


class TestImportLoadsNoDotenv:
    """Importing scalo leaves os.environ alone, and the .env layer loads only when the app asks."""

    @pytest.mark.parametrize("module", ["scalo", "scalo.config", "scalo.logger"])
    @pytest.mark.parametrize(
        "extra_env",
        [{}, {"DOTENV_CASCADE": "true", "AUTO_LOGGER_CONFIG": "1"}],
        ids=["defaults", "cascade-and-auto-logger"],
    )
    def test_import_leaves_environ_unchanged(self, tmp_path, module, extra_env):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / ".env").write_text("SCALO_IMPORT_PROBE_CWD=planted\n", encoding="utf-8")
        (fake_home / ".env").write_text("SCALO_IMPORT_PROBE_HOME=planted\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-c", _IMPORT_PROBE, module],
            cwd=work_dir,
            env=_fresh_interpreter_env(fake_home, extra_env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        changed = json.loads(result.stdout.strip().splitlines()[-1])
        assert changed == {}

    def test_get_config_loads_dotenv_from_working_directory(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("SCALO_GET_CONFIG_PROBE=planted\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _clear_env(monkeypatch, "SCALO_GET_CONFIG_PROBE")

        from scalo.config import get_config

        config = get_config(load_dotenv=True, merge_existing=False)

        # Bound first so a failure prints the value, not all of os.environ.
        loaded = os.environ.get("SCALO_GET_CONFIG_PROBE")
        assert loaded == "planted"
        assert config.get("SCALO_GET_CONFIG_PROBE") == "planted"

    def test_get_config_honours_dotenv_cascade_flag(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".env").write_text("SCALO_HOME_DOTENV_PROBE=from-home\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("DOTENV_CASCADE", "true")
        _clear_env(monkeypatch, "SCALO_HOME_DOTENV_PROBE")

        from scalo.config import get_config

        get_config(merge_existing=False)

        loaded = os.environ.get("SCALO_HOME_DOTENV_PROBE")
        assert loaded == "from-home"

    def test_settings_read_before_the_load_sees_dotenv_after_it(self, tmp_path):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (tmp_path / ".env").write_text("SCALO_SETTINGS_PROBE=planted\n", encoding="utf-8")
        probe = (
            "from scalo.config import get_config, settings\n"
            "settings.get('ANY_KEY')\n"
            "get_config()\n"
            "print(settings.get('SCALO_SETTINGS_PROBE'))\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=tmp_path,
            env=_fresh_interpreter_env(fake_home, {}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == "planted"


class _DotenvApp(ServiceApp):
    """Minimal service for driving the CLI entry point."""

    name = "dotenv-probe"
    env_prefix = "DOTENV_PROBE"

    def version_info(self) -> VersionInfo:
        return VersionInfo(self.name, "0.0.1")

    def run_service(self, config: Any) -> None:
        pass


class TestServiceAppLoadsDotenv:
    """ServiceApp.cli() loads ./.env before its env-backed flags are parsed."""

    def test_dotenv_reaches_env_backed_flags(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("METRICS_ADDR=127.0.0.1:19097\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        _clear_env(monkeypatch, "METRICS_ADDR", "LOG_LEVEL", "LOG_FORMAT")
        app = _DotenvApp()

        # No capsys: config-check installs a logger sink on sys.stderr, which must outlive this test.
        with pytest.raises(SystemExit) as exit_info:
            app.cli(["config-check"])

        assert exit_info.value.code == 0
        assert app._common_args.metrics_addr == "127.0.0.1:19097"


class TestDotenvCascade:
    """Tests for .env cascade loading."""

    def test_load_dotenv_cascade_default_order(self, tmp_path, monkeypatch):
        """Test default cascade order: home -> project."""
        # Create fake home and project directories
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create .env files
        home_env = fake_home / ".env"
        home_env.write_text("API_KEY=home-key\nDEBUG=false\nHOME_ONLY=yes\n")

        project_env = project_dir / ".env"
        project_env.write_text("DEBUG=true\nPROJECT_ONLY=yes\n")

        # Change to project directory and set home
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("HOME", str(fake_home))

        # Clear any existing env vars
        for key in ["API_KEY", "DEBUG", "HOME_ONLY", "PROJECT_ONLY"]:
            monkeypatch.delenv(key, raising=False)

        # Import and test
        from scalo.config.config import _load_dotenv_cascade

        _load_dotenv_cascade([str(home_env), str(project_env)])

        # Home values should be loaded
        assert os.environ.get("API_KEY") == "home-key"
        assert os.environ.get("HOME_ONLY") == "yes"

        # Project values should override home
        assert os.environ.get("DEBUG") == "true"  # Overridden
        assert os.environ.get("PROJECT_ONLY") == "yes"

    def test_load_dotenv_cascade_missing_files(self, tmp_path, monkeypatch):
        """Test cascade handles missing files gracefully."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Only create project .env
        project_env = project_dir / ".env"
        project_env.write_text("ONLY_PROJECT=value\n")

        monkeypatch.chdir(project_dir)
        monkeypatch.delenv("ONLY_PROJECT", raising=False)

        from scalo.config.config import _load_dotenv_cascade

        # Should not raise even if home .env doesn't exist
        _load_dotenv_cascade(
            [
                str(tmp_path / "nonexistent" / ".env"),
                str(project_env),
            ]
        )

        assert os.environ.get("ONLY_PROJECT") == "value"

    def test_load_dotenv_cascade_custom_files(self, tmp_path, monkeypatch):
        """Test custom .env file list."""
        # Create multiple config files
        system_env = tmp_path / "etc" / "app" / ".env"
        system_env.parent.mkdir(parents=True)
        system_env.write_text("LEVEL=system\nSYSTEM_VAR=yes\n")

        user_env = tmp_path / "user" / ".env"
        user_env.parent.mkdir()
        user_env.write_text("LEVEL=user\nUSER_VAR=yes\n")

        project_env = tmp_path / "project" / ".env"
        project_env.parent.mkdir()
        project_env.write_text("LEVEL=project\nPROJECT_VAR=yes\n")

        # Clear env vars
        for key in ["LEVEL", "SYSTEM_VAR", "USER_VAR", "PROJECT_VAR"]:
            monkeypatch.delenv(key, raising=False)

        from scalo.config.config import _load_dotenv_cascade

        # Load in order: system -> user -> project
        _load_dotenv_cascade(
            [
                str(system_env),
                str(user_env),
                str(project_env),
            ]
        )

        # Project has highest priority (loaded last)
        assert os.environ.get("LEVEL") == "project"
        # All files contribute unique vars
        assert os.environ.get("SYSTEM_VAR") == "yes"
        assert os.environ.get("USER_VAR") == "yes"
        assert os.environ.get("PROJECT_VAR") == "yes"

    def test_get_config_with_dotenv_cascade(self, tmp_path, monkeypatch):
        """Test get_config with dotenv_cascade=True."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create .env files
        home_env = fake_home / ".env"
        home_env.write_text("CASCADE_TEST_HOME=from-home\n")

        project_env = project_dir / ".env"
        project_env.write_text("CASCADE_TEST_PROJECT=from-project\n")

        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.delenv("CASCADE_TEST_HOME", raising=False)
        monkeypatch.delenv("CASCADE_TEST_PROJECT", raising=False)

        from scalo.config import get_config

        # Use custom dotenv_files since we're in a test environment
        get_config(
            dotenv_files=[str(home_env), str(project_env)],
            merge_existing=False,
        )

        # Verify env vars were loaded (they're now in os.environ)
        assert os.environ.get("CASCADE_TEST_HOME") == "from-home"
        assert os.environ.get("CASCADE_TEST_PROJECT") == "from-project"

    def test_get_config_with_custom_dotenv_files(self, tmp_path, monkeypatch):
        """Test get_config with explicit dotenv_files list."""
        env1 = tmp_path / "env1"
        env1.write_text("CUSTOM_FILE_1=value1\nSHARED=from-file1\n")

        env2 = tmp_path / "env2"
        env2.write_text("CUSTOM_FILE_2=value2\nSHARED=from-file2\n")

        for key in ["CUSTOM_FILE_1", "CUSTOM_FILE_2", "SHARED"]:
            monkeypatch.delenv(key, raising=False)

        from scalo.config import get_config

        get_config(
            dotenv_files=[str(env1), str(env2)],
            merge_existing=False,
        )

        # Both files loaded
        assert os.environ.get("CUSTOM_FILE_1") == "value1"
        assert os.environ.get("CUSTOM_FILE_2") == "value2"
        # Later file wins
        assert os.environ.get("SHARED") == "from-file2"

    def test_default_reads_no_env_above_the_working_directory(self, tmp_path, monkeypatch):
        """Only ./.env loads by default, even with .env files in every parent."""
        fake_home = tmp_path / "home"
        project_dir = fake_home / "project"
        work_dir = project_dir / "sub"
        work_dir.mkdir(parents=True)
        (fake_home / ".env").write_text("WALKUP_HOME=loaded\n")
        (project_dir / ".env").write_text("WALKUP_PARENT=loaded\n")

        monkeypatch.chdir(work_dir)
        monkeypatch.setenv("HOME", str(fake_home))
        for key in ["WALKUP_HOME", "WALKUP_PARENT"]:
            monkeypatch.delenv(key, raising=False)

        from scalo.config import get_config

        get_config(merge_existing=False).get("ANY_KEY")

        assert os.environ.get("WALKUP_HOME") is None
        assert os.environ.get("WALKUP_PARENT") is None

    def test_default_reads_env_in_the_working_directory(self, tmp_path, monkeypatch):
        """./.env loads by default and a real exported variable still wins."""
        (tmp_path / ".env").write_text("CWD_ONLY=from-dotenv\nCWD_SHARED=from-dotenv\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CWD_ONLY", raising=False)
        monkeypatch.setenv("CWD_SHARED", "from-env")

        from scalo.config import get_config

        config = get_config(merge_existing=False)

        assert os.environ.get("CWD_ONLY") == "from-dotenv"
        assert config.get("CWD_SHARED") == "from-env"

    def test_load_dotenv_false_reads_nothing(self, tmp_path, monkeypatch):
        """load_dotenv=False skips ./.env."""
        (tmp_path / ".env").write_text("SKIPPED_DOTENV=loaded\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("SKIPPED_DOTENV", raising=False)

        from scalo.config import get_config

        get_config(merge_existing=False, load_dotenv=False).get("ANY_KEY")

        assert os.environ.get("SKIPPED_DOTENV") is None


class TestDefaultDotenvFiles:
    """The file list get_config and ServiceApp load from."""

    def test_cascade_off_is_working_directory_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        from scalo.config.config import _default_dotenv_files

        assert _default_dotenv_files(cascade=False) == [str(tmp_path / ".env")]

    def test_cascade_on_puts_home_beneath_working_directory(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(fake_home))

        from scalo.config.config import _default_dotenv_files

        assert _default_dotenv_files(cascade=True) == [
            str(fake_home / ".env"),
            str(tmp_path / ".env"),
        ]
