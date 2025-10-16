"""
HyperLib Oneshot Application
Single-execution task with monitoring
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import MountConfig, get_mount_config
from ..logger import logger


class OneshotApplication:
    """
    One-shot task execution application.

    Provides:
    - Single task execution with monitoring
    - Mount point management (config, data, temp)
    - Execution time tracking
    - Error handling and reporting

    Example:
        app = Application.oneshot(name="batch-job")

        @app.task
        def process_batch():
            logger.info("Processing batch...")
            # Process data
            return {"processed": 100}

        result = app.run()
        print(f"Result: {result}")
    """

    def __init__(
        self,
        name: str,
        task_func: Callable | None = None,
        mounts: MountConfig | None = None,
        **kwargs,
    ):
        """
        Initialize oneshot application.

        Args:
            name: Application name
            task_func: Task function to execute
            mounts: Container mount configuration
            **kwargs: Additional options
        """
        self.name = name
        self.task_func = task_func
        self.decorated_task: Callable | None = None

        # Get or use mount config
        if mounts is None:
            mounts = get_mount_config()

        self.mounts = mounts

        logger.info(f"⚡ OneshotApplication '{name}' initialized")

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

    def run(self) -> Any:
        """
        Execute the one-shot task.

        Returns:
            Task result (if any)

        Raises:
            RuntimeError: If no task is defined
        """
        # Determine which task to run
        task = self.decorated_task or self.task_func

        if not task:
            raise RuntimeError("No task defined. Use @app.task decorator or pass task_func to constructor")

        logger.info(f"Starting one-shot task '{self.name}'")

        start_time = time.time()
        result = None

        try:
            # Execute the task
            logger.info(f"Executing task: {task.__name__}")
            result = task()

            duration = time.time() - start_time
            logger.info(f"Task completed successfully in {duration:.2f}s")

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Task failed after {duration:.2f}s: {e}")
            raise

        return result
