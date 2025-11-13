"""
Example Daemon Application

Background worker with container-native patterns:
- Health checks (/health, /ready)
- Prometheus metrics
- Profile-based configuration
- Graceful shutdown
"""

import time
from hs_lib import Application, logger

# Create application with prod profile (container-native patterns)
app = Application.daemon(
    name="example-daemon",
    version="1.0.0",
    profile="prod",  # Enable health checks, metrics, JSON logs
)


# Custom health checks for dependencies
@app.health_check
def check_database():
    """Check database connection (simulated)."""
    # In a real app: db.ping()
    logger.debug("Database health check: OK")
    return True


@app.health_check
def check_queue():
    """Check queue connection (simulated)."""
    # In a real app: queue.ping()
    logger.debug("Queue health check: OK")
    return True


# Background tasks
@app.task(interval=60)
def process_queue():
    """Process items from queue every 60 seconds."""
    logger.info("Processing queue...")

    # Simulated queue processing
    items_processed = 0
    for i in range(10):
        logger.debug(f"Processing item {i+1}/10")
        time.sleep(0.1)  # Simulate work
        items_processed += 1

    logger.info(f"Queue processing complete: {items_processed} items")
    return items_processed


@app.task(interval=300)
def cleanup_old_data():
    """Clean up old data every 5 minutes."""
    logger.info("Running cleanup task...")

    # Simulated cleanup
    records_deleted = 42
    logger.info(f"Cleanup complete: {records_deleted} records deleted")
    return records_deleted


@app.task(interval=3600)
def generate_report():
    """Generate hourly report."""
    logger.info("Generating hourly report...")

    # Simulated report generation
    time.sleep(0.5)

    logger.info("Report generated successfully")
    return True


# Application startup
if __name__ == "__main__":
    # Run with Typer CLI (supports start, stop, health-check, version, config commands)
    app.run()
