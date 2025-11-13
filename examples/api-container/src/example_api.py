"""
Example API Application

Simple FastAPI REST API with container-native patterns:
- Health checks (/health, /ready)
- Prometheus metrics
- Profile-based configuration
- Graceful shutdown
"""

from hs_lib import Application, logger

# Create application with prod profile (container-native patterns)
app = Application.api(
    name="example-api",
    version="1.0.0",
    profile="prod",  # Enable health checks, metrics, JSON logs
    enable_cors=True,
    cors_origins=["*"],  # Allow all origins for demo
)


# Custom health checks for dependencies
@app.health_check
def check_database():
    """Check database connection (simulated)."""
    # In a real app: db.ping()
    logger.debug("Database health check: OK")
    return True


@app.health_check
def check_redis():
    """Check Redis connection (simulated)."""
    # In a real app: redis.ping()
    logger.debug("Redis health check: OK")
    return True


# API Routes
@app.route("/")
def root():
    """Root endpoint."""
    return {
        "service": "example-api",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "users": "/api/users",
            "health": "/health (port 8080)",
            "metrics": "/metrics (port 9090)",
        },
    }


@app.route("/api/users")
def list_users():
    """List all users."""
    logger.info("Listing users")
    return {
        "users": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ]
    }


@app.route("/api/users", methods=["POST"])
async def create_user(name: str):
    """Create a new user."""
    logger.info(f"Creating user: {name}")
    return {"id": 4, "name": name, "created": True}


# Application startup
if __name__ == "__main__":
    # Run with Typer CLI (supports serve, version, config commands)
    app.run()
