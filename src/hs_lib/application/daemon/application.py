"""
HyperLib Daemon Application
Long-running background service with container-native patterns
"""

import asyncio
import threading
import time
from collections.abc import Callable
from typing import Any, NamedTuple

from ...logger import logger
from ..mixins import (
    CLIExecutableMixin,
    HealthCheckMixin,
    MetricsMixin,
    ProfileMixin,
    SignalHandlerMixin,
)


class ScheduledTask(NamedTuple):
    """Scheduled task with interval."""

    func: Callable
    interval: int  # seconds


class DaemonApplication(
    CLIExecutableMixin,
    SignalHandlerMixin,
    ProfileMixin,
    HealthCheckMixin,
    MetricsMixin,
):
    """
    Long-running daemon service application.

    Provides container-native patterns out of the box:
    - Profile-based configuration (dev/docker/prod)
    - Graceful shutdown (SIGTERM/SIGINT) - **fixes orphaned process bug**
    - Health HTTP server for k8s probes (separate thread)
    - Automatic task metrics (Prometheus/OTEL)
    - Typer CLI commands (start, status, stop, version, config)

    Example (simple):
        app = Application.daemon(name="worker", version="1.0.0", profile="prod")

        @app.task(interval=60)
        def process_queue():
            logger.info("Processing queue...")
            # Your business logic

        if __name__ == "__main__":
            app.run()  # Runs Typer CLI

    Example (production):
        # Container CMD: python -m my_worker start --profile prod
        # Automatically gets: health server, metrics, graceful shutdown

    Example (complex):
        app = Application.daemon(name="worker", version="1.0.0")

        @app.task(interval=60)
        def sync_data():
            # Task logic
            pass

        @app.on_startup
        def startup():
            logger.info("Daemon starting...")

        @app.on_shutdown
        def cleanup():
            logger.info("Daemon stopping...")
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        profile: str = "dev",
        profile_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize daemon application.

        Args:
            name: Application name
            version: Application version
            profile: Environment profile ("dev", "docker", "prod")
            profile_overrides: Override profile settings
            **kwargs: Additional options
        """
        # Initialize mixins (MRO: CLI -> Signal -> Profile -> Metrics)
        super().__init__(
            name=name,
            version=version,
            profile=profile,
            profile_overrides=profile_overrides,
            description=f"{name} - HyperLib Daemon Service",
        )

        self.scheduled_tasks: list[ScheduledTask] = []
        self.task_threads: list[threading.Thread] = []

        # Add start command to CLI
        self._add_start_command()

        logger.info(f"DaemonApplication '{name}' initialized (profile={profile})")

    def _add_start_command(self) -> None:
        """Add 'start' command to CLI."""

        @self.cli.command()
        def start():
            """Start the daemon service."""
            logger.info(f"Starting daemon '{self.name}' (profile={self.profile_name})")
            self._run_daemon()

    def task(self, interval: int) -> Callable:
        """
        Decorator to register a scheduled task.

        Args:
            interval: Interval in seconds between executions

        Example:
            @app.task(interval=60)
            def periodic_task():
                logger.info("Running every 60 seconds")
        """

        def decorator(func: Callable) -> Callable:
            self.scheduled_tasks.append(ScheduledTask(func=func, interval=interval))
            logger.debug(f"Registered task: {func.__name__} (every {interval}s)")
            return func

        return decorator

    # Aliases for backward compatibility
    def scheduled(self, interval: int) -> Callable:
        """Alias for task() decorator."""
        return self.task(interval)

    def on_startup(self, func: Callable) -> Callable:
        """
        Decorator to register startup hook.

        Note: Uses on_shutdown from SignalHandlerMixin for consistency.
        """
        # Store startup hook to run before tasks
        if not hasattr(self, "_startup_hooks"):
            self._startup_hooks = []
        self._startup_hooks.append(func)
        logger.debug(f"Registered startup hook: {func.__name__}")
        return func

    # Compatibility aliases for existing code
    @property
    def startup(self):
        """Alias for on_startup (backward compatibility)."""
        return self.on_startup

    @property
    def shutdown(self):
        """Alias for on_shutdown (backward compatibility)."""
        return self.on_shutdown

    def _run_scheduled_task(self, func: Callable, interval: int) -> None:
        """Run a single scheduled task in a loop."""
        while not self.is_shutting_down():
            try:
                start_time = time.time()

                # Track task execution
                self.track_counter(
                    "task_execution_total",
                    labels={"task": func.__name__, "status": "started"},
                )

                # Execute task
                try:
                    if asyncio.iscoroutinefunction(func):
                        asyncio.run(func())
                    else:
                        func()

                    # Track success
                    self.track_counter(
                        "task_execution_total",
                        labels={"task": func.__name__, "status": "success"},
                    )

                except Exception as e:
                    logger.error(f"Task {func.__name__} failed: {e}", exc_info=True)
                    self.track_counter(
                        "task_execution_total",
                        labels={"task": func.__name__, "status": "failed"},
                    )

                # Track duration
                duration = time.time() - start_time
                self.track_histogram(
                    "task_execution_duration_seconds",
                    duration,
                    labels={"task": func.__name__},
                )

                # Calculate time to next run
                elapsed = time.time() - start_time
                sleep_time = max(0, interval - elapsed)

                # Sleep with periodic checks for shutdown
                for _ in range(int(sleep_time)):
                    if self.is_shutting_down():
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Scheduled task {func.__name__} failed: {e}")
                time.sleep(interval)  # Wait before retry

    def _run_daemon(self) -> None:
        """
        Internal method to run the daemon.

        Starts:
        - All scheduled tasks
        - Startup and shutdown hooks
        - Waits for shutdown signal
        """
        logger.info(f"Daemon '{self.name}' starting...")

        # Run startup hooks
        if hasattr(self, "_startup_hooks"):
            for hook in self._startup_hooks:
                try:
                    if asyncio.iscoroutinefunction(hook):
                        asyncio.run(hook())
                    else:
                        hook()
                except Exception as e:
                    logger.error(f"Startup hook failed: {hook.__name__}: {e}")

        # Start scheduled tasks in separate threads
        for task in self.scheduled_tasks:
            thread = threading.Thread(
                target=self._run_scheduled_task,
                args=(task.func, task.interval),
                name=f"{self.name}_{task.func.__name__}",
                daemon=False,  # NOT daemon - we want to track them
            )
            thread.start()
            self.task_threads.append(thread)
            logger.info(f"Started task: {task.func.__name__} (every {task.interval}s)")

        # Register shutdown handler to stop tasks
        @self.on_shutdown
        def stop_tasks():
            logger.info("Stopping scheduled tasks...")
            # Tasks will stop when is_shutting_down() returns True
            # Wait for them to complete (up to shutdown_timeout)
            for thread in self.task_threads:
                if thread.is_alive():
                    logger.debug(f"Waiting for task thread: {thread.name}")

        # Wait for shutdown signal
        logger.info("Daemon running - waiting for shutdown signal")
        self.wait_for_shutdown()

        logger.info("Daemon shutdown complete")
