# CLI Migration Analysis: dfe-cli-core → hyperlib

**Date:** 2025-10-07
**Source Project:** `/projects/dfe-cli-core`
**Target:** Hyperlib CLI application support

## Executive Summary

Analysis of dfe-cli-core reveals several critical features needed for future migration. The project is a complex Click-based CLI with 24+ commands, custom logging, multi-environment configuration, and async job scheduling.

## Current dfe-cli-core Architecture

### Core Technologies
- **CLI Framework:** Click 8.1.0
- **Logging:** colorlog 6.8.2 (custom DFELog wrapper)
- **Config:** YAML-based with environment variable overrides
- **Async:** APScheduler 3.10.4, aiocron, asyncio
- **Data:** ClickHouse, Kafka, Elasticsearch/OpenSearch
- **API:** FastAPI 0.114.2 + Uvicorn (embedded API server)
- **Monitoring:** Prometheus FastAPI Instrumentator

### Project Structure
```
src/dfecli/
├── main.py                          # CLI entry point (24+ commands)
├── dfe_logger/                      # Custom logging wrapper
│   └── dfe_logger.py               # DFELog class
├── dfe_config/                      # Configuration management
│   └── config_loader.py            # DFEConfigLoader
├── dfe_async_hunts/                # Async job scheduling
│   ├── hunts/                      # Hunt controller & scheduler
│   ├── jobs/                       # Job definitions
│   └── runner/                     # Cron runner
├── dfe_pipelinebuilder/            # Pipeline generation
├── dfe_schemabuilder/              # Schema generation
├── dfe_sigma/                      # Sigma rule conversion
├── dfe_opensearch/                 # OpenSearch operations
├── dfe_kafka_replay/               # Kafka replay functionality
├── dfe_clickhouse/                 # ClickHouse operations
└── utils/                          # Utilities
```

## Features Missing from Hyperlib (Critical for Migration)

### 1. **CLI Application Factory Pattern** ❌

**Current dfe-cli-core:**
```python
@click.group()
@click.version_option(version=VERSION, prog_name="dfecli")
def cli():
    """DFE CLI tool."""
    click.echo(f"Welcome to dfecli! (Version: {VERSION})")

@cli.command()
@click.option("--target", help="Target environment")
def init_target(target: str):
    """Initialize configuration."""
    pass
```

**What Hyperlib Needs:**
- Application factory for CLI apps with Click integration
- Version management (from package metadata)
- Command group management
- Option/argument validation helpers

**Recommended API:**
```python
from hyperlib import Application

# Create CLI application
app = Application.cli(
    name="my-cli",
    version="1.0.0",  # Auto from package metadata
    description="My CLI tool"
)

# Register commands
@app.command()
@app.option("--target", help="Target environment")
def init(target: str):
    """Initialize configuration."""
    pass
```

### 2. **Multi-Environment Configuration** ⚠️ (Partially exists)

**Current dfe-cli-core:**
- YAML-based targets file (`~/.dfe/dfe_targets.yaml`)
- Environment variable overrides (`DFE_CH_HOST`, `DFE_CH_PORT`, etc.)
- Default target selection
- Per-environment credentials

**Example config:**
```yaml
default_target: production

targets:
  production:
    ch_host: prod.clickhouse.example.com
    ch_port: 9000
    ch_username: prod_user
    ch_password: ${DFE_CH_PASSWORD}  # From env var

  development:
    ch_host: localhost
    ch_port: 9000
    ch_username: dev_user
```

**What Hyperlib Has:**
- ✅ Dynaconf for config management
- ✅ Environment variable support
- ✅ `.env` file loading

**What's Missing:**
- ❌ Multi-environment/target management
- ❌ Per-environment config sections
- ❌ Target selection via CLI
- ❌ Config file in user home directory (`~/.app/config.yaml`)

**Recommended Enhancement:**
```python
from hyperlib.config import get_target_config

# Load target-specific config
config = get_target_config("production")  # From ~/.my-app/targets.yaml
# Or override with env: MY_APP_TARGET=staging
```

### 3. **Custom Logging with colorlog** ⚠️ (Partially exists)

**Current dfe-cli-core DFELog:**
- Colored console output (colorlog)
- Plain text file logging
- Rotating file handler (10MB, 5 backups)
- Timestamp-based log filenames
- Per-command log files

**What Hyperlib Has:**
- ✅ Loguru with Solarized colors
- ✅ Console + file logging (tee)
- ✅ Emoji support (CHARS-POLICY compliant)
- ✅ LOG_LEVEL environment variable

**What's Missing:**
- ❌ Rotating file handler (currently 10MB rotation)
- ❌ Per-command log files
- ❌ Timestamp-based log filenames
- ❌ Custom log file prefixes/suffixes

**Status:** Hyperlib's logger is MORE advanced (loguru > colorlog), but missing rotating file handler.

**Recommended Addition:**
```python
from hyperlib.logger import setup

setup(
    log_file="/var/log/my-app/app.log",
    rotation="10 MB",      # Already supported!
    retention="5 days",    # Already supported!
    log_prefix="my-app",   # NEW: for dynamic filenames
    log_suffix="-%Y-%m-%d" # NEW: timestamp suffix
)
```

### 4. **Health Check Command Pattern** ✅ (Easy to add)

**Current dfe-cli-core:**
```python
@cli.command()
def is_hunt_scheduler_healthy():
    """Health check for application."""
    try:
        # Check application state
        click.echo("Application is healthy.")
        sys.exit(0)
    except Exception as e:
        click.echo(f"Health check failed: {e}")
        sys.exit(1)
```

**Hyperlib Can Support:** Standard pattern, no special framework needed.

### 5. **Async Job Scheduling** ❌ (Not in Hyperlib)

**Current dfe-cli-core:**
- APScheduler for cron-like scheduling
- Async hunts (background jobs)
- Checkpoint management
- Job validation

**Example:**
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=run_hunt,
    trigger="cron",
    hour=2,
    minute=0
)
scheduler.start()
```

**What Hyperlib Needs:**
- ❌ Background job scheduler
- ❌ Cron-like job definitions
- ❌ Job checkpoint/state management
- ❌ Async job execution

**Recommendation:** Out of scope for hyperlib core. Use APScheduler directly in user code.

### 6. **Embedded FastAPI Server** ❌ (Conflicts with CLI paradigm)

**Current dfe-cli-core:**
- FastAPI server embedded in CLI
- Prometheus metrics endpoint
- Health check endpoints

**Issue:** This is mixing CLI and API paradigms.

**Recommendation:**
- Keep CLI and API separate (hyperlib already has this)
- Use `Application.api()` for API servers
- Use `Application.cli()` for CLI tools
- Don't embed API in CLI (architectural smell)

### 7. **Environment Variable Override Callback** ✅ (Easy pattern)

**Current dfe-cli-core:**
```python
def apply_env_override(ctx, param, value):
    """Override CLI option with environment variable."""
    env_value = os.getenv(param.name.upper())
    return env_value if env_value else value

@cli.command()
@click.option("--target", callback=apply_env_override)
def command(target):
    pass
```

**Hyperlib Can Support:** Standard Click pattern, document as best practice.

### 8. **Config File in User Home Directory** ❌

**Current dfe-cli-core:**
- Config directory: `~/.dfe/`
- Auto-create on first run
- Targets file: `~/.dfe/dfe_targets.yaml`

**What Hyperlib Has:**
- ✅ RuntimePaths for daemon/CLI apps
- ✅ User-specific paths: `~/.appname/config/`

**What's Missing:**
- ❌ Auto-create config directory
- ❌ Template/default config generation
- ❌ Config init command

**Recommended Addition:**
```python
from hyperlib.runtime import get_runtime_paths, init_config

paths = get_runtime_paths("my-app")
init_config(
    paths.config_dir,
    template="default-config.yaml",
    interactive=True  # Prompt user for values
)
```

## Migration Complexity Assessment

### Easy to Migrate (Hyperlib ready)
- ✅ Basic CLI structure (Click)
- ✅ Logging (hyperlib logger is better)
- ✅ Config management (Dynaconf)
- ✅ Runtime paths

### Medium Effort (Need enhancements)
- ⚠️ CLI application factory
- ⚠️ Multi-environment configuration
- ⚠️ Rotating log files (already supported, needs docs)
- ⚠️ Config initialization helper

### High Effort (Out of scope / Complex)
- ❌ Async job scheduling (use APScheduler directly)
- ❌ Domain-specific modules (ClickHouse, Kafka, Sigma, etc.)

## Recommended Hyperlib Additions

### Priority 1: CLI Application Factory

**Add to hyperlib.application.cli:**
```python
class CLIApplication:
    """Click-based CLI application with hyperlib integration."""

    def __init__(self, name: str, version: str = None, description: str = None):
        self.name = name
        self.version = version or self._get_package_version()
        self.description = description
        self.cli_group = click.Group()

    def command(self, *args, **kwargs):
        """Decorator to register a command."""
        return self.cli_group.command(*args, **kwargs)

    def option(self, *args, **kwargs):
        """Create a Click option with env var override support."""
        # Add callback for env var override
        return click.option(*args, **kwargs)

    def run(self):
        """Run the CLI application."""
        self.cli_group()
```

### Priority 2: Multi-Environment Config Support

**Add to hyperlib.config:**
```python
def get_target_config(
    target: str = None,
    targets_file: Path = None
) -> dict:
    """Load target-specific configuration.

    Args:
        target: Target environment name (e.g., "production")
        targets_file: Path to targets YAML file
                     Default: ~/.{APP_NAME}/targets.yaml

    Returns:
        Configuration dict for specified target
    """
    # Implementation using dynaconf
    pass

def init_config_directory(
    app_name: str,
    template: str = None,
    interactive: bool = False
):
    """Initialize config directory in user home.

    Creates ~/.{app_name}/ and default config files.
    """
    pass
```

### Priority 3: Enhanced Logging Options

**Already exists in hyperlib! Just needs documentation:**
- ✅ Rotation: `rotation="10 MB"`
- ✅ Retention: `retention="7 days"`

**Add:**
- Log file prefixes: `log_prefix="my-app"`
- Timestamp suffixes: `log_suffix="-%Y-%m-%d"`

## Migration Checklist for dfe-cli-core

When ready to migrate:

- [ ] Update hyperlib with CLI application factory
- [ ] Add multi-environment config support
- [ ] Document rotating log handler usage
- [ ] Create config initialization helper
- [ ] Migrate Click commands one-by-one
- [ ] Replace DFELog with hyperlib.logger
- [ ] Replace DFEConfigLoader with hyperlib.config
- [ ] Keep domain-specific modules (ClickHouse, Kafka, etc.) as-is
- [ ] Keep APScheduler for async jobs (not part of hyperlib)
- [ ] Test all 24+ CLI commands
- [ ] Update documentation

## Conclusion

**Migration Feasibility:** Medium complexity

**Key Blockers:**
1. Need CLI application factory in hyperlib
2. Need multi-environment configuration support
3. Need config initialization helpers

**Timeline Estimate:**
- Hyperlib enhancements: 2-3 days
- Migration of dfe-cli-core: 5-7 days
- Testing and validation: 2-3 days
- **Total: ~2 weeks**

**Recommendation:** Add CLI application factory and multi-environment config to hyperlib first, then migrate dfe-cli-core as validation project (similar to how hyperlib itself validates forge-python template).
