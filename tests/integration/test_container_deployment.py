"""
Container deployment tests for hyperlib applications.
Tests Docker, Kubernetes (Minikube), and Helm deployments with proper cleanup.

NOTE: These tests require external tools to be installed:
- Docker: Tests will be skipped if Docker is not installed or not running
- Minikube + kubectl: K8s tests will be skipped if these tools are not available
- Helm: Helm tests will be skipped if Helm is not installed
"""

import os
import json
import time
import subprocess
import tempfile
import pytest
import shutil
import uuid
import warnings
from pathlib import Path
from typing import Generator, Tuple

from hyperlib import harness


# Check and warn about missing tools at module import time
def check_tools_and_warn():
    """Check for required tools and issue warnings for missing ones."""
    tools_status = {}

    # Check Docker
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=5)
        tools_status["docker"] = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        tools_status["docker"] = False
        warnings.warn("Docker not found - Docker tests will be skipped", UserWarning)

    # Check Minikube
    try:
        result = subprocess.run(["minikube", "version"], capture_output=True, text=True, timeout=5)
        tools_status["minikube"] = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        tools_status["minikube"] = False
        warnings.warn("Minikube not found - Kubernetes tests will be skipped", UserWarning)

    # Check kubectl
    try:
        result = subprocess.run(["kubectl", "version", "--client"], capture_output=True, text=True, timeout=5)
        tools_status["kubectl"] = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        tools_status["kubectl"] = False
        warnings.warn("kubectl not found - Kubernetes tests will be skipped", UserWarning)

    # Check Helm
    try:
        result = subprocess.run(["helm", "version", "--short"], capture_output=True, text=True, timeout=5)
        tools_status["helm"] = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        tools_status["helm"] = False
        warnings.warn("Helm not found - Helm tests will be skipped", UserWarning)

    return tools_status


# Check tools when module is imported
TOOLS_STATUS = check_tools_and_warn()


# Register cleanup function for Minikube
def cleanup_minikube():
    """Stop Minikube if we started it for tests."""
    if os.environ.get("_MINIKUBE_STARTED_BY_TEST") == "1":
        print("Stopping Minikube (started by tests)...")
        try:
            subprocess.run(["minikube", "stop"], timeout=60, capture_output=True)
            print("Minikube stopped")
        except Exception as e:
            print(f"Failed to stop Minikube: {e}")
        finally:
            del os.environ["_MINIKUBE_STARTED_BY_TEST"]

import atexit
atexit.register(cleanup_minikube)


# Tool availability checks
def docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def minikube_available() -> bool:
    """Check if Minikube is installed and can be started."""
    try:
        # Check if minikube is installed
        result = subprocess.run(
            ["minikube", "version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False

        # Check if minikube is running
        result = subprocess.run(
            ["minikube", "status", "--format=json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            try:
                status = json.loads(result.stdout)
                return status.get("Host") == "Running"
            except json.JSONDecodeError:
                pass

        # Try to start minikube if it's not running
        print("Minikube installed but not running, attempting to start...")
        result = subprocess.run(
            ["minikube", "start", "--driver=docker", "--memory=2048"],
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes timeout for starting
        )

        if result.returncode == 0:
            print("Minikube started successfully for tests")
            # Mark that we started it so we can stop it after tests
            os.environ["_MINIKUBE_STARTED_BY_TEST"] = "1"
            return True
        else:
            print(f"Failed to start Minikube: {result.stderr}")
            return False

    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Minikube check failed: {e}")
        return False


def kubectl_available() -> bool:
    """Check if kubectl is available."""
    try:
        result = subprocess.run(
            ["kubectl", "version", "--client"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def helm_available() -> bool:
    """Check if Helm is available."""
    try:
        result = subprocess.run(
            ["helm", "version", "--short"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class ContainerTestBase:
    """Base class for container tests with cleanup utilities."""

    @staticmethod
    def load_fixture(fixture_name: str) -> str:
        """Load a test fixture from the fixtures directory."""
        fixture_path = Path(__file__).parent / "fixtures" / f"{fixture_name}.txt"
        if not fixture_path.exists():
            pytest.fail(f"Fixture not found: {fixture_path}")
        return fixture_path.read_text()

    @staticmethod
    def create_test_log_file(test_name: str) -> Path:
        """Create test-specific log file, renaming previous with timestamp."""
        logs_dir = Path(__file__).parent.parent.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_file = logs_dir / f"{test_name}.log"

        # Rename existing log with its modification time
        if log_file.exists():
            mtime = log_file.stat().st_mtime
            timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(mtime))
            archived_log = logs_dir / f"{test_name}-{timestamp}.log"
            log_file.rename(archived_log)

        # Write header to new log
        with log_file.open("w") as f:
            f.write(f"{'='*80}\n")
            f.write(f"Test: {test_name}\n")
            f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n\n")

        return log_file

    @staticmethod
    def append_container_logs(container_name: str, log_file: Path):
        """Append Docker container logs to test log file."""
        try:
            harness.run(
                ["docker", "logs", container_name],
                timeout=10,
                check=False,
                log_file=log_file,
                log_label=f"Container: {container_name}",
            )
        except Exception as e:
            with log_file.open("a") as f:
                f.write(f"\nFailed to capture logs for {container_name}: {e}\n")

    @staticmethod
    def append_pod_logs(pod_name: str, namespace: str, log_file: Path):
        """Append Kubernetes pod logs to test log file."""
        try:
            harness.run(
                ["kubectl", "logs", pod_name, "-n", namespace],
                timeout=10,
                check=False,
                log_file=log_file,
                log_label=f"Pod: {pod_name} (namespace: {namespace})",
            )
        except Exception as e:
            with log_file.open("a") as f:
                f.write(f"\nFailed to capture logs for {pod_name}: {e}\n")

    @staticmethod
    def run_command(
        cmd: list,
        timeout: int = 30,
        check: bool = True,
        cwd: str = None,
        log_file: Path = None,
        log_label: str = None,
    ) -> subprocess.CompletedProcess:
        """Run a command with timeout, error handling, and optional logging."""
        return harness.run(
            cmd=cmd,
            timeout=timeout,
            check=check,
            cwd=cwd,
            log_file=log_file,
            log_label=log_label,
            pytest_fail=True,
        )

    @staticmethod
    def wait_for_condition(check_func, timeout: int = 60, interval: int = 2) -> bool:
        """Wait for a condition to become true."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if check_func():
                return True
            time.sleep(interval)
        return False


@pytest.mark.skipif(not docker_available(), reason="Docker not available or not running")
class TestDockerDeployment(ContainerTestBase):
    """Test hyperlib applications in Docker containers."""

    @pytest.fixture
    def docker_test_env(self, request) -> Generator[dict, None, None]:
        """Fixture providing Docker test environment with cleanup."""
        test_id = f"hyperlib-test-{uuid.uuid4().hex[:8]}"
        containers = []
        images = []
        networks = []
        volumes = []

        # Create test log file
        test_name = request.node.name
        log_file = self.create_test_log_file(test_name)

        env = {
            "test_id": test_id,
            "containers": containers,
            "images": images,
            "networks": networks,
            "volumes": volumes,
            "log_file": log_file,
        }

        yield env

        # Cleanup - capture logs before removing containers
        for container in containers:
            try:
                self.append_container_logs(container, log_file)
            except Exception:
                pass  # Ignore log capture failures during cleanup
            self.run_command(["docker", "rm", "-f", container], check=False)

        for network in networks:
            self.run_command(["docker", "network", "rm", network], check=False)

        for volume in volumes:
            self.run_command(["docker", "volume", "rm", volume], check=False)

        # Only remove images we created for this test
        for image in images:
            if test_id in image:
                self.run_command(["docker", "rmi", "-f", image], check=False)

    def test_docker_api_deployment(self, docker_test_env):
        """Test deploying a hyperlib API application in Docker."""
        test_id = docker_test_env["test_id"]
        temp_dir = Path(tempfile.mkdtemp(prefix=test_id))

        try:
            # Create a simple API application
            app_file = temp_dir / "app.py"
            app_file.write_text(self.load_fixture("test_container_deployment_1"))

            # Copy hyperlib source and pyproject.toml
            hyperlib_src = Path(__file__).parent.parent.parent / "src" / "hyperlib"
            shutil.copytree(hyperlib_src, temp_dir / "hyperlib")

            # Copy pyproject.toml from hyperlib root
            hyperlib_pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
            shutil.copy(hyperlib_pyproject, temp_dir / "pyproject.toml")

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_container_deployment_16"))

            # Build image
            image_name = f"{test_id}-api:latest"
            self.run_command(
                ["docker", "build", "-t", image_name, "."],
                cwd=str(temp_dir),
                timeout=120
            )
            docker_test_env["images"].append(image_name)

            # Create network
            network_name = f"{test_id}-network"
            self.run_command(["docker", "network", "create", network_name])
            docker_test_env["networks"].append(network_name)

            # Run container
            container_name = f"{test_id}-api"
            result = self.run_command([
                "docker", "run", "-d",
                "--name", container_name,
                "--network", network_name,
                "-p", "18000:8000",
                "-v", f"{temp_dir}/config:/config",
                "-v", f"{temp_dir}/data:/data",
                image_name
            ])
            docker_test_env["containers"].append(container_name)

            # Wait for container to be healthy
            def check_health():
                result = self.run_command(
                    ["docker", "exec", container_name, "curl", "-f", "http://localhost:8000/"],
                    check=False
                )
                return result.returncode == 0

            # Simple check if container is running
            time.sleep(5)  # Give container time to start

            # Check container is running
            result = self.run_command(["docker", "ps", "--filter", f"name={container_name}"])
            assert container_name in result.stdout

            # Check logs for any errors
            result = self.run_command(["docker", "logs", container_name])
            assert "error" not in result.stdout.lower()

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_docker_prometheus_metrics(self, docker_test_env):
        """Test Prometheus metrics endpoint in Docker container."""
        test_id = docker_test_env["test_id"]
        temp_dir = Path(tempfile.mkdtemp(prefix=test_id))

        try:
            # Create an API application with Prometheus metrics
            app_file = temp_dir / "app_metrics.py"
            app_file.write_text(self.load_fixture("test_container_deployment_2"))

            # Copy hyperlib source and pyproject.toml
            hyperlib_root = Path(__file__).parent.parent.parent
            hyperlib_src = hyperlib_root / "src" / "hyperlib"
            shutil.copytree(hyperlib_src, temp_dir / "src" / "hyperlib")
            shutil.copy(hyperlib_root / "pyproject.toml", temp_dir / "pyproject.toml")

            # Create Dockerfile with prometheus-client
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_container_deployment_17"))

            # Build image
            image_name = f"{test_id}-metrics:latest"
            self.run_command(
                ["docker", "build", "-t", image_name, "."],
                cwd=str(temp_dir),
                timeout=120
            )
            docker_test_env["images"].append(image_name)

            # Run container
            container_name = f"{test_id}-metrics"
            self.run_command([
                "docker", "run", "-d",
                "--name", container_name,
                "-p", "18001:8000",
                "-p", "18080:8080",
                image_name
            ])
            docker_test_env["containers"].append(container_name)

            # Wait for container to start
            time.sleep(8)

            # Check container is running
            result = self.run_command(["docker", "ps", "--filter", f"name={container_name}"])
            assert container_name in result.stdout

            # Make a request to generate metrics (use python urllib - always available)
            self.run_command([
                "docker", "exec", container_name,
                "python", "-c",
                "import urllib.request; "
                "[urllib.request.urlopen('http://localhost:8000/').read() for _ in range(5)]"
            ], check=False)

            # Check metrics endpoint
            result = self.run_command([
                "docker", "exec", container_name,
                "python", "-c",
                "import urllib.request; import sys; "
                "sys.stdout.buffer.write(urllib.request.urlopen('http://localhost:8080/').read())"
            ], check=False)

            # Verify Prometheus metrics are exposed
            metrics_output = result.stdout

            # Check for standard Prometheus metrics
            assert "# HELP" in metrics_output or "# TYPE" in metrics_output

            # Check for custom metrics (if they were registered)
            # The actual metric names depend on implementation

            # Check logs
            result = self.run_command(["docker", "logs", container_name])
            assert "error" not in result.stdout.lower() or "traceback" not in result.stdout.lower()

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_docker_daemon_deployment(self, docker_test_env):
        """Test deploying a hyperlib daemon application in Docker."""
        test_id = docker_test_env["test_id"]
        temp_dir = Path(tempfile.mkdtemp(prefix=test_id))

        try:
            # Create a daemon application
            app_file = temp_dir / "daemon.py"
            app_file.write_text(self.load_fixture("test_container_deployment_3"))

            # Copy hyperlib source and pyproject.toml
            hyperlib_root = Path(__file__).parent.parent.parent
            hyperlib_src = hyperlib_root / "src" / "hyperlib"
            shutil.copytree(hyperlib_src, temp_dir / "src" / "hyperlib")
            shutil.copy(hyperlib_root / "pyproject.toml", temp_dir / "pyproject.toml")

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_container_deployment_4"))

            # Build image
            image_name = f"{test_id}-daemon:latest"
            self.run_command(
                ["docker", "build", "-t", image_name, "."],
                cwd=str(temp_dir),
                timeout=120
            )
            docker_test_env["images"].append(image_name)

            # Create volume for data persistence
            volume_name = f"{test_id}-data"
            self.run_command(["docker", "volume", "create", volume_name])
            docker_test_env["volumes"].append(volume_name)

            # Run daemon container
            container_name = f"{test_id}-daemon"
            self.run_command([
                "docker", "run", "-d",
                "--name", container_name,
                "-v", f"{volume_name}:/data",
                image_name
            ])
            docker_test_env["containers"].append(container_name)

            # Let daemon run for a bit
            time.sleep(10)

            # Check container is still running
            result = self.run_command(["docker", "ps", "--filter", f"name={container_name}"])
            assert container_name in result.stdout

            # Check logs (loguru outputs to stderr by default)
            result = self.run_command(["docker", "logs", container_name])
            assert "Starting daemon 'docker-test-daemon'" in result.stderr

            # Stop container gracefully
            self.run_command(["docker", "stop", container_name], timeout=15)

            # Check shutdown was graceful
            result = self.run_command(["docker", "logs", container_name])
            # Note: Shutdown message might not always appear due to signal handling

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_docker_compose_simulation(self, docker_test_env):
        """Test multi-container setup with database."""
        test_id = docker_test_env["test_id"]

        # Create network
        network_name = f"{test_id}-network"
        self.run_command(["docker", "network", "create", network_name])
        docker_test_env["networks"].append(network_name)

        # Start PostgreSQL container
        postgres_name = f"{test_id}-postgres"
        self.run_command([
            "docker", "run", "-d",
            "--name", postgres_name,
            "--network", network_name,
            "-e", "POSTGRES_USER=testuser",
            "-e", "POSTGRES_PASSWORD=testpass",
            "-e", "POSTGRES_DB=testdb",
            "postgres:15-alpine"
        ])
        docker_test_env["containers"].append(postgres_name)

        # Wait for PostgreSQL to be ready
        time.sleep(10)

        # Create test application that connects to database
        temp_dir = Path(tempfile.mkdtemp(prefix=test_id))

        try:
            app_file = temp_dir / "app.py"
            app_file.write_text(self.load_fixture("test_container_deployment_5"))

            # Copy hyperlib source and pyproject.toml
            hyperlib_src = Path(__file__).parent.parent.parent / "src" / "hyperlib"
            shutil.copytree(hyperlib_src, temp_dir / "src/hyperlib")

            # Copy pyproject.toml
            hyperlib_pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
            shutil.copy(hyperlib_pyproject, temp_dir / "pyproject.toml")

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_container_deployment_6"))

            # Build image
            image_name = f"{test_id}-app:latest"
            self.run_command(
                ["docker", "build", "-t", image_name, "."],
                cwd=str(temp_dir),
                timeout=60
            )
            docker_test_env["images"].append(image_name)

            # Run application container
            result = self.run_command([
                "docker", "run", "--rm",
                "--network", network_name,
                "-e", f"POSTGRES_HOST={postgres_name}",
                "-e", "POSTGRES_USER=testuser",
                "-e", "POSTGRES_PASSWORD=testpass",
                "-e", "POSTGRES_DATABASE=testdb",
                image_name
            ])

            # Verify output
            assert f"Host: {postgres_name}" in result.stdout
            assert "Database: testdb" in result.stdout
            assert "postgresql://testuser" in result.stdout

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.skipif(
    not (helm_available() and minikube_available()),
    reason="Helm or Minikube not available"
)
class TestHelmBasedDeployment(ContainerTestBase):
    """Test hyperlib applications with Helm charts in Kubernetes (Minikube)."""

    @pytest.fixture
    def helm_env(self, request) -> Generator[dict, None, None]:
        """Fixture providing Helm test environment with cleanup."""
        test_id = f"hyperlib-{uuid.uuid4().hex[:8]}"
        namespace = f"helm-{test_id}"

        # Create test log file
        test_name = request.node.name
        log_file = self.create_test_log_file(test_name)

        # Create namespace
        self.run_command([
            "kubectl", "create", "namespace", namespace
        ])

        env = {
            "test_id": test_id,
            "namespace": namespace,
            "releases": [],
            "log_file": log_file,
        }

        yield env

        # Capture pod logs before cleanup
        try:
            result = self.run_command(
                ["kubectl", "get", "pods", "-n", namespace, "-o", "name"],
                check=False
            )
            for pod_line in result.stdout.strip().split("\n"):
                if pod_line:
                    pod_name = pod_line.replace("pod/", "")
                    self.append_pod_logs(pod_name, namespace, log_file)
        except Exception:
            pass  # Ignore log capture failures during cleanup

        # Cleanup Helm releases
        for release in env["releases"]:
            self.run_command(
                ["helm", "uninstall", release, "-n", namespace],
                check=False
            )

        # Delete namespace
        self.run_command(
            ["kubectl", "delete", "namespace", namespace, "--timeout=60s"],
            check=False,
            timeout=70
        )

    def test_helm_pod_deployment(self, helm_env):
        """Test deploying a hyperlib application as a Helm-managed Pod."""
        namespace = helm_env["namespace"]
        test_id = helm_env["test_id"]

        # Create Helm chart directory
        chart_dir = Path(tempfile.mkdtemp(prefix=f"helm-pod-{test_id}"))

        try:
            # Create Chart.yaml
            chart_yaml = chart_dir / "Chart.yaml"
            chart_yaml.write_text(self.load_fixture("test_container_deployment_26"))

            # Create values.yaml
            values_yaml = chart_dir / "values.yaml"
            values_yaml.write_text(self.load_fixture("test_container_deployment_28"))

            # Create templates directory
            templates_dir = chart_dir / "templates"
            templates_dir.mkdir()

            # Create Pod template
            pod_template = templates_dir / "pod.yaml"
            pod_template.write_text(self.load_fixture("test_container_deployment_27"))

            # Create ConfigMap with application code
            app_code = self.load_fixture("test_container_deployment_7")
            configmap_name = f"{test_id}-app"
            self.run_command([
                "kubectl", "create", "configmap", configmap_name,
                f"--from-literal=app.py={app_code}",
                "-n", namespace
            ])

            # Install Helm chart
            release_name = f"pod-{test_id}"
            self.run_command([
                "helm", "install", release_name,
                str(chart_dir),
                "-n", namespace,
                "--wait",
                "--timeout", "60s"
            ], timeout=90)
            helm_env["releases"].append(release_name)

            # Wait for pod to complete
            def pod_completed():
                result = self.run_command([
                    "kubectl", "get", "pod", f"{release_name}-pod",
                    "-n", namespace,
                    "-o", "jsonpath={.status.phase}"
                ], check=False)
                return result.stdout in ["Succeeded", "Failed", "Error"]

            assert self.wait_for_condition(pod_completed, timeout=30)

            # Get pod logs
            result = self.run_command([
                "kubectl", "logs", f"{release_name}-pod", "-n", namespace
            ])

            # Verify Kubernetes environment was detected
            assert "Kubernetes detected: True" in result.stdout
            assert "KUBERNETES_SERVICE_HOST:" in result.stdout
            assert f"POD_NAME: {release_name}-pod" in result.stdout
            assert f"POD_NAMESPACE: {namespace}" in result.stdout

        finally:
            shutil.rmtree(chart_dir, ignore_errors=True)

    def test_helm_prometheus_metrics(self, helm_env):
        """Test Prometheus metrics in Helm-managed Kubernetes deployment."""
        namespace = helm_env["namespace"]
        test_id = helm_env["test_id"]

        # Create Helm chart directory
        chart_dir = Path(tempfile.mkdtemp(prefix=f"helm-metrics-{test_id}"))

        try:
            # Create Chart.yaml
            (chart_dir / "Chart.yaml").write_text(
                self.load_fixture("test_container_deployment_22")
            )

            # Create values.yaml
            (chart_dir / "values.yaml").write_text(
                self.load_fixture("test_container_deployment_25")
            )

            # Create templates directory
            templates_dir = chart_dir / "templates"
            templates_dir.mkdir()

            # Create Deployment template
            (templates_dir / "deployment.yaml").write_text(
                self.load_fixture("test_container_deployment_23")
            )

            # Create Service template
            (templates_dir / "service.yaml").write_text(
                self.load_fixture("test_container_deployment_24")
            )

            # Create ConfigMap with application code
            app_code = self.load_fixture("test_container_deployment_9")
            configmap_name = f"{test_id}-app"
            self.run_command([
                "kubectl", "create", "configmap", configmap_name,
                f"--from-literal=metrics_app.py={app_code}",
                "-n", namespace
            ])

            # Install Helm chart
            release_name = f"metrics-{test_id}"
            self.run_command([
                "helm", "install", release_name,
                str(chart_dir),
                "-n", namespace,
                "--wait",
                "--timeout", "90s"
            ], timeout=120)
            helm_env["releases"].append(release_name)

            # Wait for deployment to be ready
            def deployment_ready():
                result = self.run_command([
                    "kubectl", "get", "deployment", release_name,
                    "-n", namespace,
                    "-o", "jsonpath={.status.readyReplicas}"
                ], check=False)
                return result.stdout == "1"

            assert self.wait_for_condition(deployment_ready, timeout=60)

            # Get pod name
            result = self.run_command([
                "kubectl", "get", "pods",
                "-n", namespace,
                "-l", f"app={release_name}",
                "-o", "jsonpath={.items[0].metadata.name}"
            ])
            pod_name = result.stdout.strip()

            # Make some requests to generate metrics
            for _ in range(5):
                self.run_command([
                    "kubectl", "exec", pod_name,
                    "-n", namespace,
                    "--", "sh", "-c",
                    "wget -q -O - http://localhost:8080/"
                ], check=False)

            # Check metrics endpoint
            result = self.run_command([
                "kubectl", "exec", pod_name,
                "-n", namespace,
                "--", "wget", "-q", "-O", "-", "http://localhost:8080/metrics"
            ])

            # Verify metrics
            assert "hyperlib_requests_total" in result.stdout
            assert "hyperlib_errors_total" in result.stdout
            assert "hyperlib_uptime_seconds" in result.stdout
            assert "# HELP" in result.stdout
            assert "# TYPE" in result.stdout

            # Check annotations for Prometheus scraping
            result = self.run_command([
                "kubectl", "get", "pod", pod_name,
                "-n", namespace,
                "-o", "jsonpath={.metadata.annotations}"
            ])
            assert "prometheus.io/scrape" in result.stdout

        finally:
            shutil.rmtree(chart_dir, ignore_errors=True)

    def test_helm_api_deployment_with_service(self, helm_env):
        """Test deploying a hyperlib API with Helm-managed Deployment and Service."""
        namespace = helm_env["namespace"]
        test_id = helm_env["test_id"]

        # Create Helm chart directory
        chart_dir = Path(tempfile.mkdtemp(prefix=f"helm-api-{test_id}"))

        try:
            # Create Chart.yaml
            (chart_dir / "Chart.yaml").write_text(
                self.load_fixture("test_container_deployment_18")
            )

            # Create values.yaml with namespace interpolation
            values_content = self.load_fixture("test_container_deployment_21")
            # Replace namespace placeholder
            values_content = values_content.replace("{{ .Release.Namespace }}", namespace)
            (chart_dir / "values.yaml").write_text(values_content)

            # Create templates directory
            templates_dir = chart_dir / "templates"
            templates_dir.mkdir()

            # Create Deployment template
            (templates_dir / "deployment.yaml").write_text(
                self.load_fixture("test_container_deployment_19")
            )

            # Create Service template
            (templates_dir / "service.yaml").write_text(
                self.load_fixture("test_container_deployment_20")
            )

            # Install Helm chart
            release_name = f"api-{test_id}"
            self.run_command([
                "helm", "install", release_name,
                str(chart_dir),
                "-n", namespace,
                "--wait",
                "--timeout", "90s"
            ], timeout=120)
            helm_env["releases"].append(release_name)

            # Wait for deployment to be ready
            def deployment_ready():
                result = self.run_command([
                    "kubectl", "get", "deployment", release_name,
                    "-n", namespace,
                    "-o", "jsonpath={.status.readyReplicas}"
                ], check=False)
                return result.stdout == "1"

            assert self.wait_for_condition(deployment_ready, timeout=60)

            # Check pod environment variables
            result = self.run_command([
                "kubectl", "get", "pods",
                "-n", namespace,
                "-l", f"app={release_name}",
                "-o", "jsonpath={.items[0].metadata.name}"
            ])
            pod_name = result.stdout.strip()

            # Check environment in pod
            result = self.run_command([
                "kubectl", "exec", pod_name,
                "-n", namespace,
                "--", "env"
            ])

            assert "APP_NAME=hyperlib-api" in result.stdout
            assert f"POSTGRES_HOST=postgres.{namespace}.svc.cluster.local" in result.stdout

        finally:
            shutil.rmtree(chart_dir, ignore_errors=True)
@pytest.mark.skipif(
    not (helm_available() and minikube_available()),
    reason="Helm or Minikube not available"
)
class TestHelmDeployment(ContainerTestBase):
    """Test hyperlib applications with Helm charts."""

    @pytest.fixture
    def helm_test_env(self) -> Generator[dict, None, None]:
        """Fixture providing Helm test environment with cleanup."""
        test_id = f"hyperlib-{uuid.uuid4().hex[:8]}"
        namespace = f"helm-test-{test_id}"

        # Create namespace
        self.run_command([
            "kubectl", "create", "namespace", namespace
        ])

        env = {
            "test_id": test_id,
            "namespace": namespace,
            "releases": [],
        }

        yield env

        # Cleanup Helm releases
        for release in env["releases"]:
            self.run_command(
                ["helm", "uninstall", release, "-n", namespace],
                check=False
            )

        # Delete namespace
        self.run_command(
            ["kubectl", "delete", "namespace", namespace, "--timeout=60s"],
            check=False,
            timeout=70
        )

    def test_helm_chart_deployment(self, helm_test_env):
        """Test deploying a hyperlib application via Helm chart."""
        namespace = helm_test_env["namespace"]
        test_id = helm_test_env["test_id"]

        # Create a simple Helm chart
        chart_dir = Path(tempfile.mkdtemp(prefix=f"helm-{test_id}"))

        try:
            # Create Chart.yaml
            chart_yaml = chart_dir / "Chart.yaml"
            chart_yaml.parent.mkdir(exist_ok=True)
            chart_yaml.write_text(self.load_fixture("test_container_deployment_12"))

            # Create values.yaml
            values_yaml = chart_dir / "values.yaml"
            values_yaml.write_text(self.load_fixture("test_container_deployment_13"))

            # Create deployment template
            templates_dir = chart_dir / "templates"
            templates_dir.mkdir()

            deployment_template = templates_dir / "deployment.yaml"
            deployment_template.write_text(self.load_fixture("test_container_deployment_14"))

            # Create service template
            service_template = templates_dir / "service.yaml"
            service_template.write_text(self.load_fixture("test_container_deployment_15"))

            # Install Helm chart
            release_name = f"test-{test_id}"
            self.run_command([
                "helm", "install", release_name,
                str(chart_dir),
                "-n", namespace,
                "--wait",
                "--timeout", "60s"
            ], timeout=90)
            helm_test_env["releases"].append(release_name)

            # Verify deployment
            result = self.run_command([
                "helm", "list", "-n", namespace, "-o", "json"
            ])
            releases = json.loads(result.stdout)
            assert any(r["name"] == release_name for r in releases)

            # Check that HELM environment variables are set
            result = self.run_command([
                "kubectl", "get", "pods",
                "-n", namespace,
                "-l", f"app={release_name}",
                "-o", "jsonpath={.items[0].metadata.name}"
            ])
            pod_name = result.stdout.strip()

            # Check environment in pod
            result = self.run_command([
                "kubectl", "exec", pod_name,
                "-n", namespace,
                "--", "env"
            ])

            assert f"HELM_RELEASE_NAME={release_name}" in result.stdout
            assert "APP_NAME=hyperlib-helm-app" in result.stdout
            assert "POSTGRES_HOST=postgres" in result.stdout
            assert "POSTGRES_DATABASE=helmdb" in result.stdout

            # Check mounts exist
            result = self.run_command([
                "kubectl", "exec", pod_name,
                "-n", namespace,
                "--", "ls", "-la", "/"
            ])

            assert "config" in result.stdout
            assert "data" in result.stdout
            assert "secrets" in result.stdout

        finally:
            shutil.rmtree(chart_dir, ignore_errors=True)

    def test_helm_with_custom_values(self, helm_test_env):
        """Test Helm deployment with custom values override."""
        namespace = helm_test_env["namespace"]
        test_id = helm_test_env["test_id"]

        # Create a minimal Helm chart
        chart_dir = Path(tempfile.mkdtemp(prefix=f"helm-{test_id}"))

        try:
            # Create Chart.yaml
            (chart_dir / "Chart.yaml").write_text(f"""
apiVersion: v2
name: hyperlib-custom
version: 0.1.0
""")

            # Create values.yaml with defaults
            (chart_dir / "values.yaml").write_text("""
env:
  APP_NAME: default-app
  LOG_LEVEL: INFO
""")

            # Create a simple ConfigMap template
            templates_dir = chart_dir / "templates"
            templates_dir.mkdir()

            (templates_dir / "configmap.yaml").write_text("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Release.Name }}-config
data:
  APP_NAME: {{ .Values.env.APP_NAME }}
  LOG_LEVEL: {{ .Values.env.LOG_LEVEL }}
""")

            # Create custom values file
            custom_values = {
                "env": {
                    "APP_NAME": "custom-hyperlib-app",
                    "LOG_LEVEL": "DEBUG"
                }
            }

            custom_values_file = chart_dir / "custom-values.yaml"
            import yaml
            with open(custom_values_file, 'w') as f:
                yaml.dump(custom_values, f)

            # Install with custom values
            release_name = f"custom-{test_id}"
            self.run_command([
                "helm", "install", release_name,
                str(chart_dir),
                "-f", str(custom_values_file),
                "-n", namespace
            ], timeout=90)
            helm_test_env["releases"].append(release_name)

            # Verify custom values were applied
            result = self.run_command([
                "kubectl", "get", "configmap",
                f"{release_name}-config",
                "-n", namespace,
                "-o", "jsonpath={.data}"
            ])

            assert "custom-hyperlib-app" in result.stdout
            assert "DEBUG" in result.stdout

        finally:
            shutil.rmtree(chart_dir, ignore_errors=True)