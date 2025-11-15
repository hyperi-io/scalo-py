"""
hs-lib Process Execution Harness - Intelligent Subprocess Monitoring and Testing

Provides smart process execution with:
- Activity-based monitoring (detects hangs early via output patterns)
- Flexible timeout handling (activity timeout + total execution timeout)
- Output pattern matching (failure, success, progress detection)
- Early termination on detected failures
- Detailed execution results for debugging

Use cases:
- Running tests with intelligent hang detection
- Monitoring long-running CI/CD processes
- Container/K8s deployment verification
- Any subprocess that needs smarter timeout handling than simple wall-clock limits
"""

import os
import subprocess  # nosec B404 - Subprocess is required for process execution harness
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TerminationReason(Enum):
    """Reasons for process termination"""

    NO_ACTIVITY = "no_activity"  # Process hung (no output/activity detected)
    TOTAL_EXECUTION = "total_execution"  # Total time limit exceeded
    FAILURE_DETECTED = "failure_detected"  # Failure pattern found in output
    MANUAL_STOP = "manual_stop"  # Manually stopped or exception
    COMPLETED = "completed"  # Process completed successfully


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
class HarnessResult:
    """Result of harness process execution"""

    success: bool
    termination_reason: TerminationReason
    total_duration: float
    last_activity_time: float
    activity_count: int
    final_output: str
    return_code: int | None = None
    error_message: str | None = None


def run(
    cmd: list[str],
    timeout: int = 30,
    check: bool = True,
    cwd: str | None = None,
    log_file: Path | None = None,
    log_label: str | None = None,
    pytest_fail: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a subprocess command with optional logging to file.

    Args:
        cmd: Command to execute
        timeout: Timeout in seconds
        check: Raise exception on non-zero exit
        cwd: Working directory
        log_file: Optional Path to log file for capturing output
        log_label: Optional label for log section (e.g., "Container: foo")
        pytest_fail: If True, use pytest.fail() on errors (for test integration)

    Returns:
        CompletedProcess with stdout/stderr

    Raises:
        subprocess.CalledProcessError: If check=True and command fails (unless pytest_fail=True)
        subprocess.TimeoutExpired: If command times out (unless pytest_fail=True)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            cwd=cwd,
        )  # nosec B603 - Command list is caller-controlled
    except subprocess.TimeoutExpired:
        if pytest_fail:
            import pytest

            pytest.fail(f"Command timed out: {' '.join(cmd)}")
        raise
    except subprocess.CalledProcessError as e:
        if pytest_fail and check:
            import pytest

            pytest.fail(f"Command failed: {' '.join(cmd)}\n{e.stderr}")
        raise

    # Log to file if specified
    if log_file:
        with log_file.open("a") as f:
            f.write(f"\n{'='*80}\n")
            if log_label:
                f.write(f"{log_label}\n")
            else:
                f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"{'='*80}\n\n")

            if result.stdout:
                f.write("STDOUT:\n")
                f.write(result.stdout)
                f.write("\n\n")

            if result.stderr:
                f.write("STDERR:\n")
                f.write(result.stderr)
                f.write("\n\n")

            f.write(f"Exit code: {result.returncode}\n")

    return result


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
    ) -> HarnessResult:
        """
        Run command with smart timeout monitoring

        Args:
            command: Command to execute
            activity_indicators: What constitutes activity
            working_dir: Working directory for command
            env: Environment variables

        Returns:
            HarnessResult with execution details
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
            )  # nosec B603,B607 - Command list is caller-controlled

            # Start monitoring thread
            monitor_thread = threading.Thread(target=self._monitor_activity, args=(activity_indicators,), daemon=True)
            monitor_thread.start()

            # Read output in real-time
            timeout_reason = self._read_output_with_monitoring(activity_indicators)

            # Wait for process completion or timeout
            if timeout_reason == TerminationReason.COMPLETED:
                return_code = self.process.wait()
            else:
                # Terminate process due to timeout
                self._terminate_process()
                return_code = -1

            total_duration = time.time() - self.start_time

            return HarnessResult(
                success=(timeout_reason == TerminationReason.COMPLETED and return_code == 0),
                timeout_reason=timeout_reason,
                total_duration=total_duration,
                last_activity_time=time.time() - self.last_activity_time,
                activity_count=self.activity_count,
                final_output="\n".join(self.output_buffer),
                return_code=return_code,
            )

        except Exception as e:
            return HarnessResult(
                success=False,
                timeout_reason=TerminationReason.MANUAL_STOP,
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
) -> HarnessResult:
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
        HarnessResult with execution details
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
    ) -> HarnessResult:
        """
        Run Python function with smart timeout monitoring

        Args:
            func: Function to execute
            args: Function positional arguments
            kwargs: Function keyword arguments
            description: Description for logging
            capture_output: Whether to capture stdout/stderr

        Returns:
            HarnessResult with execution details
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
) -> HarnessResult:
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
        HarnessResult with execution details

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


# ============================================================================
# Container Registry Throttling Detection
# ============================================================================


def container_registry_login() -> tuple[bool, str]:
    """
    Authenticate with Artifactory container registry from .env file.

    Uses JFrog Artifactory as Docker Hub caching proxy for faster pulls
    and no rate limiting.

    Returns:
        (success: bool, message: str)

    Example .env:
        ARTIFACTORY_CONTAINER_URL=hypersec.jfrog.io
        ARTIFACTORY_USERNAME=your-email@hypersec.io
        ARTIFACTORY_PASSWORD=your-jfrog-password
    """
    artifactory_url = os.getenv("ARTIFACTORY_CONTAINER_URL")
    artifactory_user = os.getenv("ARTIFACTORY_USERNAME")
    artifactory_pass = os.getenv("ARTIFACTORY_PASSWORD")

    if not (artifactory_url and artifactory_user and artifactory_pass):
        return False, "ARTIFACTORY_CONTAINER_URL or credentials not set in .env"

    try:
        result = subprocess.run(
            ["docker", "login", artifactory_url, "-u", artifactory_user, "--password-stdin"],
            input=artifactory_pass,
            capture_output=True,
            text=True,
            timeout=30,
        )  # nosec B603,B607 - Docker login with controlled inputs

        if result.returncode == 0:
            return True, f"Artifactory container registry authenticated: {artifactory_url}"
        else:
            return False, f"Artifactory login failed: {result.stderr.strip()}"

    except subprocess.TimeoutExpired:
        return False, "Artifactory login timed out after 30s"
    except Exception as e:
        return False, f"Artifactory login error: {e}"


def docker_login_from_env() -> tuple[bool, str]:
    """
    Legacy function - use container_registry_login() instead.

    Kept for backward compatibility with existing code.
    """
    return container_registry_login()


def check_registry_throttling(namespace: str) -> tuple[bool, str]:
    """
    Check if container registry is being throttled in Kubernetes namespace.

    Detects throttling via:
    1. Kubernetes events (rate limit messages)
    2. Pod status (ImagePullBackOff with throttling reasons)
    3. Container status messages

    Args:
        namespace: Kubernetes namespace to check

    Returns:
        (is_throttled: bool, reason: str)

    Example:
        throttled, reason = check_registry_throttling("my-namespace")
        if throttled:
            pytest.skip(f"Registry throttling detected: {reason}")
    """
    throttle_patterns = [
        "toomanyrequests",
        "rate limit",
        "throttl",
        "quota exceeded",
        "pull rate limit",
        "429",  # HTTP 429 Too Many Requests
    ]

    try:
        # Check Kubernetes events for throttling indicators
        result = subprocess.run(
            ["kubectl", "get", "events", "-n", namespace, "--field-selector", "type=Warning"],
            capture_output=True,
            text=True,
            timeout=10,
        )  # nosec B603,B607 - kubectl with controlled namespace

        events_lower = result.stdout.lower()
        for pattern in throttle_patterns:
            if pattern in events_lower:
                return True, f"Registry throttling detected in events: {pattern}"

        # Check pod statuses for ImagePullBackOff with rate limit reasons
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )  # nosec B603,B607 - kubectl with controlled namespace

        if result.returncode == 0:
            import json

            pods = json.loads(result.stdout)
            for pod in pods.get("items", []):
                # Check container statuses
                for container_status in pod.get("status", {}).get("containerStatuses", []):
                    waiting = container_status.get("state", {}).get("waiting", {})
                    reason = waiting.get("reason", "").lower()
                    message = waiting.get("message", "").lower()

                    # Check for ImagePullBackOff or ErrImagePull
                    if "imagepull" in reason:
                        for pattern in throttle_patterns:
                            if pattern in message:
                                return True, f"Registry throttling in pod {pod['metadata']['name']}: {pattern}"

        return False, ""

    except subprocess.TimeoutExpired:
        return False, "Throttling check timed out (kubectl slow)"
    except Exception as e:
        return False, f"Throttling check error: {e}"


def check_container_registry_access() -> tuple[bool, dict]:
    """
    Check container registry access (Artifactory).

    Tests if registry is accessible and authentication is working.

    Returns:
        (accessible: bool, status: dict)

    status dict contains:
        - authenticated: bool
        - message: str
        - throttled: bool (if rate limiting detected)

    Example:
        accessible, status = check_container_registry_access()
        if status.get('throttled'):
            pytest.skip(f"Registry throttled: {status['message']}")
    """
    artifactory_url = os.getenv("ARTIFACTORY_CONTAINER_URL")

    if not artifactory_url:
        return False, {"authenticated": False, "message": "ARTIFACTORY_CONTAINER_URL not configured"}

    try:
        # Test registry access by pulling a small manifest
        # Using busybox as it's tiny and commonly cached
        result = subprocess.run(
            ["docker", "manifest", "inspect", f"{artifactory_url}/hypersec-docker/library/busybox:latest"],
            capture_output=True,
            text=True,
            timeout=15,
        )  # nosec B603,B607 - Docker manifest with controlled URL

        if result.returncode == 0:
            return True, {"authenticated": True, "message": f"Artifactory registry accessible: {artifactory_url}"}
        else:
            # Check if error mentions throttling/rate limiting
            stderr_lower = result.stderr.lower()
            throttle_patterns = ["rate limit", "toomanyrequests", "429", "quota", "throttl"]

            if any(pattern in stderr_lower for pattern in throttle_patterns):
                return False, {
                    "authenticated": False,
                    "throttled": True,
                    "message": f"Registry rate limit/throttling detected: {artifactory_url}",
                }

            return False, {"authenticated": False, "message": f"Registry access failed: {result.stderr.strip()}"}

    except subprocess.TimeoutExpired:
        return False, {"error": "Registry check timed out after 15s"}
    except Exception as e:
        return False, {"error": str(e)}


def check_docker_hub_rate_limit() -> tuple[bool, dict]:
    """
    Legacy function - use check_container_registry_access() instead.

    Kept for backward compatibility with existing test code.
    """
    return check_container_registry_access()
