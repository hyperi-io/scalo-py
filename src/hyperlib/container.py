"""
HyperLib Container Management - Enterprise Deployment Abstraction
Provides "attach later" pattern for containerized Python applications
"""

import json
import resource
import signal
import threading
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

# Import hyperlib components
from . import logger


@dataclass
class MountConfig:
    """Container mount configuration following K8s/Docker patterns"""

    config_dir: Path | None = None  # READ-ONLY (ConfigMap)
    data_dir: Path | None = None  # PERSISTENT (PVC)
    temp_dir: Path | None = None  # EPHEMERAL (EmptyDir)

    def __post_init__(self):
        """Convert strings to Path objects"""
        if isinstance(self.config_dir, str):
            self.config_dir = Path(self.config_dir)
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        if isinstance(self.temp_dir, str):
            self.temp_dir = Path(self.temp_dir)


@dataclass
class ContainerConfig:
    """Enterprise container application configuration"""

    app_name: str
    mounts: MountConfig

    # API configuration
    metrics_port: int = 8080
    health_port: int | None = None  # Same as metrics if None
    api_port: int = 8000

    # Lifecycle management
    shutdown_timeout: int = 30
    startup_timeout: int = 60

    memory_limit_detection: bool = True
    memory_safety_margin: float = 0.2  # Reserve 20% for safety
    memory_monitoring: bool = True
    memory_alert_threshold: float = 0.75  # Alert at 75%
    memory_critical_threshold: float = 0.90  # Emergency at 90%

    # Threading configuration
    auto_thread_sizing: bool = True
    max_io_threads_override: int | None = None
    max_cpu_processes_override: int | None = None
    thread_memory_budget_percent: float = 0.15  # 15% of memory for threads

    # Monitoring
    enable_metrics: bool = True
    enable_health: bool = True
    enable_prometheus: bool = True

    # Logging
    log_level: str = "INFO"
    structured_logging: bool = True


class ResourceManager:
    """Manages container resource detection and allocation"""

    def __init__(self, config: ContainerConfig):
        self.config = config
        self.logger = logger

    def detect_container_resources(self) -> dict[str, Any]:
        """Detect actual container resource limits"""

        resources = {"memory_bytes": None, "cpu_cores": None, "detection_method": None, "container_detected": False}

        # Try cgroups v2 first (2025 standard)
        try:
            memory_limit = self._read_cgroup_v2_memory()
            cpu_limit = self._read_cgroup_v2_cpu()

            if memory_limit and cpu_limit:
                resources.update(
                    {
                        "memory_bytes": memory_limit,
                        "cpu_cores": cpu_limit,
                        "detection_method": "cgroups_v2",
                        "container_detected": True,
                    }
                )

                self.logger.info("Container resources detected (cgroups v2)")
                self.logger.info(f"   Memory: {memory_limit/1024/1024/1024:.2f}GB")
                self.logger.info(f"   CPU cores: {cpu_limit}")

                return resources

        except Exception as e:
            self.logger.debug(f"cgroups v2 detection failed: {e}")

        # Fallback to system resources
        try:
            import psutil

            resources.update(
                {
                    "memory_bytes": psutil.virtual_memory().total,
                    "cpu_cores": psutil.cpu_count(),
                    "detection_method": "system_fallback",
                    "container_detected": False,
                }
            )

            self.logger.info("System resources detected (fallback)")

        except Exception as e:
            self.logger.error(f"Resource detection failed: {e}")
            raise RuntimeError("Could not detect system resources")

        return resources

    def _read_cgroup_v2_memory(self) -> int | None:
        """Read memory limit from cgroups v2"""
        try:
            with open("/sys/fs/cgroup/memory.max") as f:
                limit_str = f.read().strip()

            if limit_str == "max":
                return None  # No limit set

            limit = int(limit_str)
            if limit >= (1 << 63):  # Very large number = no limit
                return None

            return limit

        except (FileNotFoundError, ValueError, PermissionError):
            return None

    def _read_cgroup_v2_cpu(self) -> float | None:
        """Read CPU limit from cgroups v2"""
        try:
            # Read CPU quota and period
            with open("/sys/fs/cgroup/cpu.max") as f:
                cpu_max = f.read().strip()

            if cpu_max == "max":
                # No CPU limit, use system CPU count
                return float(psutil.cpu_count())

            if " " in cpu_max:
                quota, period = cpu_max.split()
                quota = int(quota)
                period = int(period)

                # Calculate CPU cores from quota/period
                cpu_cores = quota / period
                return cpu_cores

            return None

        except (FileNotFoundError, ValueError, PermissionError):
            return None

    def calculate_safe_thread_limits(self, resources: dict[str, Any]) -> dict[str, int]:
        """Calculate thread limits that won't OOM the container"""

        memory_bytes = resources["memory_bytes"]
        cpu_cores = resources["cpu_cores"]

        # Memory-based thread calculation
        thread_memory_budget = memory_bytes * self.config.thread_memory_budget_percent
        per_thread_memory = 12 * 1024 * 1024  # 12MB per thread (stack + overhead)
        max_threads_by_memory = int(thread_memory_budget / per_thread_memory)

        # CPU-based thread calculation (I/O oversubscription)
        max_threads_by_cpu = int(cpu_cores * 4)  # 4x for I/O-bound workloads

        # Use override or calculated limits
        io_threads = self.config.max_io_threads_override or min(max_threads_by_memory, max_threads_by_cpu, 32)

        cpu_processes = self.config.max_cpu_processes_override or max(1, int(cpu_cores))

        self.logger.info("🧵 Thread allocation:")
        self.logger.info(
            f"   I/O threads: {io_threads} (memory limit: {max_threads_by_memory}, CPU limit: {max_threads_by_cpu})"
        )
        self.logger.info(f"   CPU processes: {cpu_processes}")

        return {
            "io_threads": io_threads,
            "cpu_processes": cpu_processes,
            "memory_budget": thread_memory_budget,
            "per_thread_memory": per_thread_memory,
        }

    def enforce_memory_limits(self, resources: dict[str, Any]):
        """Enforce container memory limits on Python process"""

        if not self.config.memory_limit_detection or not resources["container_detected"]:
            self.logger.info("Memory limit enforcement disabled or not in container")
            return

        memory_limit = resources["memory_bytes"]
        safety_margin = self.config.memory_safety_margin

        # Calculate Python process memory limit
        python_memory_limit = int(memory_limit * (1 - safety_margin))

        try:
            # Force Python to respect memory limit
            resource.setrlimit(resource.RLIMIT_AS, (python_memory_limit, python_memory_limit))

            self.logger.info("Memory limits enforced:")
            self.logger.info(f"   Container limit: {memory_limit/1024/1024/1024:.2f}GB")
            self.logger.info(f"   Python limit: {python_memory_limit/1024/1024/1024:.2f}GB")
            self.logger.info(f"   Safety margin: {safety_margin*100:.0f}%")

        except Exception as e:
            self.logger.error(f"Could not enforce memory limits: {e}")


class MetricsManager:
    """Manages Prometheus metrics and monitoring"""

    def __init__(self, config: ContainerConfig, resources: dict[str, Any]):
        self.config = config
        self.resources = resources
        self.logger = logger
        self.registry = None  # Initialize registry

        if config.enable_prometheus:
            self._setup_prometheus_metrics()

    def _setup_prometheus_metrics(self):
        """Setup default enterprise metrics"""
        try:
            from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

            # Create custom registry for this app
            self.registry = CollectorRegistry()

            # Process metrics
            self.memory_usage = Gauge(
                "container_memory_usage_bytes", "Container memory usage in bytes", registry=self.registry
            )

            self.memory_limit = Gauge(
                "container_memory_limit_bytes", "Container memory limit in bytes", registry=self.registry
            )

            self.cpu_usage = Gauge(
                "container_cpu_usage_percent", "Container CPU usage percentage", registry=self.registry
            )

            self.thread_count = Gauge("container_thread_count", "Number of threads in use", registry=self.registry)

            # Application metrics
            self.requests_total = Counter(
                "app_requests_total",
                "Total application requests",
                ["method", "endpoint", "status"],
                registry=self.registry,
            )

            self.request_duration = Histogram(
                "app_request_duration_seconds", "Application request duration", registry=self.registry
            )

            # LLM-specific metrics
            self.llm_requests_total = Counter(
                "llm_requests_total", "Total LLM API requests", ["provider", "model", "status"], registry=self.registry
            )

            self.llm_response_size = Histogram(
                "llm_response_size_bytes", "LLM response size in bytes", registry=self.registry
            )

            # Initialize static metrics
            if self.resources["memory_bytes"]:
                self.memory_limit.set(self.resources["memory_bytes"])

            self.logger.info("Prometheus metrics initialized")

        except ImportError:
            self.logger.warning("prometheus-client not available, metrics disabled")
            self.registry = None

    def get_metrics_endpoint(self) -> str:
        """Get Prometheus metrics in standard format"""
        if not self.registry:
            return "# Metrics not available\n"

        try:
            from prometheus_client import generate_latest

            return generate_latest(self.registry).decode("utf-8")
        except Exception as e:
            self.logger.error(f"Metrics generation failed: {e}")
            return f"# Error generating metrics: {e}\n"


class ContainerApp:
    """
    Enterprise container application abstraction

    Provides "attach later" deployment pattern:
    1. Develop core business logic without container concerns
    2. Attach ContainerApp when ready for deployment
    3. Get enterprise features automatically (metrics, health, graceful shutdown)
    """

    def __init__(self, business_logic: Any, config: ContainerConfig, custom_metrics: dict | None = None):

        self.business_logic = business_logic
        self.config = config
        self.shutdown_event = threading.Event()
        self.logger = logger

        # Load hyperlib configuration (avoid naming conflict)
        from . import config as hyperlib_config

        self.settings = hyperlib_config.get_settings()

        # Resource management
        self.resource_manager = ResourceManager(config)
        self.resources = self.resource_manager.detect_container_resources()

        # Enforce memory limits early
        self.resource_manager.enforce_memory_limits(self.resources)

        # Calculate thread limits
        self.thread_limits = self.resource_manager.calculate_safe_thread_limits(self.resources)

        # Setup metrics
        self.metrics_manager = MetricsManager(config, self.resources)

        # Setup thread pools
        self._setup_thread_pools()

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Setup memory monitoring
        if config.memory_monitoring:
            self._setup_memory_guardian()

        logger.info(f"🏗️ ContainerApp '{config.app_name}' initialized")
        logger.info(f"   Resource detection: {self.resources['detection_method']}")
        logger.info(
            f"   Thread allocation: {self.thread_limits['io_threads']} I/O, {self.thread_limits['cpu_processes']} CPU"
        )

    def _setup_thread_pools(self):
        """Setup thread and process pools based on resource calculations"""

        # I/O thread pool for LLM APIs and network operations
        self.io_thread_pool = ThreadPoolExecutor(
            max_workers=self.thread_limits["io_threads"], thread_name_prefix=f"{self.config.app_name}_io"
        )

        # CPU process pool for compute-intensive tasks
        self.cpu_process_pool = ProcessPoolExecutor(max_workers=self.thread_limits["cpu_processes"])

        logger.info("🏊 Thread pools initialized")

    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers"""

        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            logger.info(f"🛑 Received {signal_name}, initiating graceful shutdown...")
            self.shutdown_event.set()

        # Register handlers for graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C

        logger.info("Signal handlers registered")

    def _setup_memory_guardian(self):
        """Setup proactive memory monitoring and protection"""

        def memory_guardian():
            """Memory monitoring loop"""
            while not self.shutdown_event.is_set():
                try:
                    self._check_memory_pressure()
                    time.sleep(5)  # Check every 5 seconds
                except Exception as e:
                    logger.error(f"Memory guardian error: {e}")
                    time.sleep(30)  # Back off on errors

        self.memory_guardian_thread = threading.Thread(
            target=memory_guardian, name=f"{self.config.app_name}_memory_guardian", daemon=True
        )
        self.memory_guardian_thread.start()

        logger.info("🔍 Memory guardian started")

    def _check_memory_pressure(self):
        """Check memory usage and take action if needed"""

        if not self.resources["container_detected"]:
            return  # Skip if not in container

        try:
            process = psutil.Process()
            memory_usage = process.memory_info().rss
            memory_percent = (memory_usage / self.resources["memory_bytes"]) * 100

            # Update metrics
            if self.metrics_manager.registry:
                self.metrics_manager.memory_usage.set(memory_usage)
                self.metrics_manager.cpu_usage.set(psutil.cpu_percent())

                # Count active threads
                thread_count = threading.active_count()
                self.metrics_manager.thread_count.set(thread_count)

            # Progressive memory pressure response
            if memory_percent > self.config.memory_alert_threshold * 100:
                logger.warning(f"Memory pressure: {memory_percent:.1f}%")

                # Trigger garbage collection
                import gc

                gc.collect()

            if memory_percent > self.config.memory_critical_threshold * 100:
                logger.error(f"Critical memory usage: {memory_percent:.1f}%")
                self._emergency_memory_management()

            if memory_percent > 95:
                logger.critical(f"💀 Imminent OOM: {memory_percent:.1f}%")
                self._emergency_shutdown("memory_exhaustion")

        except Exception as e:
            logger.error(f"Memory check failed: {e}")

    def _emergency_memory_management(self):
        """Emergency response to high memory usage"""
        import gc

        # Aggressive garbage collection
        for _ in range(3):
            gc.collect()

        logger.warning("Emergency memory management activated")

    def _emergency_shutdown(self, reason: str):
        """Emergency graceful shutdown to prevent OOM kill"""
        logger.critical(f"💀 Emergency shutdown: {reason}")

        # Save critical state if possible
        try:
            self._save_emergency_state()
        except Exception as e:
            logger.error(f"Could not save emergency state: {e}")

        # Trigger shutdown
        self.shutdown_event.set()

    def _save_emergency_state(self):
        """Save critical application state during emergency"""
        if self.config.mounts.temp_dir:
            emergency_file = self.config.mounts.temp_dir / f"{self.config.app_name}_emergency_state.json"

            state = {
                "timestamp": time.time(),
                "reason": "memory_exhaustion",
                "memory_usage": psutil.Process().memory_info().rss,
                "thread_count": threading.active_count(),
                "resources": self.resources,
            }

            with open(emergency_file, "w") as f:
                json.dump(state, f, indent=2)

    # Three deployment patterns

    def run_daemon(self):
        """Pattern 1: Long-running daemon process"""
        logger.info(f"Starting daemon: {self.config.app_name}")

        try:
            # Start metrics server if enabled
            if self.config.enable_metrics:
                self._start_metrics_server()

            # Call business logic main loop
            if hasattr(self.business_logic, "run_daemon"):
                self.business_logic.run_daemon(
                    shutdown_event=self.shutdown_event,
                    thread_pool=self.io_thread_pool,
                    process_pool=self.cpu_process_pool,
                )
            else:
                # Generic daemon loop
                while not self.shutdown_event.is_set():
                    time.sleep(1)

        except KeyboardInterrupt:
            logger.info("🛑 Keyboard interrupt received")
        finally:
            self._graceful_shutdown()

    def run_daemon_api(self, fastapi_app: Any | None = None):
        """Pattern 2: Long-running daemon + FastAPI REST control"""
        logger.info(f"Starting daemon with API: {self.config.app_name}")

        try:
            # Create FastAPI app if not provided
            if fastapi_app is None:
                fastapi_app = self._create_default_api()

            # Add control endpoints
            self._add_control_endpoints(fastapi_app)

            # Start metrics server
            if self.config.enable_metrics:
                self._start_metrics_server()

            # Start FastAPI in background thread
            import uvicorn

            api_thread = threading.Thread(
                target=lambda: uvicorn.run(
                    fastapi_app, host="0.0.0.0", port=self.config.api_port, log_config=None  # Use hyperlib logger
                ),
                daemon=True,
            )
            api_thread.start()

            # Run business logic
            if hasattr(self.business_logic, "run_daemon"):
                self.business_logic.run_daemon(
                    shutdown_event=self.shutdown_event,
                    thread_pool=self.io_thread_pool,
                    process_pool=self.cpu_process_pool,
                )
            else:
                # Generic daemon loop
                while not self.shutdown_event.is_set():
                    time.sleep(1)

        except KeyboardInterrupt:
            logger.info("🛑 Keyboard interrupt received")
        finally:
            self._graceful_shutdown()

    def run_oneshot(self, task_func: Callable):
        """Pattern 3: CLI one-shot execution with monitoring"""
        logger.info(f"⚡ Starting one-shot task: {self.config.app_name}")

        try:
            # Start metrics server for monitoring
            if self.config.enable_metrics:
                self._start_metrics_server()

            # Execute task with resource monitoring
            start_time = time.time()

            if hasattr(task_func, "__code__") and "thread_pool" in task_func.__code__.co_varnames:
                # Task accepts thread pool
                result = task_func(thread_pool=self.io_thread_pool, process_pool=self.cpu_process_pool)
            else:
                # Simple task execution
                result = task_func()

            duration = time.time() - start_time
            logger.info(f"One-shot task completed in {duration:.2f}s")

            return result

        except Exception as e:
            logger.error(f"One-shot task failed: {e}")
            raise
        finally:
            self._graceful_shutdown()

    def _start_metrics_server(self):
        """Start Prometheus metrics HTTP server"""
        if not self.config.enable_prometheus or not self.metrics_manager.registry:
            return

        try:
            from prometheus_client import start_http_server

            start_http_server(self.config.metrics_port, registry=self.metrics_manager.registry)
            logger.info(f"Metrics server started on port {self.config.metrics_port}")
        except Exception as e:
            logger.error(f"Could not start metrics server: {e}")

    def _create_default_api(self):
        """Create default FastAPI app with health endpoints"""
        try:
            from fastapi import FastAPI

            app = FastAPI(
                title=self.config.app_name, description="Enterprise containerized application", version="1.0.0"
            )

            @app.get("/health")
            async def health():
                return {
                    "status": "healthy",
                    "app": self.config.app_name,
                    "memory_percent": self._get_memory_percent(),
                    "thread_count": threading.active_count(),
                }

            @app.get("/ready")
            async def ready():
                return {
                    "status": "ready" if not self.shutdown_event.is_set() else "shutting_down",
                    "app": self.config.app_name,
                }

            return app

        except ImportError:
            logger.warning("FastAPI not available, API endpoints disabled")
            return None

    def _add_control_endpoints(self, fastapi_app):
        """Add control endpoints to FastAPI app"""
        if not fastapi_app:
            return

        @fastapi_app.post("/control/shutdown")
        async def shutdown():
            logger.info("🛑 Shutdown requested via API")
            self.shutdown_event.set()
            return {"status": "shutdown_initiated"}

        @fastapi_app.get("/control/status")
        async def status():
            return {
                "app": self.config.app_name,
                "status": "running" if not self.shutdown_event.is_set() else "shutting_down",
                "uptime": time.time() - self.start_time,
                "resources": self.resources,
                "thread_limits": self.thread_limits,
                "memory_percent": self._get_memory_percent(),
            }

    def _get_memory_percent(self) -> float:
        """Get current memory usage percentage"""
        try:
            if self.resources["container_detected"]:
                memory_usage = psutil.Process().memory_info().rss
                return (memory_usage / self.resources["memory_bytes"]) * 100
            return 0.0
        except:
            return 0.0

    def _graceful_shutdown(self):
        """Perform graceful shutdown"""
        logger.info("Performing graceful shutdown...")

        # Shutdown thread pools
        try:
            # ThreadPoolExecutor.shutdown() doesn't support timeout parameter
            # Use wait=True and cancel_futures=True for Python 3.9+ compatibility

            self.io_thread_pool.shutdown(wait=True, cancel_futures=True)
            self.cpu_process_pool.shutdown(wait=True, cancel_futures=True)

            logger.info("Thread pools shut down")
        except Exception as e:
            logger.error(f"Thread pool shutdown error: {e}")

        # Call business logic cleanup if available
        try:
            if hasattr(self.business_logic, "cleanup"):
                self.business_logic.cleanup()
                logger.info("Business logic cleanup completed")
        except Exception as e:
            logger.error(f"Business logic cleanup error: {e}")

        logger.info("Graceful shutdown completed")


# Convenience functions for common patterns


def create_daemon_app(business_logic: Any, app_name: str, mounts: MountConfig | None = None, **kwargs) -> ContainerApp:
    """Create daemon application with sensible defaults"""

    if mounts is None:
        mounts = MountConfig(config_dir=Path("/app/config"), data_dir=Path("/app/data"), temp_dir=Path("/app/tmp"))

    config = ContainerConfig(app_name=app_name, mounts=mounts, **kwargs)

    return ContainerApp(business_logic, config)


def create_api_daemon_app(business_logic: Any, app_name: str, api_port: int = 8000, **kwargs) -> ContainerApp:
    """Create daemon + API application"""

    return create_daemon_app(business_logic, app_name, api_port=api_port, **kwargs)


def create_oneshot_app(task_func: Callable, app_name: str, **kwargs) -> Any:
    """Create and run one-shot application"""

    app = create_daemon_app(None, app_name, **kwargs)
    return app.run_oneshot(task_func)
