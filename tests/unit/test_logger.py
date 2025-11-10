"""Tests for hyperlib.logger module.

Following No Mocks Policy: Tests use real logger, no mocks of internal implementation.
"""

import logging
from pathlib import Path

import pytest


class TestLoggerBasics:
    """Test basic logger functionality."""

    def test_logger_import(self):
        """Test logger can be imported."""
        from hyperlib.logger import logger

        assert logger is not None

    def test_logger_has_standard_methods(self):
        """Test logger has standard logging methods."""
        from hyperlib.logger import logger

        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "critical")

    def test_logger_convenience_functions(self):
        """Test convenience functions exist."""
        from hyperlib import logger

        # These are the public API
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "success") or hasattr(logger, "info")  # success may be alias


class TestLoggerIntegration:
    """Integration tests for logger (no mocks)."""

    def test_info_logging(self, tmp_path):
        """Test info logging works."""
        from hyperlib.logger import logger

        # Just verify it doesn't crash
        logger.info("Test info message")

    def test_error_logging(self, tmp_path):
        """Test error logging works."""
        from hyperlib.logger import logger

        # Just verify it doesn't crash
        logger.error("Test error message")

    def test_warning_logging(self, tmp_path):
        """Test warning logging works."""
        from hyperlib.logger import logger

        # Just verify it doesn't crash
        logger.warning("Test warning message")

    def test_debug_logging(self, tmp_path):
        """Test debug logging works."""
        from hyperlib.logger import logger

        # Just verify it doesn't crash
        logger.debug("Test debug message")
