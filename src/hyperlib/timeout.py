"""
HyperLib Smart Timeout System - Generic Intelligent Process Monitoring
Replaces simple timeouts with intelligent activity detection for any long-running process
"""

import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TimeoutReason(Enum):
    """Reasons for timeout termination"""

    NO_ACTIVITY = "no_activity"
    TOTAL_EXECUTION = "total_execution"
    MANUAL_STOP = "manual_stop"
    COMPLETED = "completed"


@dataclass
class ActivityIndicator:
    """Defines what constitutes activity for monitoring"""

    log_patterns: list[str] = None  # Regex patterns in logs to detect activity
    file_monitors: list[str] = None  # File paths to monitor for changes
    output_monitors: list[str] = None  # Output patterns to monitor

    def __post_init__(self):
        if self.log_patterns is None:
            self.log_patterns = []
        if self.file_monitors is None:
            self.file_monitors = []
        if self.output_monitors is None:
            self.output_monitors = []


@dataclass
class TimeoutResult:
    """Result of smart timeout execution"""

    success: bool
    timeout_reason: TimeoutReason
    total_duration: float
    last_activity_time: float
    activity_count: int
    final_output: str
    return_code: int | None = None
    error_message: str | None = None


class SmartTimeoutMonitor:
    """
    Smart timeout system with dual-level monitoring:
    1. Activity timeout - detects hangs early
    2. Total execution timeout - generous backup timeout
    """

    def __init__(
        self,
        activity_timeout: int = 120,  # 2 minutes no activity = hang
        total_timeout: int = 1800,  # 30 minutes total = generous backup
        activity_check_interval: int = 5,
    ):  # Check every 5 seconds

        self.activity_timeout = activity_timeout
        self.total_timeout = total_timeout
        self.activity_check_interval = activity_check_interval

        # Monitoring state
        self.start_time = None
        self.last_activity_time = None
        self.activity_count = 0
        self.monitoring = False
        self.process = None
        self.output_buffer = []

        # File monitoring
        self.file_timestamps = {}

    def run_with_smart_timeout(
        self,
        command: list[str],
        activity_indicators: ActivityIndicator,
        working_dir: str | None = None,
        env: dict | None = None,
    ) -> TimeoutResult:
        """
        Run command with smart timeout monitoring

        Args:
            command: Command to execute
            activity_indicators: What constitutes activity
            working_dir: Working directory for command
            env: Environment variables

        Returns:
            TimeoutResult with execution details
        """

        self.start_time = time.time()
        self.last_activity_time = self.start_time
        self.activity_count = 0
        self.monitoring = True
        self.output_buffer = []

        # Initialize file monitoring
        self._initialize_file_monitoring(activity_indicators.file_monitors)

        try:
            # Start process
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=working_dir,
                env=env,
                bufsize=1,
                universal_newlines=True,
            )

            # Start monitoring thread
            monitor_thread = threading.Thread(target=self._monitor_activity, args=(activity_indicators,), daemon=True)
            monitor_thread.start()

            # Read output in real-time
            timeout_reason = self._read_output_with_monitoring(activity_indicators)

            # Wait for process completion or timeout
            if timeout_reason == TimeoutReason.COMPLETED:
                return_code = self.process.wait()
            else:
                # Terminate process due to timeout
                self._terminate_process()
                return_code = -1

            total_duration = time.time() - self.start_time

            return TimeoutResult(
                success=(timeout_reason == TimeoutReason.COMPLETED and return_code == 0),
                timeout_reason=timeout_reason,
                total_duration=total_duration,
                last_activity_time=time.time() - self.last_activity_time,
                activity_count=self.activity_count,
                final_output="\n".join(self.output_buffer),
                return_code=return_code,
            )

        except Exception as e:
            return TimeoutResult(
                success=False,
                timeout_reason=TimeoutReason.MANUAL_STOP,
                total_duration=time.time() - self.start_time if self.start_time else 0,
                last_activity_time=0,
                activity_count=self.activity_count,
                final_output="\n".join(self.output_buffer),
                error_message=str(e),
            )
        finally:
            self.monitoring = False

    def _initialize_file_monitoring(self, file_paths: list[str]):
        """Initialize file modification time tracking"""
        self.file_timestamps = {}
        for file_path in file_paths:
            path = Path(file_path)
            if path.exists():
                self.file_timestamps[str(path)] = path.stat().st_mtime

    def _monitor_activity(self, activity_indicators: ActivityIndicator):
        """Monitor for activity indicators in separate thread"""

        while self.monitoring and self.process and self.process.poll() is None:
            current_time = time.time()

            # Check file modifications
            if self._check_file_activity(activity_indicators.file_monitors):
                self._register_activity("file_modification")

            # Check total timeout
            if current_time - self.start_time > self.total_timeout:
                logger.warning(f"⏰ Total execution timeout ({self.total_timeout}s) reached")

    def _terminate_process(self):
        """Terminate the monitored process"""
        if self.process:
            try:
                # Graceful termination first
                self.process.terminate()

                # Wait briefly for graceful exit
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    self.process.kill()
                    self.process.wait()

            except Exception as e:
                logger.error(f"Error terminating process: {e}")


def smart_run(
    command: list[str],
    description: str,
    activity_timeout: int = 60,  # 1 minute no activity
    total_timeout: int = 300,  # 5 minutes total
    failure_patterns: list[str] = None,
    success_patterns: list[str] = None,
    progress_patterns: list[str] = None,
) -> TimeoutResult:
    """
    Generic smart timeout for any command with stdout/stderr monitoring

    Args:
        command: Command to run (e.g., ['python', 'script.py'])
        description: Description for logging
        activity_timeout: Seconds without activity before timeout
        total_timeout: Total execution time limit
        failure_patterns: Patterns that indicate immediate failure
        success_patterns: Patterns that indicate success
        progress_patterns: Patterns that indicate progress

    Returns:
        TimeoutResult with execution details
    """

    # Default patterns if not provided
    if failure_patterns is None:
        failure_patterns = [
            r"Error:",
            r"Exception:",
            r"FAILED",
            r"Traceback \(most recent call last\):",  # Python traceback start
            r"TypeError:",
            r"ValueError:",
            r"RuntimeError:",
            r"AttributeError:",
            r"ImportError:",
            r"ModuleNotFoundError:",
            r"FileNotFoundError:",
            r"SyntaxError:",
            r"AssertionError:",
        ]

    if success_patterns is None:
        success_patterns = [r"SUCCESS", r"PASSED", r"completed successfully", r"✓"]

    if progress_patterns is None:
        progress_patterns = [
            r"Testing",
            r"Executing",
            r"Running",
            r"Processing",
            r"Found:",
            r"INFO",
            r"PROGRESS",
            r"Starting",
        ]

    activity_indicators = ActivityIndicator(output_monitors=failure_patterns + success_patterns + progress_patterns)

    timeout_manager = SmartTimeoutMonitor(activity_timeout=activity_timeout, total_timeout=total_timeout)

    return timeout_manager.run_with_smart_timeout(
        command=command, activity_indicators=activity_indicators, working_directory=os.getcwd()
    )


# End of generic smart_run() - all convenience functions removed
# Use smart_run() directly with custom patterns for specific test needs


class FunctionTimeoutMonitor:
    """
    Smart timeout system for Python functions with progress monitoring
    """

    def __init__(self, activity_timeout: int = 120, total_timeout: int = 600, progress_check_interval: int = 5):

        self.activity_timeout = activity_timeout
        self.total_timeout = total_timeout
        self.progress_check_interval = progress_check_interval

        # Monitoring state
        self.start_time = None
        self.last_activity_time = None
        self.activity_count = 0
        self.monitoring = False
        self.function_thread = None
        self.result = None
        self.exception = None
        self.output_buffer = []

        # Progress callback state
        self.progress_callback_called = False

    def run_function_with_timeout(
        self, func: Callable, args: tuple = (), kwargs: dict = None, description: str = "", capture_output: bool = True
    ) -> TimeoutResult:
        """
        Run Python function with smart timeout monitoring

        Args:
            func: Function to execute
            args: Function positional arguments
            kwargs: Function keyword arguments
            description: Description for logging
            capture_output: Whether to capture stdout/stderr

        Returns:
            TimeoutResult with execution details
        """

        if kwargs is None:
            kwargs = {}

        self.start_time = time.time()
        self.last_activity_time = self.start_time
        self.activity_count = 0
        self.monitoring = True
        self.result = None
        self.exception = None
        self.output_buffer = []
        self.progress_callback_called = False

        logger.info(f"Starting function: {description}")


def smart_run_function(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    description: str = "",
    activity_timeout: int = 60,
    total_timeout: int = 300,
    capture_output: bool = True,
) -> TimeoutResult:
    """
    Smart timeout for Python functions with intelligent monitoring

    Args:
        func: Python function to execute
        args: Function positional arguments
        kwargs: Function keyword arguments
        description: Description for logging
        activity_timeout: Seconds without progress before timeout
        total_timeout: Total execution time limit
        capture_output: Whether to capture stdout/stderr from function

    Returns:
        TimeoutResult with execution details

    Example:
        # Test a /src component directly
        def test_function():
            from dfe_ai.vector.parser.vrl.baseline import VRLBaselineGenerator
            generator = VRLBaselineGenerator()
            return generator.generate_vrl(logs, device_type="ssh")

        result = smart_run_function(
            func=test_function,
            description="Test VRL baseline generation",
            activity_timeout=120,
            total_timeout=600
        )
    """

    if kwargs is None:
        kwargs = {}

    monitor = FunctionTimeoutMonitor(activity_timeout=activity_timeout, total_timeout=total_timeout)

    return monitor.run_function_with_timeout(
        func=func, args=args, kwargs=kwargs, description=description, capture_output=capture_output
    )
