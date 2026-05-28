# Project:   hyperi-pylib
# File:      examples/basic-logging/tests/test_main.py
# Purpose:   Tests for basic-logging example
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for basic-logging example."""

import sys
from io import StringIO

import pytest
from main import (
    demonstrate_log_levels,
    demonstrate_logger_object,
    demonstrate_structured_logging,
    main,
    process_user,
)


class TestProcessUser:
    """Tests for process_user function."""

    def test_login_returns_true(self) -> None:
        """Login action should return True."""
        assert process_user(123, "login") is True

    def test_logout_returns_true(self) -> None:
        """Logout action should return True."""
        assert process_user(456, "logout") is True

    def test_unknown_action_returns_false(self) -> None:
        """Unknown action should return False."""
        assert process_user(789, "unknown") is False


class TestDemonstrations:
    """Tests for demonstration functions."""

    def test_demonstrate_log_levels_runs(self) -> None:
        """Log levels demonstration should run without error."""
        demonstrate_log_levels()

    def test_demonstrate_structured_logging_runs(self) -> None:
        """Structured logging demonstration should run without error."""
        demonstrate_structured_logging()

    def test_demonstrate_logger_object_runs(self) -> None:
        """Logger object demonstration should run without error."""
        demonstrate_logger_object()


class TestMain:
    """Tests for main function."""

    def test_main_runs_without_error(self, capsys: pytest.CaptureFixture) -> None:
        """Main function should run and produce output."""
        main()
        captured = capsys.readouterr()
        assert "Log Levels" in captured.out
        assert "Structured Logging" in captured.out
        assert "User Processing" in captured.out
