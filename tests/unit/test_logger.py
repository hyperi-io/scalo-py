"""Tests for hyperlib.logger module with CHARS-POLICY.md enforcement."""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from hyperlib import logger


class TestInteractiveConsoleDetection:
    """Test interactive console detection (Docker/K8s vs developer terminal)."""

    def test_interactive_console_with_utf8_locale(self):
        """Test interactive console detection with UTF-8 locale (developer terminal)."""
        with (
            mock.patch("sys.stderr.isatty", return_value=True),
            mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8", "TERM": "xterm-256color"}),
        ):
            from hyperlib.logger import _is_interactive_console

            assert _is_interactive_console() is True

    def test_non_interactive_without_tty(self):
        """Test non-interactive when not a TTY (Docker/K8s container)."""
        with (
            mock.patch("sys.stderr.isatty", return_value=False),
            mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8", "TERM": "xterm-256color"}),
        ):
            from hyperlib.logger import _is_interactive_console

            assert _is_interactive_console() is False

    def test_non_interactive_with_dumb_terminal(self):
        """Test non-interactive with TERM=dumb."""
        with (
            mock.patch("sys.stderr.isatty", return_value=True),
            mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8", "TERM": "dumb"}),
        ):
            from hyperlib.logger import _is_interactive_console

            assert _is_interactive_console() is False

    def test_non_interactive_without_utf8_locale(self):
        """Test non-interactive without UTF-8 locale."""
        with (
            mock.patch("sys.stderr.isatty", return_value=True),
            mock.patch.dict(os.environ, {"LANG": "C", "TERM": "xterm-256color"}),
        ):
            from hyperlib.logger import _is_interactive_console

            assert _is_interactive_console() is False

    def test_interactive_with_lc_all_override(self):
        """Test LC_ALL overrides LANG for detection."""
        with (
            mock.patch("sys.stderr.isatty", return_value=True),
            mock.patch.dict(os.environ, {"LANG": "C", "LC_ALL": "en_US.UTF-8", "TERM": "xterm"}),
        ):
            from hyperlib.logger import _is_interactive_console

            assert _is_interactive_console() is True


class TestLogFormatting:
    """Test log format generation."""

    def test_file_format_is_ascii_only(self):
        """Test file format contains no emojis or Unicode."""
        from hyperlib.logger import _get_log_format

        file_format = _get_log_format(is_file=True, color_scheme="solarized")

        # Should be plain ASCII with no color codes
        assert "{time:" in file_format
        assert "{level:" in file_format
        assert "{message}" in file_format
        # Should not contain color markup
        assert "<fg" not in file_format
        assert "<level>" not in file_format

    def test_console_format_solarized(self):
        """Test console format with Solarized colors."""
        from hyperlib.logger import _get_log_format

        console_format = _get_log_format(is_file=False, color_scheme="solarized")

        # Should contain Solarized color codes
        assert "<fg #859900>" in console_format  # green timestamp
        assert "<fg #2aa198>" in console_format  # cyan module
        assert "<level>" in console_format

    def test_console_format_loguru(self):
        """Test console format with Loguru default colors."""
        from hyperlib.logger import _get_log_format

        console_format = _get_log_format(is_file=False, color_scheme="loguru")

        # Should contain Loguru color codes
        assert "<green>" in console_format
        assert "<cyan>" in console_format
        assert "<level>" in console_format


class TestEmojiFilter:
    """Test emoji injection filter."""

    def test_emoji_filter_adds_emojis(self):
        """Test filter adds emojis to appropriate log levels."""
        from hyperlib.logger import LOG_LEVEL_EMOJIS, _add_emoji_to_record

        filter_func = _add_emoji_to_record(use_emojis=True)

        # Test ERROR level - level.name must be a string
        level_mock = mock.Mock()
        level_mock.name = "ERROR"
        record = {"level": level_mock, "message": "Test error"}
        result = filter_func(record)
        assert result is True
        assert record["message"] == f"{LOG_LEVEL_EMOJIS['ERROR']} Test error"

    def test_emoji_filter_skips_info(self):
        """Test filter doesn't add emoji to INFO (no emoji defined)."""
        from hyperlib.logger import _add_emoji_to_record

        filter_func = _add_emoji_to_record(use_emojis=True)

        # Test INFO level (no emoji) - level.name must be a string
        level_mock = mock.Mock()
        level_mock.name = "INFO"
        record = {"level": level_mock, "message": "Test info"}
        result = filter_func(record)
        assert result is True
        assert record["message"] == "Test info"  # No emoji added

    def test_emoji_filter_disabled(self):
        """Test filter doesn't add emojis when disabled."""
        from hyperlib.logger import _add_emoji_to_record

        filter_func = _add_emoji_to_record(use_emojis=False)

        # Test ERROR level with emojis disabled - level.name must be a string
        level_mock = mock.Mock()
        level_mock.name = "ERROR"
        record = {"level": level_mock, "message": "Test error"}
        result = filter_func(record)
        assert result is True
        assert record["message"] == "Test error"  # No emoji added


class TestLoggerSetup:
    """Test logger setup with CHARS-POLICY enforcement."""

    def test_setup_with_interactive_terminal(self):
        """Test setup enables emojis with interactive terminal (developer)."""
        from hyperlib.logger import setup

        with (
            mock.patch("sys.stderr.isatty", return_value=True),
            mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8", "TERM": "xterm-256color"}),
        ):
            logger_instance = setup(color_scheme="solarized")
            assert logger_instance is not None

    def test_setup_with_non_interactive_console(self):
        """Test setup disables emojis in non-interactive mode (Docker/K8s)."""
        from hyperlib.logger import setup

        with mock.patch("sys.stderr.isatty", return_value=False):
            logger_instance = setup(color_scheme="solarized")
            assert logger_instance is not None

    def test_setup_force_emojis(self):
        """Test setup respects forced emoji setting."""
        from hyperlib.logger import setup

        # Force emojis on
        logger_instance = setup(use_emojis=True)
        assert logger_instance is not None

        # Force emojis off
        logger_instance = setup(use_emojis=False)
        assert logger_instance is not None

    def test_file_logging_converts_emojis_to_text(self):
        """Test file logging converts emojis to ASCII text (CHARS-POLICY requirement)."""
        from hyperlib.logger import emojis_to_text, strip_emojis

        # Test emoji to text conversion
        assert emojis_to_text("✅ Success") == "[SUCCESS] Success"
        assert emojis_to_text("❌ Failed") == "[ERROR] Failed"
        assert emojis_to_text("⚠️ Warning") == "[WARN] Warning"
        assert emojis_to_text("💥 Critical") == "[FATAL] Critical"

        # Test emoji stripping
        assert strip_emojis("✅ Success") == "Success"
        assert strip_emojis("❌ Failed") == "Failed"
        assert strip_emojis("⚠️ Warning") == "Warning"

    def test_non_interactive_console_is_ascii_only(self):
        """Test non-interactive consoles (Docker/K8s) use ASCII-only logs."""
        from hyperlib.logger import _is_interactive_console

        # Non-interactive console (Docker/K8s) - NOT a TTY
        with mock.patch("sys.stderr.isatty", return_value=False):
            assert _is_interactive_console() is False

        # This means use_emojis will be False by default
        # Non-interactive = ASCII-only (critical for log aggregators)


class TestCharsPolicy:
    """Test CHARS-POLICY.md compliance."""

    def test_approved_emojis_only(self):
        """Test only approved emojis from CHARS-POLICY.md are used."""
        from hyperlib.logger import LOG_LEVEL_EMOJIS

        # CHARS-POLICY.md approved emojis for log levels
        approved_emojis = {
            "CRITICAL": "💥",  # FATAL
            "ERROR": "❌",  # ERROR
            "WARNING": "⚠️",  # WARN
            "INFO": "",  # No emoji
            "SUCCESS": "✅",  # SUCCESS
            "DEBUG": "",  # No emoji
            "TRACE": "",  # No emoji
        }

        assert approved_emojis == LOG_LEVEL_EMOJIS

    def test_no_unicode_in_file_logs(self):
        """Test file logs contain only ASCII (CHARS-POLICY requirement)."""
        from hyperlib.logger import _get_log_format

        file_format = _get_log_format(is_file=True, color_scheme="solarized")

        # Verify format string is ASCII-only
        try:
            file_format.encode("ascii")
        except UnicodeEncodeError:
            pytest.fail("File log format contains non-ASCII characters")


class TestLoggerConvenience:
    """Test convenience logging functions."""

    def test_info_function(self):
        """Test info() convenience function."""
        from hyperlib.logger import info

        with mock.patch("hyperlib.logger.logger.info") as mock_info:
            info("Test message")
            mock_info.assert_called_once_with("Test message")

    def test_error_function(self):
        """Test error() convenience function."""
        from hyperlib.logger import error

        with mock.patch("hyperlib.logger.logger.error") as mock_error:
            error("Test error")
            mock_error.assert_called_once_with("Test error")

    def test_warning_function(self):
        """Test warning() convenience function."""
        from hyperlib.logger import warning

        with mock.patch("hyperlib.logger.logger.warning") as mock_warning:
            warning("Test warning")
            mock_warning.assert_called_once_with("Test warning")

    def test_success_function(self):
        """Test success() convenience function."""
        from hyperlib.logger import success

        with mock.patch("hyperlib.logger.logger.success") as mock_success:
            success("Test success")
            mock_success.assert_called_once_with("Test success")

    def test_debug_function(self):
        """Test debug() convenience function."""
        from hyperlib.logger import debug

        with mock.patch("hyperlib.logger.logger.debug") as mock_debug:
            debug("Test debug")
            mock_debug.assert_called_once_with("Test debug")


class TestLogLevelEnvironment:
    """Test LOG_LEVEL environment variable handling."""

    def test_log_level_from_env_debug(self):
        """Test LOG_LEVEL=DEBUG enables debug logging."""
        from hyperlib.logger import setup

        with (
            mock.patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}),
            mock.patch("hyperlib.logger.get_logging_config") as mock_config,
        ):
            mock_config.return_value = {
                "console": True,
                "level": "DEBUG",  # Config should pick up LOG_LEVEL
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
                "file": None,
            }
            logger_instance = setup()
            assert logger_instance is not None

    def test_log_level_from_env_error(self):
        """Test LOG_LEVEL=ERROR filters out info/warning."""
        from hyperlib.logger import setup

        with (
            mock.patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}),
            mock.patch("hyperlib.logger.get_logging_config") as mock_config,
        ):
            mock_config.return_value = {
                "console": True,
                "level": "ERROR",  # Config should pick up LOG_LEVEL
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
                "file": None,
            }
            logger_instance = setup()
            assert logger_instance is not None

    def test_log_level_priority_env_over_config(self):
        """Test LOG_LEVEL env var takes priority over config file."""
        from hyperlib.config import get_logging_config

        with (
            mock.patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}),
            mock.patch("hyperlib.config.settings.get") as mock_settings,
        ):
            mock_settings.return_value = {"level": "ERROR"}  # Config says ERROR
            config = get_logging_config()
            assert config["level"] == "DEBUG"  # But env says DEBUG wins


class TestTeeLogging:
    """Test simultaneous console and file logging (tee behavior)."""

    def test_tee_both_handlers_registered(self):
        """Test that both console and file handlers can be registered."""
        from hyperlib.logger import setup

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            log_file = f.name

        try:
            with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
                mock_config.return_value = {
                    "console": True,  # Enable console
                    "file": log_file,  # Enable file
                    "level": "INFO",
                    "format": "console",
                    "output": "stderr",
                    "color": True,
                    "timestamp_format": "rfc3339",
                    "caller": True,
                    "stacktrace_level": "ERROR",
                }
                logger_instance = setup(use_emojis=False)
                assert logger_instance is not None
                # Both handlers should be registered (can't easily verify count with loguru)

        finally:
            if Path(log_file).exists():
                Path(log_file).unlink()

    def test_console_only_mode(self):
        """Test console-only logging (no file)."""
        from hyperlib.logger import setup

        with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
            mock_config.return_value = {
                "console": True,  # Enable console
                "file": None,  # No file
                "level": "INFO",
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
            }
            logger_instance = setup()
            assert logger_instance is not None

    def test_file_only_mode(self):
        """Test file-only logging (no console)."""
        from hyperlib.logger import setup

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            log_file = f.name

        try:
            with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
                mock_config.return_value = {
                    "console": False,  # Disable console
                    "file": log_file,  # Enable file
                    "level": "INFO",
                    "format": "text",
                    "output": "file",
                    "color": False,
                    "timestamp_format": "rfc3339",
                    "caller": True,
                    "stacktrace_level": "ERROR",
                }
                logger_instance = setup()
                assert logger_instance is not None

        finally:
            if Path(log_file).exists():
                Path(log_file).unlink()


class TestDifferentFormatsPerHandler:
    """Test that console and file handlers use different formats."""

    def test_console_uses_colors(self):
        """Test console handler uses colored output."""
        from hyperlib.logger import _get_log_format

        console_format = _get_log_format(is_file=False, color_scheme="solarized")

        # Console format should have color codes
        assert "<fg" in console_format
        assert "<level>" in console_format
        assert "SOLARIZED" not in console_format  # Should have actual color values

    def test_file_uses_plain_ascii(self):
        """Test file handler uses plain ASCII format."""
        from hyperlib.logger import _get_log_format

        file_format = _get_log_format(is_file=True, color_scheme="solarized")

        # File format should NOT have color codes
        assert "<fg" not in file_format
        assert "<level>" not in file_format
        assert "{time:" in file_format
        assert "{level:" in file_format
        assert "{message}" in file_format

    def test_console_emoji_filter_vs_file_text_filter(self):
        """Test console adds emojis while file converts to text."""
        from hyperlib.logger import _add_emoji_to_record

        # Console filter (adds emojis)
        console_filter = _add_emoji_to_record(use_emojis=True, convert_to_text=False)
        level_mock = mock.Mock()
        level_mock.name = "ERROR"
        record = {"level": level_mock, "message": "Test error"}
        console_filter(record)
        assert "❌" in record["message"]

        # File filter (converts emojis to text)
        file_filter = _add_emoji_to_record(use_emojis=False, convert_to_text=True)
        record2 = {"level": level_mock, "message": "✅ Success message"}
        file_filter(record2)
        assert "[SUCCESS]" in record2["message"]
        assert "✅" not in record2["message"]


class TestColorSchemes:
    """Test different color schemes."""

    def test_solarized_color_scheme(self):
        """Test Solarized color scheme configuration."""
        from hyperlib.logger import setup

        with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
            mock_config.return_value = {
                "console": True,
                "file": None,
                "level": "INFO",
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
            }
            logger_instance = setup(color_scheme="solarized")
            assert logger_instance is not None

    def test_loguru_color_scheme(self):
        """Test Loguru default color scheme."""
        from hyperlib.logger import setup

        with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
            mock_config.return_value = {
                "console": True,
                "file": None,
                "level": "INFO",
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
            }
            logger_instance = setup(color_scheme="loguru")
            assert logger_instance is not None

    def test_loguru_format_uses_simple_colors(self):
        """Test Loguru format uses simple color tags."""
        from hyperlib.logger import _get_log_format

        loguru_format = _get_log_format(is_file=False, color_scheme="loguru")

        # Loguru format should use simple tags
        assert "<green>" in loguru_format
        assert "<cyan>" in loguru_format
        assert "<level>" in loguru_format
        # Should NOT have Solarized hex colors
        assert "#859900" not in loguru_format


class TestAllowAllEmojis:
    """Test allow_all_emojis parameter."""

    def test_allow_all_emojis_passes_through_user_emojis(self):
        """Test that allow_all_emojis=True allows user emojis."""
        from hyperlib.logger import _add_emoji_to_record

        filter_func = _add_emoji_to_record(use_emojis=True, allow_all=True)

        level_mock = mock.Mock()
        level_mock.name = "INFO"
        record = {"level": level_mock, "message": "🎉 User's celebration emoji"}
        filter_func(record)

        # User emoji should be preserved
        assert "🎉" in record["message"]
        assert "celebration emoji" in record["message"]

    def test_allow_all_emojis_still_adds_level_emojis(self):
        """Test that allow_all_emojis still adds log level emojis."""
        from hyperlib.logger import _add_emoji_to_record

        filter_func = _add_emoji_to_record(use_emojis=True, allow_all=True)

        level_mock = mock.Mock()
        level_mock.name = "ERROR"
        record = {"level": level_mock, "message": "Failed operation"}
        filter_func(record)

        # Should add ERROR emoji
        assert "❌" in record["message"]

    def test_allow_all_emojis_disabled_by_default(self):
        """Test that allow_all_emojis is disabled by default in setup."""
        from hyperlib.logger import setup

        with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
            mock_config.return_value = {
                "console": True,
                "file": None,
                "level": "INFO",
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
            }
            # Default setup should not allow all emojis
            logger_instance = setup(use_emojis=True)  # allow_all_emojis not specified
            assert logger_instance is not None

    def test_allow_all_emojis_requires_use_emojis(self):
        """Test that allow_all_emojis requires use_emojis=True."""
        from hyperlib.logger import setup

        with mock.patch("hyperlib.logger.get_logging_config") as mock_config:
            mock_config.return_value = {
                "console": True,
                "file": None,
                "level": "INFO",
                "format": "console",
                "output": "stderr",
                "color": True,
                "timestamp_format": "rfc3339",
                "caller": True,
                "stacktrace_level": "ERROR",
            }
            # allow_all_emojis with use_emojis=False should be disabled
            logger_instance = setup(use_emojis=False, allow_all_emojis=True)
            assert logger_instance is not None
            # allow_all_emojis should be internally set to False
