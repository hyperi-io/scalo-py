"""
HyperLib Daemon Application
Long-running background service with scheduled tasks and worker pools
"""

import asyncio
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import MountConfig, get_mount_config
from ..logger import logger


class DaemonApplication:
    """
    Long-running daemon service application.

    Provides:
    - Scheduled task execution (e.g., run every N seconds)
    - Worker pools for parallel task processing
    - Startup and shutdown hooks
    - Graceful shutdown handling
    - Mount point management (config, data, temp)

    Example:
        app = Application.daemon(name="worker")

        @app.scheduled(interval=60)
        def check_queue():
            logger.info("Checking work queue...")
            # Process items

        @app.scheduled(interval=300)
        async def sync_data():
            logger.info("Syncing data...")
            # Async sync operation

        @app.on_startup
        def startup():
            logger.info("Starting up...")

        @app.on_shutdown
        def shutdown():
            logger.info("Shutting down...")

        app.run()
    """

    def __init__(
        self,
        name: str,
        business_logic: Any = None,
        mounts: MountConfig | None = None,
        **kwargs,
    ):
        """
        Initialize daemon application.

        Args:
            name: Application name
            business_logic: Optional business logic class with run_daemon() method
            mounts: Container mount configuration
            **kwargs: Additional options
        """
        self.name = name
        self.business_logic = business_logic
        self.scheduled_tasks: list[tuple[Callable, int]] = []  # (func, interval_seconds)
        self.startup_hooks: list[Callable] = []
        self.shutdown_hooks: list[Callable] = []
        self.shutdown_event = threading.Event()

        # Get or use mount config
        if mounts is None:
            mounts = get_mount_config()

        self.mounts = mounts

        # Aliases for backward compatibility
        self.startup = self.on_startup
        self.shutdown = self.on_shutdown

        logger.info(f"🔧 DaemonApplication '{name}' initialized")

    def scheduled(self, interval: int) -> Callable:
        """
        Decorator to register a scheduled task.

        Args:
            interval: Interval in seconds between executions

        Example:
            @app.scheduled(interval=60)
            def periodic_task():
                logger.info("Running every 60 seconds")
        """

        def decorator(func: Callable) -> Callable:
            self.scheduled_tasks.append((func, interval))
            logger.debug(f"Registered scheduled task: {func.__name__} (every {interval}s)")
            return func

        return decorator

    def on_startup(self, func: Callable) -> Callable:
        """
        Decorator to register startup hook.

        Example:
            @app.on_startup
            def startup():
                logger.info("Daemon starting...")
                # Initialize resources
        """
        self.startup_hooks.append(func)
        logger.debug(f"Registered startup hook: {func.__name__}")
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """
        Decorator to register shutdown hook.

        Example:
            @app.on_shutdown
            def shutdown():
                logger.info("Daemon stopping...")
                # Cleanup resources
        """
        self.shutdown_hooks.append(func)
        logger.debug(f"Registered shutdown hook: {func.__name__}")
        return func

    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers."""

        def signal_handler(signum, _frame):
            signal_name = signal.Signals(signum).name
            logger.info(f"Received {signal_name}, initiating graceful shutdown...")
            self.shutdown_event.set()

        # Register handlers for graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C

        logger.info("Signal handlers registered")

    def _run_scheduled_task(self, func: Callable, interval: int):
        """Run a single scheduled task in a loop."""
        while not self.shutdown_event.is_set():
            try:
                start_time = time.time()

                if asyncio.iscoroutinefunction(func):
                    asyncio.run(func())
                else:
                    func()

                # Calculate time to next run
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)

                # Sleep with periodic checks for shutdown
                for _ in range(int(sleep_time)):
                    if self.shutdown_event.is_set():
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Scheduled task {func.__name__} failed: {e}")
                time.sleep(interval)  # Wait before retry

    def run(self):
        """
        Start the daemon service.

        Starts:
        - Signal handlers for graceful shutdown
        - All scheduled tasks
        - Business logic (if provided)
        - Startup and shutdown hooks
        """
        logger.info(f"Starting daemon '{self.name}'")

        # Setup signal handlers
        self._setup_signal_handlers()

        # Run startup hooks
        for hook in self.startup_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    asyncio.run(hook())
                else:
                    hook()
            except Exception as e:
                logger.error(f"Startup hook failed: {hook.__name__}: {e}")

        # Start scheduled tasks in separate threads
        task_threads = []
        for func, interval in self.scheduled_tasks:
            thread = threading.Thread(
                target=self._run_scheduled_task, args=(func, interval), name=f"{self.name}_{func.__name__}", daemon=True
            )
            thread.start()
            task_threads.append(thread)
            logger.info(f"Started scheduled task: {func.__name__} (every {interval}s)")

        try:
            # If business logic provided, run it
            if self.business_logic and hasattr(self.business_logic, "run_daemon"):
                self.business_logic.run_daemon(shutdown_event=self.shutdown_event)
            else:
                # Otherwise just wait for shutdown
                logger.info("Daemon running - press Ctrl+C to stop")
                while not self.shutdown_event.is_set():
                    time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            # Run shutdown hooks
            for hook in self.shutdown_hooks:
                try:
                    if asyncio.iscoroutinefunction(hook):
                        asyncio.run(hook())
                    else:
                        hook()
                except Exception as e:
                    logger.error(f"Shutdown hook failed: {hook.__name__}: {e}")

            logger.info("Daemon shutdown complete")
