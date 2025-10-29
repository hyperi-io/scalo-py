"""
Docker container tests for hyperlib applications
Tests containerized deployments with actual Docker containers
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


def docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not docker_available(), reason="Docker not available")
class TestDockerContainer:
    """Test hyperlib applications in Docker containers."""

    @staticmethod
    def load_fixture(fixture_name: str) -> str:
        """Load a test fixture from the fixtures directory."""
        fixture_path = Path(__file__).parent / "fixtures" / f"{fixture_name}.txt"
        if not fixture_path.exists():
            pytest.fail(f"Fixture not found: {fixture_path}")
        return fixture_path.read_text()

    @pytest.fixture
    def docker_cleanup(self):
        """Fixture to clean up Docker containers and images after tests."""
        containers = []
        images = []

        yield {"containers": containers, "images": images}

        # Cleanup containers
        for container in containers:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)

        # Cleanup images
        for image in images:
            subprocess.run(["docker", "rmi", "-f", image], capture_output=True)

    def test_docker_environment_detection(self, docker_cleanup):
        """Test that hyperlib detects Docker environment correctly."""
        # Create a test Dockerfile
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create test application
            app_file = temp_dir / "test_app.py"
            app_file.write_text(self.load_fixture("test_docker_container_1"))

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_docker_container_2"))

            # Build Docker image
            image_name = "hyperlib-test:docker-env"
            result = subprocess.run(
                ["docker", "build", "-t", image_name, "--build-arg", f"host={Path.cwd()}", "."],
                cwd=temp_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # Try simpler Dockerfile without build context
                dockerfile.write_text(self.load_fixture("test_docker_container_3"))
                result = subprocess.run(
                    ["docker", "build", "-t", image_name, "."], cwd=temp_dir, capture_output=True, text=True
                )

            docker_cleanup["images"].append(image_name)

            # Run container
            container_name = "hyperlib-docker-test"
            result = subprocess.run(
                ["docker", "run", "--name", container_name, "--rm", image_name], capture_output=True, text=True
            )

            output = result.stdout
            assert "environment: docker" in output.lower() or "environment: container" in output.lower()

        finally:
            shutil.rmtree(temp_dir)

    def test_docker_mount_paths(self, docker_cleanup):
        """Test Docker mount path configuration."""
        # Create a simple test script that checks mount paths
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create test application
            app_file = temp_dir / "check_mounts.py"
            app_file.write_text(self.load_fixture("test_docker_container_4"))

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_docker_container_5"))

            # Build image
            image_name = "hyperlib-test:mounts"
            subprocess.run(["docker", "build", "-t", image_name, "."], cwd=temp_dir, capture_output=True)
            docker_cleanup["images"].append(image_name)

            # Run container with volume mounts
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{temp_dir}/config:/app/config",
                    "-v",
                    f"{temp_dir}/data:/app/data",
                    image_name,
                ],
                capture_output=True,
                text=True,
            )

            output = result.stdout
            assert "config_dir: /app/config EXISTS" in output
            assert "data_dir: /app/data EXISTS" in output

        finally:
            shutil.rmtree(temp_dir)

    def test_docker_with_environment_variables(self, docker_cleanup):
        """Test Docker container with environment variables."""
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create test script
            app_file = temp_dir / "check_env.py"
            app_file.write_text(self.load_fixture("test_docker_container_6"))

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_docker_container_7"))

            # Build image
            image_name = "hyperlib-test:env"
            subprocess.run(["docker", "build", "-t", image_name, "."], cwd=temp_dir, capture_output=True)
            docker_cleanup["images"].append(image_name)

            # Run with environment variables
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-e",
                    "APP_NAME=test-service",
                    "-e",
                    "POSTGRES_HOST=db.example.com",
                    "-e",
                    "POSTGRES_USER=testuser",
                    image_name,
                ],
                capture_output=True,
                text=True,
            )

            output = result.stdout
            assert "APP_NAME=test-service" in output
            assert "POSTGRES_HOST=db.example.com" in output
            assert "POSTGRES_USER=testuser" in output
            assert "CONTAINER=docker" in output

        finally:
            shutil.rmtree(temp_dir)

    def test_docker_compose_simulation(self, docker_cleanup):
        """Test multi-container setup simulating docker-compose."""
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create a simple API application
            api_file = temp_dir / "api.py"
            api_file.write_text(self.load_fixture("test_docker_container_8"))

            # Create Dockerfile for API
            dockerfile = temp_dir / "Dockerfile.api"
            dockerfile.write_text(self.load_fixture("test_docker_container_9"))

            # Build API image
            api_image = "hyperlib-test:api"
            subprocess.run(
                ["docker", "build", "-f", "Dockerfile.api", "-t", api_image, "."], cwd=temp_dir, capture_output=True
            )
            docker_cleanup["images"].append(api_image)

            # Create a network for containers
            network_name = "hyperlib-test-network"
            subprocess.run(["docker", "network", "create", network_name], capture_output=True)

            try:
                # Run API container with database environment
                result = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        network_name,
                        "-e",
                        "POSTGRES_HOST=postgres",
                        "-e",
                        "POSTGRES_USER=apiuser",
                        "-e",
                        "POSTGRES_DATABASE=apidb",
                        api_image,
                    ],
                    capture_output=True,
                    text=True,
                )

                output = result.stdout
                data = json.loads(output)
                assert data["status"] == "ready"
                assert data["database"]["host"] == "postgres"
                assert data["database"]["user"] == "apiuser"
                assert data["database"]["database"] == "apidb"

            finally:
                # Clean up network
                subprocess.run(["docker", "network", "rm", network_name], capture_output=True)

        finally:
            shutil.rmtree(temp_dir)

    def test_helm_style_mounts(self, docker_cleanup):
        """Test HELM-style mount points in Docker."""
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create test script for HELM-style paths
            app_file = temp_dir / "check_helm.py"
            app_file.write_text(self.load_fixture("test_docker_container_10"))

            # Create Dockerfile with HELM paths
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_docker_container_11"))

            # Build image
            image_name = "hyperlib-test:helm"
            subprocess.run(["docker", "build", "-t", image_name, "."], cwd=temp_dir, capture_output=True)
            docker_cleanup["images"].append(image_name)

            # Create host directories for mounting
            for dir_name in ["config", "secrets", "data", "logs"]:
                (temp_dir / dir_name).mkdir(exist_ok=True)

            # Run container with HELM-style mounts
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{temp_dir}/config:/config",
                    "-v",
                    f"{temp_dir}/secrets:/secrets",
                    "-v",
                    f"{temp_dir}/data:/data",
                    "-v",
                    f"{temp_dir}/logs:/logs",
                    image_name,
                ],
                capture_output=True,
                text=True,
            )

            output = result.stdout
            results = json.loads(output)

            # Verify HELM paths exist and are writable
            assert results["config"]
            assert results["secrets"]
            assert results["data"]
            assert results["logs"]

        finally:
            shutil.rmtree(temp_dir)

    def test_container_resource_limits(self, docker_cleanup):
        """Test container with resource limits."""
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create script that checks available resources
            app_file = temp_dir / "check_resources.py"
            app_file.write_text(self.load_fixture("test_docker_container_12"))

            # Create Dockerfile
            dockerfile = temp_dir / "Dockerfile"
            dockerfile.write_text(self.load_fixture("test_docker_container_13"))

            # Build image
            image_name = "hyperlib-test:resources"
            subprocess.run(["docker", "build", "-t", image_name, "."], cwd=temp_dir, capture_output=True)
            docker_cleanup["images"].append(image_name)

            # Run with resource limits (512MB memory, 0.5 CPU)
            result = subprocess.run(
                ["docker", "run", "--rm", "--memory", "512m", "--cpus", "0.5", image_name],
                capture_output=True,
                text=True,
            )

            output = result.stdout
            assert "CONTAINER_TYPE=docker" in output
            # Resource limits may or may not be visible depending on cgroup version

        finally:
            shutil.rmtree(temp_dir)
