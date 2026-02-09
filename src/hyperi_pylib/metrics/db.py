# Project:   hyperi-pylib
# File:      metrics/db.py
# Purpose:   Database query metrics helpers (context manager and decorator)
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Database query metrics helpers for explicit instrumentation.

Provides context manager and decorator for tracking DB query metrics
with any database client (ClickHouse, Postgres, Redis, etc.).

Quick Start:
    >>> from hyperi_pylib.metrics import create_metrics
    >>> from hyperi_pylib.metrics.db import db_query, track_db_query
    >>>
    >>> metrics = create_metrics("myapp")
    >>>
    >>> # Context manager
    >>> with db_query(metrics, "postgres", "select"):
    ...     result = cursor.execute("SELECT * FROM users")
    >>>
    >>> # Decorator
    >>> @track_db_query(metrics, db_type="clickhouse")
    ... def run_analytics_query(query: str):
    ...     return ch_client.execute(query)

Metrics Exposed:
    - db_query_duration_seconds: Histogram with labels [db_type, operation, status]
    - db_query_total: Counter with labels [db_type, operation, status]
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Generator, TypeVar

if TYPE_CHECKING:
    from .manager import MetricsManager

T = TypeVar("T")

# Module-level metrics cache to avoid recreating metrics
_metrics_cache: dict[int, tuple[Any, Any]] = {}


def _get_db_metrics(metrics: MetricsManager) -> tuple[Any, Any]:
    """Get or create DB metrics for a MetricsManager instance.

    Args:
        metrics: MetricsManager instance

    Returns:
        Tuple of (duration_histogram, query_counter)
    """
    cache_key = id(metrics)
    if cache_key not in _metrics_cache:
        duration = metrics.histogram(
            "db_query_duration_seconds",
            "Database query duration in seconds",
            labels=["db_type", "operation", "status"],
        )
        counter = metrics.counter(
            "db_query_total",
            "Total database queries",
            labels=["db_type", "operation", "status"],
        )
        _metrics_cache[cache_key] = (duration, counter)
    return _metrics_cache[cache_key]


@contextmanager
def db_query(
    metrics: MetricsManager,
    db_type: str,
    operation: str,
) -> Generator[None, None, None]:
    """Context manager for tracking DB query metrics.

    Args:
        metrics: MetricsManager instance
        db_type: Database type (e.g., "postgres", "clickhouse", "redis")
        operation: Operation type (e.g., "select", "insert", "update", "delete")

    Yields:
        None

    Raises:
        Exception: Re-raises any exception from the wrapped code

    Usage:
        >>> with db_query(metrics, "clickhouse", "select"):
        ...     result = ch_client.execute(query)

        >>> with db_query(metrics, "postgres", "insert"):
        ...     cursor.execute("INSERT INTO users VALUES (%s)", (data,))

    Metrics recorded:
        - db_query_duration_seconds: Query execution time
        - db_query_total: Query count (success/error)
    """
    duration_metric, counter_metric = _get_db_metrics(metrics)

    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.perf_counter() - start
        duration_metric.labels(db_type=db_type, operation=operation, status=status).observe(elapsed)
        counter_metric.labels(db_type=db_type, operation=operation, status=status).inc()


def track_db_query(
    metrics: MetricsManager,
    db_type: str,
    operation: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for tracking DB query methods.

    Args:
        metrics: MetricsManager instance
        db_type: Database type (e.g., "postgres", "clickhouse", "redis")
        operation: Operation type (defaults to function name)

    Returns:
        Decorated function

    Usage:
        >>> @track_db_query(metrics, db_type="postgres")
        ... def get_user(user_id: int):
        ...     return cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

        >>> @track_db_query(metrics, db_type="clickhouse", operation="analytics")
        ... def run_report(date_range: tuple):
        ...     return ch_client.execute(report_query, date_range)

    Metrics recorded:
        - db_query_duration_seconds: Query execution time
        - db_query_total: Query count (success/error)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op = operation or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with db_query(metrics, db_type, op):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def track_db_query_async(
    metrics: MetricsManager,
    db_type: str,
    operation: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Async decorator for tracking DB query methods.

    Args:
        metrics: MetricsManager instance
        db_type: Database type (e.g., "postgres", "clickhouse", "redis")
        operation: Operation type (defaults to function name)

    Returns:
        Decorated async function

    Usage:
        >>> @track_db_query_async(metrics, db_type="postgres")
        ... async def get_user(user_id: int):
        ...     return await conn.fetch("SELECT * FROM users WHERE id = $1", user_id)

    Metrics recorded:
        - db_query_duration_seconds: Query execution time
        - db_query_total: Query count (success/error)
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        op = operation or func.__name__

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            duration_metric, counter_metric = _get_db_metrics(metrics)

            start = time.perf_counter()
            status = "success"
            try:
                return await func(*args, **kwargs)
            except Exception:
                status = "error"
                raise
            finally:
                elapsed = time.perf_counter() - start
                duration_metric.labels(db_type=db_type, operation=op, status=status).observe(elapsed)
                counter_metric.labels(db_type=db_type, operation=op, status=status).inc()

        return wrapper

    return decorator
