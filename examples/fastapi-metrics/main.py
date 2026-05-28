# Project:   hyperi-pylib
# File:      examples/fastapi-metrics/main.py
# Purpose:   Demonstrate hyperi-pylib Prometheus metrics with FastAPI
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""
FastAPI Metrics Example.

Demonstrates hyperi-pylib's Prometheus metrics integration with FastAPI.
Run with: uv run python main.py

Then visit:
- http://localhost:8000/ - API root
- http://localhost:8000/api/users - Sample endpoint
- http://localhost:8000/health - Health check
- http://localhost:8000/metrics - Prometheus metrics
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from hyperi_pylib.logger import info, success
from hyperi_pylib.metrics import create_metrics

# Configuration
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))
METRICS_NAMESPACE = os.environ.get("METRICS_NAMESPACE", "myapp")

# Create metrics manager
metrics = create_metrics(namespace=METRICS_NAMESPACE)

# Define application metrics
http_requests = metrics.counter(
    "http_requests",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_duration = metrics.histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

active_requests = metrics.gauge(
    "active_requests",
    "Number of requests currently being processed",
)

# Sample business metrics
users_total = metrics.gauge("users_total", "Total number of users")
users_total.set(150)  # Simulated value


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    info("Application starting", host=API_HOST, port=API_PORT)
    yield
    info("Application shutting down")


# Create FastAPI application
app = FastAPI(
    title="FastAPI Metrics Example",
    description="Demonstrates hyperi-pylib Prometheus metrics",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to track request metrics."""
    # Skip metrics endpoint to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.perf_counter()
    active_requests.inc()

    try:
        response = await call_next(request)

        # Record metrics
        duration = time.perf_counter() - start_time
        http_requests.labels(
            method=request.method,
            endpoint=request.url.path,
            status=str(response.status_code),
        ).inc()
        http_duration.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(duration)

        return response
    finally:
        active_requests.dec()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "fastapi-metrics-example",
        "version": "1.0.0",
        "endpoints": {
            "users": "/api/users",
            "health": "/health",
            "metrics": "/metrics",
        },
    }


@app.get("/api/users")
async def list_users():
    """List users endpoint."""
    info("Listing users")
    # Simulated users
    return {
        "users": [
            {"id": 1, "name": "Alice", "role": "admin"},
            {"id": 2, "name": "Bob", "role": "user"},
            {"id": 3, "name": "Charlie", "role": "user"},
        ],
        "total": 3,
    }


@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    """Get a specific user."""
    info("Getting user", user_id=user_id)
    # Simulated user lookup
    users = {
        1: {"id": 1, "name": "Alice", "role": "admin"},
        2: {"id": 2, "name": "Bob", "role": "user"},
        3: {"id": 3, "name": "Charlie", "role": "user"},
    }
    if user_id in users:
        return users[user_id]
    return Response(status_code=404, content="User not found")


@app.get("/health")
@app.get("/health/live")
async def health_live():
    """Liveness probe - is the process alive?"""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe - can we handle traffic?"""
    # In a real app, check database connections, etc.
    return {"status": "ready"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return metrics.export()


def main() -> None:
    """Run the FastAPI server."""
    import uvicorn

    success("Starting FastAPI server", host=API_HOST, port=API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
