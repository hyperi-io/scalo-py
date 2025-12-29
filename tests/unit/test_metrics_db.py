# Project:   hs-pylib
# File:      tests/unit/test_metrics_db.py
# Purpose:   Unit tests for hs_pylib.metrics.db module
# Language:  Python
#
# License:   LicenseRef-HyperSec-EULA
# Copyright: (c) 2025 HyperSec

"""Unit tests for hs_pylib.metrics.db module."""

import pytest
from unittest.mock import MagicMock, patch


class TestDbQueryContextManager:
    """Tests for db_query context manager."""

    def test_import(self):
        """Test that db_query can be imported."""
        from hs_pylib.metrics.db import db_query

        assert db_query is not None

    def test_records_success_metrics(self):
        """Test context manager records success metrics."""
        from hs_pylib.metrics.db import db_query, _metrics_cache

        # Clear cache for clean test
        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_duration = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=mock_duration)
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        with db_query(mock_metrics, "postgres", "select"):
            pass  # Simulate successful query

        # Verify metrics were recorded
        mock_duration.labels.assert_called_with(
            db_type="postgres", operation="select", status="success"
        )
        mock_counter.labels.assert_called_with(
            db_type="postgres", operation="select", status="success"
        )

    def test_records_error_metrics(self):
        """Test context manager records error metrics on exception."""
        from hs_pylib.metrics.db import db_query, _metrics_cache

        # Clear cache for clean test
        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_duration = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=mock_duration)
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        with pytest.raises(ValueError):
            with db_query(mock_metrics, "clickhouse", "insert"):
                raise ValueError("Test error")

        # Verify error status recorded
        mock_duration.labels.assert_called_with(
            db_type="clickhouse", operation="insert", status="error"
        )
        mock_counter.labels.assert_called_with(
            db_type="clickhouse", operation="insert", status="error"
        )

    def test_reraises_exception(self):
        """Test context manager re-raises the original exception."""
        from hs_pylib.metrics.db import db_query, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=MagicMock())
        mock_metrics.counter = MagicMock(return_value=MagicMock())

        with pytest.raises(RuntimeError, match="Original error"):
            with db_query(mock_metrics, "redis", "get"):
                raise RuntimeError("Original error")


class TestTrackDbQueryDecorator:
    """Tests for track_db_query decorator."""

    def test_import(self):
        """Test that track_db_query can be imported."""
        from hs_pylib.metrics.db import track_db_query

        assert track_db_query is not None

    def test_decorator_wraps_function(self):
        """Test decorator wraps function correctly."""
        from hs_pylib.metrics.db import track_db_query, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=MagicMock())
        mock_metrics.counter = MagicMock(return_value=MagicMock())

        @track_db_query(mock_metrics, db_type="postgres")
        def my_query(sql: str) -> str:
            return f"Result: {sql}"

        result = my_query("SELECT 1")
        assert result == "Result: SELECT 1"

    def test_decorator_preserves_function_name(self):
        """Test decorator preserves original function name."""
        from hs_pylib.metrics.db import track_db_query, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=MagicMock())
        mock_metrics.counter = MagicMock(return_value=MagicMock())

        @track_db_query(mock_metrics, db_type="postgres")
        def my_custom_query():
            pass

        assert my_custom_query.__name__ == "my_custom_query"

    def test_decorator_uses_function_name_as_operation(self):
        """Test decorator uses function name as operation by default."""
        from hs_pylib.metrics.db import track_db_query, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_duration = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=mock_duration)
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        @track_db_query(mock_metrics, db_type="postgres")
        def get_user_by_id(user_id: int):
            return {"id": user_id}

        get_user_by_id(123)

        # Verify operation is function name
        mock_duration.labels.assert_called_with(
            db_type="postgres", operation="get_user_by_id", status="success"
        )

    def test_decorator_with_custom_operation(self):
        """Test decorator with custom operation name."""
        from hs_pylib.metrics.db import track_db_query, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_duration = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=mock_duration)
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        @track_db_query(mock_metrics, db_type="clickhouse", operation="analytics")
        def run_complex_report():
            return []

        run_complex_report()

        # Verify custom operation used
        mock_duration.labels.assert_called_with(
            db_type="clickhouse", operation="analytics", status="success"
        )


class TestTrackDbQueryAsyncDecorator:
    """Tests for track_db_query_async decorator."""

    def test_import(self):
        """Test that track_db_query_async can be imported."""
        from hs_pylib.metrics.db import track_db_query_async

        assert track_db_query_async is not None

    @pytest.mark.asyncio
    async def test_async_decorator_wraps_function(self):
        """Test async decorator wraps function correctly."""
        from hs_pylib.metrics.db import track_db_query_async, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=MagicMock())
        mock_metrics.counter = MagicMock(return_value=MagicMock())

        @track_db_query_async(mock_metrics, db_type="postgres")
        async def async_query(sql: str) -> str:
            return f"Async Result: {sql}"

        result = await async_query("SELECT 1")
        assert result == "Async Result: SELECT 1"

    @pytest.mark.asyncio
    async def test_async_decorator_records_success(self):
        """Test async decorator records success metrics."""
        from hs_pylib.metrics.db import track_db_query_async, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_duration = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=mock_duration)
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        @track_db_query_async(mock_metrics, db_type="postgres")
        async def fetch_users():
            return [{"id": 1}]

        await fetch_users()

        mock_duration.labels.assert_called_with(
            db_type="postgres", operation="fetch_users", status="success"
        )

    @pytest.mark.asyncio
    async def test_async_decorator_records_error(self):
        """Test async decorator records error metrics."""
        from hs_pylib.metrics.db import track_db_query_async, _metrics_cache

        _metrics_cache.clear()

        mock_metrics = MagicMock()
        mock_duration = MagicMock()
        mock_counter = MagicMock()
        mock_metrics.histogram = MagicMock(return_value=mock_duration)
        mock_metrics.counter = MagicMock(return_value=mock_counter)

        @track_db_query_async(mock_metrics, db_type="redis")
        async def failing_query():
            raise ConnectionError("Connection lost")

        with pytest.raises(ConnectionError):
            await failing_query()

        mock_duration.labels.assert_called_with(
            db_type="redis", operation="failing_query", status="error"
        )
