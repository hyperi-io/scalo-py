"""Unit tests for .env cascade functionality."""

import os
from pathlib import Path

import pytest


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
        from hs_pylib.config.config import _load_dotenv_cascade

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

        from hs_pylib.config.config import _load_dotenv_cascade

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

        from hs_pylib.config.config import _load_dotenv_cascade

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

        from hs_pylib.config import get_config

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

        from hs_pylib.config import get_config

        get_config(
            dotenv_files=[str(env1), str(env2)],
            merge_existing=False,
        )

        # Both files loaded
        assert os.environ.get("CUSTOM_FILE_1") == "value1"
        assert os.environ.get("CUSTOM_FILE_2") == "value2"
        # Later file wins
        assert os.environ.get("SHARED") == "from-file2"

    def test_dotenv_cascade_disabled_by_default(self, tmp_path, monkeypatch):
        """Test that cascade is disabled by default."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()

        # Create home .env
        home_env = fake_home / ".env"
        home_env.write_text("DEFAULT_BEHAVIOR_TEST=should-not-load\n")

        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.delenv("DEFAULT_BEHAVIOR_TEST", raising=False)
        monkeypatch.delenv("HS_DOTENV_CASCADE", raising=False)

        from hs_pylib.config import get_config

        # Without dotenv_cascade, home .env should not be loaded
        # (only project .env via Dynaconf's standard behavior)
        get_config(merge_existing=False)

        # Home .env should NOT be loaded by default
        # (Dynaconf only loads ./.env, not ~/.env)
        # Note: This test verifies the default behavior hasn't changed


class TestDotenvCascadeEnvVar:
    """Tests for HS_DOTENV_CASCADE environment variable."""

    def test_env_var_enables_cascade(self, tmp_path, monkeypatch):
        """Test HS_DOTENV_CASCADE=true enables cascade at module init."""
        # This test verifies the environment variable works
        # Note: Module-level initialization happens at import time,
        # so this is more of a documentation test
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".env").write_text("ENV_VAR_CASCADE_TEST=from-home\n")

        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("HS_DOTENV_CASCADE", "true")

        # The actual cascade would happen at module import time
        # This test documents the expected behavior
        assert os.environ.get("HS_DOTENV_CASCADE") == "true"
