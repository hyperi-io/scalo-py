# API Applications

FastAPI applications with container-native patterns.

## Quick Start

```python
from hyperlib import Application

app = Application.api(name="my-api", version="1.0.0", profile="prod")

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id, "name": "John Doe"}

if __name__ == "__main__":
    app.run()  # Runs Typer CLI with 'serve' command
```

Container CMD: `python -m my_api serve --profile prod`

## Features

- **FastAPI integration**: Full FastAPI features
- **Auto-metrics**: Request/response tracking (Prometheus/OTEL)
- **Health endpoints**: `/health` and `/ready` for k8s probes
- **Graceful shutdown**: Handles SIGTERM correctly
- **Typer CLI**: Commands for serve, health-check, version, config
- **CORS support**: Optional middleware

## Profiles

- **dev**: Local development (debug mode, CORS enabled, hot reload)
- **docker**: CI/CD containers (metrics, health checks, JSON logs)
- **prod**: Kubernetes deployment (optimized, metrics, health checks)

## Lifecycle Hooks

```python
@app.on_startup
async def startup():
    logger.info("API starting...")
    await db.connect()

@app.on_shutdown
async def cleanup():
    logger.info("API stopping...")
    await db.disconnect()
```

## Routers

```python
from fastapi import APIRouter

# Define router
users_router = APIRouter()

@users_router.get("/users")
def list_users():
    return {"users": []}

@users_router.post("/users")
def create_user(user: UserSchema):
    return {"id": 1}

# Include in app
app.include_router(users_router, prefix="/api/v1", tags=["users"])
```

## Exception Handlers

```python
@app.exception_handler(ValueError)
async def handle_value_error(request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )
```

## Middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIDMiddleware)
```

## CORS

```python
app = Application.api(
    name="my-api",
    enable_cors=True,
    cors_origins=["https://example.com", "https://app.example.com"]
)
```

## Metrics Endpoint

Automatically available at `/metrics` (Prometheus format):

```python
# HTTP request metrics
http_requests_total{method="GET",path="/users",status="200"}
http_request_duration_seconds{method="GET",path="/users"}

# Process metrics (CPU, memory, etc.)
process_cpu_seconds_total
process_resident_memory_bytes
```

## Health Endpoints

Auto-configured in docker/prod profiles:

- **GET /health**: Liveness probe (always 200 if running)
- **GET /ready**: Readiness probe (checks dependencies, 503 if any fail)

### Custom Dependency Checks

Register custom health checks for databases, caches, external services:

```python
@app.health_check
def check_database():
    try:
        db.ping()
        return True
    except Exception:
        return False

@app.health_check
def check_redis():
    try:
        redis.ping()
        return True
    except Exception:
        return False
```

The `/ready` endpoint will return 503 if any check returns `False` or raises an exception.

## Production Example

```python
from hyperlib import Application, logger
from fastapi import Depends, HTTPException
from pydantic import BaseModel

app = Application.api(
    name="user-service",
    version="1.0.0",
    profile="prod",
    enable_cors=True,
    cors_origins=["https://app.example.com"]
)

class User(BaseModel):
    id: int
    name: str
    email: str

@app.on_startup
async def startup():
    logger.info("Connecting to database...")
    await db.connect()

@app.get("/api/v1/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/api/v1/users", response_model=User, status_code=201)
async def create_user(user: User):
    created = await db.create_user(user)
    app.track_counter("users_created")
    return created

@app.on_shutdown
async def cleanup():
    logger.info("Shutting down...")
    await db.disconnect()

if __name__ == "__main__":
    app.run()
```

## Container Deployment

Dockerfile:
```dockerfile
CMD ["python", "-m", "user_service", "serve", "--profile", "prod"]
```

Kubernetes manifest:
```yaml
spec:
  containers:
  - name: api
    ports:
    - containerPort: 8000
    livenessProbe:
      httpGet:
        path: /health
        port: 8000
    readinessProbe:
      httpGet:
        path: /ready
        port: 8000
```

## Configuration

```python
app = Application.api(
    name="my-api",
    version="1.0.0",
    port=8000,
    host="0.0.0.0",
    profile="prod",
    profile_overrides={
        "uvicorn": {
            "workers": 4,
            "log_level": "info"
        }
    }
)
```

## Testing

```python
from fastapi.testclient import TestClient

client = TestClient(app.fastapi)

def test_get_user():
    response = client.get("/api/v1/users/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1
```

## Access Underlying FastAPI

```python
# Direct FastAPI access when needed
fastapi_app = app.fastapi

# Add custom routes directly
@fastapi_app.get("/custom")
def custom_route():
    return {"custom": True}
```
