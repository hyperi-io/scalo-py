# hs-pylib Testing Guide

## Test Requirements

### Prerequisites

**Required Tools:**
- Python 3.12+
- Docker (for container deployment tests)
- Minikube (for Kubernetes/Helm tests)
- Helm (for Helm deployment tests)
- kubectl (installed via Minikube)

**Minikube Installation:**
Follow the official installation guide: https://minikube.sigs.k8s.io/docs/start/?arch=%2Flinux%2Fx86-64%2Fstable%2Fbinary%20download

**Note:** No kubectl alias is required. Tests use `kubectl` directly (Minikube provides it).

### Test Infrastructure

**Minikube Behavior:**
- K8s/Helm tests automatically start Minikube if not running
- Tests deploy to Minikube cluster
- Tests clean up and stop Minikube after completion
- Each test run is isolated (fresh Minikube instance)

**Docker Behavior:**
- Tests build actual Docker images
- Tests run real containers
- Tests verify container behavior (logs, environment detection)
- Tests clean up containers and images after each run

## Running Tests

### All Tests

```bash
# Run complete test suite (unit + integration + e2e)
ci/.venv/bin/pytest tests/ -v
```

### Test Categories

```bash
# Unit tests only (fast, no external dependencies)
ci/.venv/bin/pytest tests/unit/ -v

# Integration tests (Docker + K8s/Helm)
ci/.venv/bin/pytest tests/integration/ -v

# E2E tests (application-level)
ci/.venv/bin/pytest tests/e2e/ -v
```

### Specific Test Suites

```bash
# Docker deployment tests
ci/.venv/bin/pytest tests/integration/test_docker_container.py -v
ci/.venv/bin/pytest tests/integration/test_container_deployment.py::TestDockerDeployment -v

# Kubernetes/Helm deployment tests
ci/.venv/bin/pytest tests/integration/test_container_deployment.py::TestHelmBasedDeployment -v
ci/.venv/bin/pytest tests/integration/test_container_deployment.py::TestHelmDeployment -v
```

### Single Test

```bash
# Run specific test
ci/.venv/bin/pytest tests/unit/test_application.py::TestApplication::test_api_application_creation -v
```

## Test Logging

All test runs log to `/logs` directory:

- **Active log**: `logs/<test-name>.log` (current run)
- **Previous logs**: `logs/<test-name>-YYYYMMDD-HHMMSS.log` (archived on each run)

Example:
```bash
# Current run
logs/test-full-run.log

# Previous runs (auto-archived)
logs/test-full-run-20251009-141500.log
logs/test-full-run-20251009-120000.log
```

## Test Fixtures

Test fixtures are stored in `tests/integration/fixtures/` using standardized naming:

- Format: `test_<suite>_<N>.txt`
- Example: `test_container_deployment_1.txt`, `test_docker_container_5.txt`
- Fixtures contain code snippets, Dockerfiles, Helm charts, K8s manifests

## Integration Test Details

### Docker Tests

**What they test:**
- Environment detection (Docker vs bare metal)
- Container configuration
- Application behavior in containers
- Logging and output

**How they work:**
1. Create temporary directory
2. Copy hs-pylib source + pyproject.toml
3. Generate Dockerfile from fixture
4. Build Docker image
5. Run container
6. Verify behavior (logs, HTTP endpoints, etc.)
7. Clean up container and image

### Helm/K8s Tests

**What they test:**
- Helm chart deployment
- Kubernetes pod creation
- Service exposure
- ConfigMap mounting
- Environment variable injection

**How they work:**
1. Start Minikube (if not running)
2. Create namespace
3. Generate Helm chart from fixtures
4. Create ConfigMaps with app code
5. Deploy via `helm install`
6. Wait for pods to be ready
7. Verify deployment (pod status, logs, services)
8. Clean up (helm uninstall, delete namespace)
9. Stop Minikube

## Troubleshooting

### Minikube Issues

```bash
# Check Minikube status
minikube status

# Start Minikube manually
minikube start

# Reset Minikube
minikube delete && minikube start

# View Minikube logs
minikube logs
```

### Docker Issues

```bash
# Check Docker daemon
docker info

# View test containers (including stopped)
docker ps -a --filter "name=hs-pylib-test"

# Clean up test artifacts
docker container prune
docker image prune
```

### Test Timeouts

Helm tests have timeouts (60s-90s). If tests timeout:

1. Check Minikube is running: `minikube status`
2. Check pod events: `kubectl get events -n <namespace>`
3. Check pod logs: `kubectl logs -n <namespace> <pod-name>`
4. Increase timeout in test if needed

## Test Coverage

- **Unit tests**: 153 passed (core functionality, no dependencies)
- **Integration tests**: Docker + K8s/Helm deployment
- **E2E tests**: Full application scenarios (API, daemon, oneshot)

Total: 180+ tests
