# Test Fixtures

This directory contains code snippets, Dockerfiles, and YAML manifests used by the integration tests.

## Naming Convention

Fixtures follow the pattern: `{test_file_base}_{number}.txt`

For example:

- `test_container_deployment_code_1.txt` - First Python code snippet for container deployment tests
- `test_container_deployment_dockerfile_1.txt` - First Dockerfile for container deployment tests
- `test_container_deployment_12.txt` - Helm Chart.yaml template

## Usage

Tests load fixtures using the `ContainerTestBase.load_fixture()` method:

```python
# In test
app_code = self.load_fixture("test_container_deployment_code_1")
dockerfile_content = self.load_fixture("test_container_deployment_dockerfile_1")
```

## File Index

### test_container_deployment fixtures

**Python Code:**

- `test_container_deployment_code_1.txt` - API application with database config
- `test_container_deployment_code_2.txt` - API with Prometheus metrics
- `test_container_deployment_code_3.txt` - Daemon application with scheduled tasks
- `test_container_deployment_code_5.txt` - Database connection test app
- `test_container_deployment_7.txt` - Kubernetes environment detection app
- `test_container_deployment_9.txt` - Prometheus metrics HTTP server

**Dockerfiles:**

- `test_container_deployment_dockerfile_1.txt` - API Dockerfile with uv
- `test_container_deployment_dockerfile_2.txt` - Metrics API Dockerfile
- `test_container_deployment_4.txt` - Daemon Dockerfile
- `test_container_deployment_6.txt` - Database app Dockerfile

**Kubernetes Manifests:**

- `test_container_deployment_8.txt` - Pod manifest template
- `test_container_deployment_10.txt` - Deployment + Service with Prometheus annotations
- `test_container_deployment_11.txt` - Deployment + Service for API

**Helm Charts (Original TestHelmDeployment):**

- `test_container_deployment_12.txt` - Chart.yaml
- `test_container_deployment_13.txt` - values.yaml
- `test_container_deployment_14.txt` - Deployment template
- `test_container_deployment_15.txt` - Service template

**Helm Charts (TestHelmBasedDeployment - converted from kubectl):**

*Pod Deployment:*

- `test_container_deployment_helm_pod_chart.txt` - Chart.yaml for Pod test
- `test_container_deployment_helm_pod_values.txt` - values.yaml for Pod test
- `test_container_deployment_helm_pod_template.txt` - Pod template

*Metrics Deployment:*

- `test_container_deployment_helm_metrics_chart.txt` - Chart.yaml for Prometheus metrics test
- `test_container_deployment_helm_metrics_values.txt` - values.yaml for metrics test
- `test_container_deployment_helm_metrics_deployment.txt` - Deployment template with Prometheus annotations
- `test_container_deployment_helm_metrics_service.txt` - Service template for metrics

*API Deployment:*

- `test_container_deployment_helm_api_chart.txt` - Chart.yaml for API test
- `test_container_deployment_helm_api_values.txt` - values.yaml for API test
- `test_container_deployment_helm_api_deployment.txt` - Deployment template for API
- `test_container_deployment_helm_api_service.txt` - Service template for API

### test_docker_container fixtures

**Python Code:**

- `test_docker_container_1.txt` - Environment detection test app
- `test_docker_container_4.txt` - Mount paths detection script
- `test_docker_container_6.txt` - Environment variables check script
- `test_docker_container_8.txt` - Docker Compose API simulation
- `test_docker_container_10.txt` - HELM-style mount paths check
- `test_docker_container_12.txt` - Container resource limits check

**Dockerfiles:**

- `test_docker_container_2.txt` - Dockerfile with build context
- `test_docker_container_3.txt` - Simple Dockerfile without context
- `test_docker_container_5.txt` - Dockerfile for mount paths test
- `test_docker_container_7.txt` - Dockerfile for env vars test
- `test_docker_container_9.txt` - API Dockerfile for compose test
- `test_docker_container_11.txt` - HELM-style Dockerfile
- `test_docker_container_13.txt` - Resource limits Dockerfile

## Benefits

1. **Cleaner Test Code**: Test files focus on logic, not large string literals
2. **Easier Maintenance**: Update code/configs without touching test logic
3. **Better Syntax Highlighting**: Editors recognize `.txt` files and can apply appropriate highlighting
4. **Reusability**: Fixtures can be shared across multiple tests
5. **Version Control**: Easier to see diffs when fixtures change
