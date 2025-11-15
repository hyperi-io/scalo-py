"""
hs-lib Oneshot Application
Single-execution task with container-native patterns
"""

import time
from collections.abc import Callable
from typing import Any

from ...logger import logger
from ..mixins import (
    CLIExecutableMixin,
    ProfileMixin,
    SignalHandlerMixin,
)


class OneshotApplication(
    CLIExecutableMixin,
    SignalHandlerMixin,
    ProfileMixin,
):
    """
    One-shot task execution application.

    Provides container-native patterns out of the box:
    - Profile-based configuration (dev/docker/prod)
    - Graceful shutdown (SIGTERM/SIGINT) if interrupted
    - Typer CLI commands (run, validate, version, config)

    Note: No metrics or health checks (one-shot execution doesn't need them)

    Example (simple):
        app = Application.oneshot(name="batch-job", version="1.0.0")

        @app.task
        def process_batch():
            logger.info("Processing batch...")
            # Process data
            return {"processed": 100}

        if __name__ == "__main__":
            app.run()  # Runs Typer CLI

    Example (production):
        # Container CMD: python -m my_job run --profile prod
        # Runs once and exits

    Example (with metrics):
        app = Application.oneshot(
            name="batch-job",
            version="1.0.0",
            profile="prod",
            profile_overrides={"metrics": True}  # Enable metrics if needed
        )

        @app.task
        def process():
            logger.info("Processing...")
            return {"status": "complete"}
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        profile: str = "dev",
        task_func: Callable | None = None,
        profile_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize oneshot application.

        Args:
            name: Application name
            version: Application version
            profile: Environment profile ("dev", "docker", "prod")
            task_func: Task function to execute
            profile_overrides: Override profile settings
            **kwargs: Additional options
        """
        # Initialize mixins (MRO: CLI -> Signal -> Profile)
        # Note: No MetricsMixin by default (oneshot jobs don't usually need metrics)
        super().__init__(
            name=name,
            version=version,
            profile=profile,
            profile_overrides=profile_overrides,
            description=f"{name} - hs-lib Oneshot Job",
        )

        self.task_func = task_func
        self.decorated_task: Callable | None = None

        # Add run command to CLI
        self._add_run_command()

        logger.info(f"OneshotApplication '{name}' initialized (profile={profile})")

    def _add_run_command(self) -> None:
        """Add 'run' command to CLI."""
        import typer

        @self.cli.command()
        def run():
            """Execute the one-shot task."""
            logger.info(f"Starting one-shot task '{self.name}' (profile={self.profile_name})")
            result = self._execute_task()

            # Exit with success code
            if result is not None:
                typer.echo("Task completed successfully")
            raise typer.Exit(0)

    def task(self, func: Callable) -> Callable:
        """
        Decorator to register the main task.

        Example:
            @app.task
            def process():
                logger.info("Processing...")
                return {"status": "complete"}
        """
        self.decorated_task = func
        self.task_func = func  # Also set task_func for compatibility
        logger.debug(f"Registered task: {func.__name__}")
        return func

    def _execute_task(self) -> Any:
        """
        Internal method to execute the task.

        Returns:
            Task result (if any)

        Raises:
            RuntimeError: If no task is defined
        """
        # Determine which task to run
        task = self.decorated_task or self.task_func

        if not task:
            raise RuntimeError("No task defined. Use @app.task decorator or pass task_func to constructor")

        logger.info(f"Executing task: {task.__name__}")

        start_time = time.time()
        result = None

        try:
            # Execute the task
            result = task()

            duration = time.time() - start_time

            # Track metrics if enabled
            if hasattr(self, "track_counter"):
                self.track_counter(
                    "job_execution_total",
                    labels={"job": self.name, "status": "success"},
                )
                self.track_histogram(
                    "job_execution_duration_seconds",
                    duration,
                    labels={"job": self.name},
                )

            logger.info(f"Task completed successfully in {duration:.2f}s")

        except Exception as e:
            duration = time.time() - start_time

            # Track failure metrics if enabled
            if hasattr(self, "track_counter"):
                self.track_counter(
                    "job_execution_total",
                    labels={"job": self.name, "status": "failed"},
                )

            logger.error(f"Task failed after {duration:.2f}s: {e}", exc_info=True)
            raise

        return result
