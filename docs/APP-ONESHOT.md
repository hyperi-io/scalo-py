# Oneshot Applications

Single-run jobs for batch processing and data pipelines.

## Quick Start

```python
from hyperi_pylib import Application, logger

app = Application.oneshot(name="data-import", version="1.0.0")

@app.task
def import_data():
    logger.info("Starting data import...")
    records = fetch_data_from_source()
    load_data_to_db(records)
    logger.success(f"Imported {len(records)} records")

if __name__ == "__main__":
    app.run()  # Runs task once and exits
```

Container CMD: `python -m data_import run --profile prod`

## Features

- **Single execution**: Run once and exit (perfect for k8s Jobs/CronJobs)
- **Graceful shutdown**: Handles SIGTERM during execution
- **Exit codes**: 0 for success, 1 for failure
- **Typer CLI**: Commands for run, version, config
- **Optional metrics**: Track job execution

## Profiles

- **dev**: Local development (debug logging)
- **docker**: CI/CD containers (JSON logs, metrics)
- **prod**: Kubernetes jobs (optimized, metrics, JSON logs)

## Task Decorator

```python
@app.task
def my_job():
    # Synchronous task
    process_data()

@app.task
async def async_job():
    # Async task
    await process_data_async()
```

## Error Handling

```python
@app.task
def risky_job():
    try:
        process_data()
    except DataError as e:
        logger.error(f"Data processing failed: {e}")
        raise  # Exit code 1

    logger.success("Job completed successfully")
    # Exit code 0
```

## Lifecycle Hooks

```python
@app.on_startup
def setup():
    logger.info("Setting up resources...")
    db.connect()

@app.task
def process():
    records = db.get_records()
    transform_records(records)

@app.on_shutdown
def cleanup():
    logger.info("Cleaning up...")
    db.disconnect()
```

## Production Example: ETL Job

```python
from hyperi_pylib import Application, logger
from datetime import datetime

app = Application.oneshot(
    name="daily-etl",
    version="1.0.0",
    profile="prod"
)

@app.on_startup
def connect():
    logger.info("Connecting to database...")
    db.connect()

@app.task
def run_etl():
    start = datetime.now()
    logger.info("Starting ETL job...")

    # Extract
    logger.info("Extracting data from source...")
    raw_data = extract_from_source()
    logger.info(f"Extracted {len(raw_data)} records")

    # Transform
    logger.info("Transforming data...")
    transformed = transform_data(raw_data)
    logger.info(f"Transformed {len(transformed)} records")

    # Load
    logger.info("Loading to warehouse...")
    load_to_warehouse(transformed)

    duration = (datetime.now() - start).total_seconds()
    logger.success(f"ETL complete in {duration:.2f}s")

    # Optional: Track metrics
    if hasattr(app, 'track_counter'):
        app.track_counter("etl_records_processed", len(transformed))
        app.track_histogram("etl_duration_seconds", duration)

@app.on_shutdown
def disconnect():
    logger.info("Disconnecting...")
    db.disconnect()

if __name__ == "__main__":
    app.run()
```

## Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-etl
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: etl
            image: my-etl:1.0.0
            command: ["python", "-m", "daily_etl", "run", "--profile", "prod"]
          restartPolicy: OnFailure
      backoffLimit: 3
```

## Kubernetes Job (One-time)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: data-migration
spec:
  template:
    spec:
      containers:
      - name: migration
        image: my-migration:1.0.0
        command: ["python", "-m", "migrate", "run", "--profile", "prod"]
      restartPolicy: Never
  backoffLimit: 2
```

## CLI Commands

```bash
# Run job
python -m my_job run --profile prod

# Show version
python -m my_job version

# Show config
python -m my_job config
```

## Exit Codes

- **0**: Success (task completed without exceptions)
- **1**: Failure (task raised exception)
- **130**: Interrupted (SIGINT/Ctrl+C)
- **143**: Terminated (SIGTERM from k8s)

## Optional Metrics

Enable metrics in prod:

```python
app = Application.oneshot(
    name="my-job",
    profile_overrides={"metrics": True}
)

@app.task
def job():
    app.track_counter("job_started")
    process_data()
    app.track_counter("job_completed")
```

## Testing

```python
def test_job():
    app = Application.oneshot(name="test-job")

    executed = []

    @app.task
    def test_task():
        executed.append(True)

    app._execute_task()
    assert len(executed) == 1
```

## When to Use Oneshot

Use oneshot applications for:

- **ETL jobs**: Extract, transform, load data
- **Data migrations**: One-time or periodic migrations
- **Report generation**: Daily/weekly reports
- **Cleanup jobs**: Delete old data, archive logs
- **Batch processing**: Process queued items
- **Database maintenance**: VACUUM, ANALYZE, backups

Don't use for:
- Long-running services (use Daemon instead)
- Web APIs (use API instead)
- Interactive tools (use CLI instead)
