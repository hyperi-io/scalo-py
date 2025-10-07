"""
HyperLib Oneshot Application
Single-execution task with container monitoring and resource management
"""

from pathlib import Path
from typing import Any, Callable

from ..container import ContainerApp, ContainerConfig, MountConfig
from ..logger import logger


class OneshotApplication:
    """
    One-shot task application with container monitoring.

    Provides:
    - Single task execution
    - Container resource detection
    - Prometheus metrics during execution
    - Memory monitoring
    - Thread/process pool access
    - Graceful error handling

    Example:
        app = Application.oneshot(name="my-task")

        @app.task
        def process_data():
            logger.info("Processing data...")
            return {"status": "success"}

        result = app.run()
        print(result)

    Or with thread pools:

        app = Application.oneshot(name="parallel-task")

        @app.task
        def parallel_process(thread_pool, process_pool):
            # Use thread pool for I/O-bound work
            futures = [thread_pool.submit(fetch_url, url) for url in urls]
            results = [f.result() for f in futures]
            return results

        result = app.run()
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
            task_func: Optional task function to execute
            mounts: Container mount configuration
            **kwargs: Additional ContainerConfig options
        """
        self.name = name
        self.task_func = task_func

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

        logger.info(f"⚡ OneshotApplication '{name}' initialized")

    def task(self, func: Callable) -> Callable:
        """
        Decorator to register task function.

        Example:
            @app.task
            def process_data():
                return {"result": "success"}
        """
        self.task_func = func
        logger.debug(f"Registered task: {func.__name__}")
        return func

    def run(self) -> Any:
        """
        Execute the one-shot task.

        Returns:
            Task return value

        Raises:
            ValueError: If no task function registered
            Exception: If task execution fails
        """
        if not self.task_func:
            raise ValueError(
                f"No task function registered for '{self.name}'. "
                "Use @app.task decorator or pass task_func to Application.oneshot()"
            )

        logger.info(f"⚡ Starting oneshot task '{self.name}'")

        # Create container app
        self.container = ContainerApp(
            business_logic=None,  # We'll run task directly
            config=self.config,
        )

        # Run task with container monitoring
        result = self.container.run_oneshot(self.task_func)

        logger.success(f"✅ Oneshot task '{self.name}' completed")
        return result
