# Project:   hyperi-pylib
# File:      examples/basic-logging/main.py
# Purpose:   Demonstrate hyperi-pylib structured logging
# Language:  Python
#
# License:   FSL-1.1-ALv2
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
Basic Logging Example.

Demonstrates hyperi-pylib's structured logging with automatic environment detection.
Run with: uv run python main.py
"""

from hyperi_pylib.logger import debug, error, info, logger, success, warning


def process_user(user_id: int, action: str) -> bool:
    """Process a user action with structured logging."""
    info("Processing user", user_id=user_id, action=action)

    if action == "login":
        debug("Validating credentials", user_id=user_id)
        success("User logged in successfully", user_id=user_id)
        return True
    elif action == "logout":
        info("User logged out", user_id=user_id)
        return True
    else:
        warning("Unknown action", user_id=user_id, action=action)
        return False


def demonstrate_log_levels() -> None:
    """Show all available log levels."""
    debug("This is a debug message - verbose details")
    info("This is an info message - normal operation")
    success("This is a success message - operation completed")
    warning("This is a warning message - something to note")
    error("This is an error message - something went wrong")


def demonstrate_structured_logging() -> None:
    """Show structured key-value logging."""
    # Log with context
    info("Database query executed", table="users", rows=42, duration_ms=15.3)

    # Log with nested data (will be serialised)
    info(
        "Request processed",
        endpoint="/api/users",
        method="GET",
        status=200,
        headers={"content-type": "application/json"},
    )

    # Exception logging with traceback
    try:
        result = 1 / 0
    except ZeroDivisionError:
        error("Calculation failed", operation="division", exc_info=True)


def demonstrate_logger_object() -> None:
    """Show direct logger object usage."""
    # The logger object is Loguru's global singleton
    logger.info("Using logger object directly")
    logger.bind(request_id="abc123").info("Bound context for multiple calls")

    # Temporary context
    with logger.contextualize(user_id=456):
        logger.info("This message has user_id in context")
        logger.info("So does this one")


def main() -> None:
    """Run the logging demonstration."""
    info("Application starting", version="1.0.0")

    print("\n=== Log Levels ===")
    demonstrate_log_levels()

    print("\n=== Structured Logging ===")
    demonstrate_structured_logging()

    print("\n=== User Processing ===")
    process_user(123, "login")
    process_user(456, "logout")
    process_user(789, "unknown")

    print("\n=== Logger Object ===")
    demonstrate_logger_object()

    success("Application finished")


if __name__ == "__main__":
    main()
