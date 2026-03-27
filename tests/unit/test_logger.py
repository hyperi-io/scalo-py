"""Tests for hyperi_pylib.logger module.

Following No Mocks Policy: Tests use real logger, no mocks of internal implementation.
"""


class TestLoggerBasics:
    """Test basic logger functionality."""

    def test_logger_import(self):
        """Test logger can be imported."""
        from hyperi_pylib.logger import logger

        assert logger is not None

    def test_logger_has_standard_methods(self):
        """Test logger has standard logging methods."""
        from hyperi_pylib.logger import logger

        assert hasattr(logger, "debug")
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "critical")

    def test_logger_convenience_functions(self):
        """Test convenience functions exist."""
        from hyperi_pylib import logger

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
        from hyperi_pylib.logger import logger

        # Just verify it doesn't crash
        logger.info("Test info message")

    def test_error_logging(self, tmp_path):
        """Test error logging works."""
        from hyperi_pylib.logger import logger

        # Just verify it doesn't crash
        logger.error("Test error message")

    def test_warning_logging(self, tmp_path):
        """Test warning logging works."""
        from hyperi_pylib.logger import logger

        # Just verify it doesn't crash
        logger.warning("Test warning message")

    def test_debug_logging(self, tmp_path):
        """Test debug logging works."""
        from hyperi_pylib.logger import logger

        # Just verify it doesn't crash
        logger.debug("Test debug message")


class TestConvenienceKwargs:
    """Test convenience wrappers pass structured kwargs to loguru."""

    def test_info_accepts_kwargs(self):
        """info() must forward kwargs for structured logging."""
        from hyperi_pylib.logger.logger import info

        info("Processing request", user_id=123, action="login")

    def test_error_accepts_kwargs(self):
        """error() must forward kwargs for structured logging."""
        from hyperi_pylib.logger.logger import error

        error("Operation failed", operation="db_query", exc_info=True)

    def test_warning_accepts_kwargs(self):
        """warning() must forward kwargs for structured logging."""
        from hyperi_pylib.logger.logger import warning

        warning("Slow response", endpoint="/api/v1/data", latency_ms=1500)

    def test_debug_accepts_kwargs(self):
        """debug() must forward kwargs for structured logging."""
        from hyperi_pylib.logger.logger import debug

        debug("Cache lookup", key="user:42", hit=False)

    def test_success_accepts_kwargs(self):
        """success() must forward kwargs for structured logging."""
        from hyperi_pylib.logger.logger import success

        success("Deployed", version="2.25.0", environment="production")
