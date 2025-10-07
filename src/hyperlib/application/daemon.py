"""
HyperLib Daemon Application
Long-running background service with scheduled tasks and worker pools
"""

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..container import ContainerApp, ContainerConfig, MountConfig
from ..logger import logger


class DaemonApplication:
    """
    Long-running daemon service application.

    Provides:
    - Scheduled background tasks (decorator pattern)
    - Worker thread/process pools from container
    - Graceful shutdown handling (SIGTERM, SIGINT)
    - Prometheus metrics
    - Memory monitoring and OOM protection
    - Container resource detection (cgroups v2)

    Example:
        app = Application.daemon(name="my-worker")

        @app.scheduled(interval=60)
        async def process_queue():
            # Background task every 60 seconds
            logger.info("Processing queue...")

        @app.startup
        async def on_startup():
            logger.info("Daemon starting...")

        @app.shutdown
        async def on_shutdown():
            logger.info("Daemon stopping...")

        app.run()
    """

    def __init__(
        self,
        name: str,
        business_logic: Any | None = None,
        mounts: MountConfig | None = None,
        **kwargs,
    ):
        """
        Initialize daemon application.

        Args:
            name: Application name
            business_logic: Optional business logic object with run_daemon() method
            mounts: Container mount configuration
            **kwargs: Additional ContainerConfig options
        """
        self.name = name
        self.business_logic = business_logic
        self.scheduled_tasks: list[tuple[Callable, int]] = []  # (func, interval_seconds)
        self.startup_hooks: list[Callable] = []
        self.shutdown_hooks: list[Callable] = []

        # Create container config
        if mounts is None:
            mounts = MountConfig(
                config_dir=Path("/app/config"),
                data_dir=Path("/app/data"),
                temp_dir=Path("/app/tmp"),
            )

        self.config = ContainerConfig(
            app_name=name,
            mounts=mounts,
            **kwargs,
        )

        # Container app will be created when run() is called
        self.container: ContainerApp | None = None

        logger.info(f"🔧 DaemonApplication '{name}' initialized")

    def scheduled(self, interval: int) -> Callable:
        """
        Decorator to register scheduled background task.

        Args:
            interval: Interval in seconds between task executions

        Example:
            @app.scheduled(interval=60)
            async def hourly_sync():
                # Runs every 60 seconds
                logger.info("Syncing data...")
        """

        def decorator(func: Callable) -> Callable:
            self.scheduled_tasks.append((func, interval))
            logger.debug(f"Registered scheduled task: {func.__name__} (every {interval}s)")
            return func

        return decorator

    def startup(self, func: Callable) -> Callable:
        """
        Decorator to register startup hook.

        Example:
            @app.startup
            async def on_startup():
                logger.info("Daemon starting...")
        """
        self.startup_hooks.append(func)
        logger.debug(f"Registered startup hook: {func.__name__}")
        return func

    def shutdown(self, func: Callable) -> Callable:
        """
        Decorator to register shutdown hook.

        Example:
            @app.shutdown
            async def on_shutdown():
                logger.info("Daemon stopping...")
        """
        self.shutdown_hooks.append(func)
        logger.debug(f"Registered shutdown hook: {func.__name__}")
        return func

    def run(self):
        """
        Start the daemon service.

        Starts:
        - Container resource detection and limits
        - Prometheus metrics server
        - Memory guardian (OOM protection)
        - All scheduled tasks
        - Business logic (if provided)
        - Graceful shutdown handling
        """
        logger.info(f"Starting daemon '{self.name}'")

        # If business logic provided, use it directly
        if self.business_logic:
            self.container = ContainerApp(
                business_logic=self.business_logic,
                config=self.config,
            )
            self.container.run_daemon()
            return

        # Otherwise, create wrapper with scheduled tasks
        class DaemonBusinessLogic:
            def __init__(self, daemon_app: "DaemonApplication"):
                self.daemon_app = daemon_app

            def run_daemon(self, shutdown_event, thread_pool, process_pool):
                """Main daemon loop with scheduled tasks."""
                # Run startup hooks
                for hook in self.daemon_app.startup_hooks:
                    try:
                        if asyncio.iscoroutinefunction(hook):
                            asyncio.run(hook())
                        else:
                            hook()
                    except Exception as e:
                        logger.error(f"Startup hook failed: {hook.__name__}: {e}")

                # If no scheduled tasks, just wait for shutdown
                if not self.daemon_app.scheduled_tasks:
                    logger.info("No scheduled tasks - waiting for shutdown signal")
                    while not shutdown_event.is_set():
                        time.sleep(1)
                    return

                # Schedule tasks
                task_threads = []
                for task_func, interval in self.daemon_app.scheduled_tasks:
                    logger.info(f"Starting scheduled task: {task_func.__name__} (every {interval}s)")

                    def task_runner(func, interval_sec):
                        """Run task at specified interval."""
                        while not shutdown_event.is_set():
                            try:
                                start_time = time.time()

                                # Execute task
                                if asyncio.iscoroutinefunction(func):
                                    asyncio.run(func())
                                else:
                                    func()

                                # Sleep for remaining interval
                                elapsed = time.time() - start_time
                                sleep_time = max(0, interval_sec - elapsed)

                                if sleep_time > 0:
                                    shutdown_event.wait(timeout=sleep_time)

                            except Exception as e:
                                logger.error(f"Scheduled task error: {func.__name__}: {e}")
                                shutdown_event.wait(timeout=interval_sec)

                    # Submit task to thread pool
                    future = thread_pool.submit(task_runner, task_func, interval)
                    task_threads.append(future)

                # Wait for shutdown
                logger.info(f"Daemon '{self.daemon_app.name}' running with {len(task_threads)} scheduled tasks")
                shutdown_event.wait()

                # Run shutdown hooks
                for hook in self.daemon_app.shutdown_hooks:
                    try:
                        if asyncio.iscoroutinefunction(hook):
                            asyncio.run(hook())
                        else:
                            hook()
                    except Exception as e:
                        logger.error(f"Shutdown hook failed: {hook.__name__}: {e}")

            def cleanup(self):
                """Optional cleanup method called during graceful shutdown."""
                logger.info("Daemon cleanup completed")

        # Create container with daemon wrapper
        self.container = ContainerApp(
            business_logic=DaemonBusinessLogic(self),
            config=self.config,
        )

        self.container.run_daemon()
