# Hyperlib Test Suite

Test organization for hyperlib following standard testing patterns.

## Directory Structure

```
tests/
├── conftest.py           # Shared pytest fixtures and configuration
├── unit/                 # Unit tests (fast, isolated)
│   ├── test_application.py  # Application factory and decorator tests
│   └── test_import.py       # Module import tests
├── integration/          # Integration tests (component interaction)
│   └── (future tests)
└── e2e/                  # End-to-end tests (full application behavior)
    ├── test_application.py  # Application runtime and decorator behavior
    └── test_deploy.py       # Deployment workflow tests
```

## Test Types

### Unit Tests (`tests/unit/`)

Fast, isolated tests that verify individual components without external dependencies.

- **Scope**: Single functions, classes, or modules
- **Speed**: < 1s per test
- **Dependencies**: None (mocked if needed)
- **Example**: Testing Application factory methods return correct types

**Run unit tests only:**
```bash
pytest tests/unit/ -v
```

### Integration Tests (`tests/integration/`)

Tests that verify components work together correctly.

- **Scope**: Multiple components interacting
- **Speed**: 1-5s per test
- **Dependencies**: Real services (optional, Docker)
- **Example**: Testing API routes with database

**Run integration tests only:**
```bash
pytest tests/integration/ -v
```

### E2E Tests (`tests/e2e/`)

Full application behavior tests using real frameworks (FastAPI, Click, etc.).

- **Scope**: Complete user workflows
- **Speed**: 1-10s per test
- **Dependencies**: Full stack (FastAPI TestClient, CliRunner, etc.)
- **Example**: Testing API endpoints respond correctly via HTTP

**Run e2e tests only:**
```bash
pytest tests/e2e/ -v
```

**Skip slow deployment tests:**
```bash
pytest tests/e2e/ -v -k "not deploy"
```

## Running Tests

**All tests:**
```bash
pytest tests/ -v
```

**Fast tests only (unit):**
```bash
pytest tests/unit/ -v
```

**With coverage:**
```bash
pytest tests/ --cov=hyperlib --cov-report=html
```

**Specific test file:**
```bash
pytest tests/unit/test_application.py -v
```

**Specific test function:**
```bash
pytest tests/unit/test_application.py::TestApplicationFactory::test_api_factory -v
```

## Test Statistics

- **Unit tests**: 25 tests (22 application, 3 import)
- **Integration tests**: 0 tests (future)
- **E2E tests**: 18 tests (14 application, 4 deployment - skipped by default)
- **Total**: 43 tests (39 passing, 4 skipped)

## Writing Tests

### Unit Test Example

```python
# tests/unit/test_mymodule.py
from hyperlib import Application

def test_api_factory():
    """Test API factory creates APIApplication."""
    app = Application.api(name="test-api")
    assert app.name == "test-api"
    assert app.port == 8000
```

### E2E Test Example

```python
# tests/e2e/test_myfeature.py
import pytest
from hyperlib import Application
from fastapi.testclient import TestClient

@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
def test_api_route_works():
    """Test API route responds correctly."""
    app = Application.api(name="test-api")

    @app.route("/test")
    def test_endpoint():
        return {"message": "hello"}

    client = TestClient(app.fastapi)
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json()["message"] == "hello"
```

## CI Integration

Tests run automatically via CI scripts:

```bash
./scripts/ci check  # Runs all tests
```

Individual test commands used by CI:
- `pytest tests/unit/ -v` - Fast unit tests
- `pytest tests/e2e/ -v -k "not deploy"` - E2E without deployment
- `pytest tests/ --cov=hyperlib` - Full suite with coverage
