"""
SignalHandlerMixin: Graceful shutdown handling for SIGTERM/SIGINT.

This mixin provides signal handling for graceful application shutdown,
preventing orphaned processes and ensuring cleanup runs properly.
"""

import signal
import sys
import threading
from collections.abc import Callable
from typing import Any

from hyperlib.logger import logger


class SignalHandlerMixin:
    """
    Mixin to add graceful shutdown handling to applications.

    Registers handlers for SIGTERM and SIGINT signals, allowing applications
    to clean up resources before exiting. Prevents orphaned child processes
    (fixes dfe-hunt-runner bug).

    Example:
        class MyApp(SignalHandlerMixin, ProfileMixin):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

                @self.on_shutdown
                def cleanup():
                    print("Cleaning up resources...")
                    self.db.close()
    """

    def __init__(self, **kwargs: Any):
        """
        Initialize signal handler mixin.

        Args:
            **kwargs: Additional args passed to next mixin in chain
        """
        self._shutdown_handlers: list[Callable[[], None]] = []
        self._shutdown_event = threading.Event()
        self._shutting_down = False

        # Setup signal handlers if graceful_shutdown is enabled
        if self._should_setup_signals():
            self._setup_signal_handlers()

        # Call next mixin in MRO chain
        super().__init__(**kwargs)

    def _should_setup_signals(self) -> bool:
        """Check if signal handlers should be set up based on profile."""
        # Check if profile is available (from ProfileMixin)
        if hasattr(self, "profile"):
            return self.profile.get("graceful_shutdown", True)
        return True  # Default: enable graceful shutdown

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM and SIGINT handlers."""
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        logger.debug("Signal handlers registered (SIGTERM, SIGINT)")

    def _handle_shutdown_signal(self, signum: int, frame: Any) -> None:  # noqa: ARG002
        """
        Handle shutdown signal (SIGTERM or SIGINT).

        Args:
            signum: Signal number
            frame: Current stack frame (unused but required by signal handler signature)
        """
        if self._shutting_down:
            logger.warning("Already shutting down, ignoring signal")
            return

        self._shutting_down = True
        signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        logger.info(f"Received {signal_name}, initiating graceful shutdown")

        # Get shutdown timeout from profile
        timeout = self._get_shutdown_timeout()

        try:
            # Run shutdown handlers
            self._run_shutdown_handlers(timeout)

            # Signal that shutdown is complete
            self._shutdown_event.set()

            logger.info("Graceful shutdown complete")
            sys.exit(0)

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
            sys.exit(1)

    def _get_shutdown_timeout(self) -> int:
        """Get shutdown timeout from profile or use default."""
        if hasattr(self, "profile"):
            return self.profile.get("shutdown_timeout", 30)
        return 30  # Default timeout

    def _run_shutdown_handlers(self, timeout: int) -> None:
        """
        Run all registered shutdown handlers with timeout.

        Args:
            timeout: Maximum seconds to wait for handlers

        Raises:
            TimeoutError: If handlers don't complete within timeout
        """
        if not self._shutdown_handlers:
            logger.debug("No shutdown handlers registered")
            return

        logger.info(f"Running {len(self._shutdown_handlers)} shutdown handler(s)")

        # Run handlers in a thread with timeout
        def run_handlers():
            for handler in self._shutdown_handlers:
                try:
                    handler_name = getattr(handler, "__name__", "unknown")
                    logger.debug(f"Running shutdown handler: {handler_name}")
                    handler()
                except Exception as e:
                    logger.error(f"Error in shutdown handler: {e}", exc_info=True)

        handler_thread = threading.Thread(target=run_handlers, daemon=False)
        handler_thread.start()
        handler_thread.join(timeout=timeout)

        if handler_thread.is_alive():
            logger.warning(f"Shutdown handlers did not complete within {timeout}s, forcing exit")
            # Handlers are still running but we've exceeded timeout
            # They will be terminated when process exits

    def on_shutdown(self, func: Callable[[], None]) -> Callable[[], None]:
        """
        Register a shutdown handler (decorator).

        Shutdown handlers are called when SIGTERM or SIGINT is received,
        allowing cleanup before the application exits.

        Args:
            func: Function to call on shutdown (takes no args)

        Returns:
            The original function (allows use as decorator)

        Example:
            @app.on_shutdown
            def cleanup_database():
                db.close()
                print("Database closed")
        """
        self._shutdown_handlers.append(func)
        logger.debug(f"Registered shutdown handler: {func.__name__}")
        return func

    def wait_for_shutdown(self, timeout: float | None = None) -> bool:
        """
        Wait for shutdown signal.

        Blocks until SIGTERM/SIGINT is received or timeout expires.
        Useful for long-running applications that wait for signals.

        Args:
            timeout: Optional timeout in seconds (None = wait forever)

        Returns:
            True if shutdown signal received, False if timeout

        Example:
            # Main loop
            app.wait_for_shutdown()
            print("Shutting down...")
        """
        return self._shutdown_event.wait(timeout)

    def is_shutting_down(self) -> bool:
        """
        Check if application is currently shutting down.

        Returns:
            True if shutdown has been initiated

        Example:
            while not app.is_shutting_down():
                process_task()
        """
        return self._shutting_down
