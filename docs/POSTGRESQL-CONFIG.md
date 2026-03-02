# PostgreSQL Configuration Source

Implementation specification for PostgreSQL as a configuration source in the HyperI config cascade. This document covers both hyperi-pylib (Python) and hs-rustlib (Rust) implementations.

## Overview

**Status: Built-For, Not Built-With.** The PostgreSQL config layer is implemented
and tested but is **not currently active**. The YAML file-based approach already
provides centralised configuration management (gitops-optimised, stored on S3
for AWS deployments, used across all services). The PostgreSQL option exists in
case we want to pursue a more complex PG-over-YAML path in the future — the ROI
for that is not there yet. The cascade is designed so PG can be enabled without
any code changes, just set `HYPERI_CONFIG_DSN`.

PostgreSQL serves as a **centralised configuration store** that **OVERRIDES file-based config**. This allows multi-pod deployments to share configuration from a single source of truth.

**Key principle:** Configuration flows ONE WAY only: PostgreSQL → Application. Never Application → PostgreSQL.

## Updated Cascade Priority

PostgreSQL has **HIGH priority** (layer 4), overriding all file-based config:

```
Priority  Layer              Source                  Notes
--------  -----              ------                  -----
1         CLI args           --host=X                Runtime override
2         ENV vars           MYAPP_DATABASE_HOST     Deployment/secrets
3         .env file          .env                    Local dev secrets
4         PostgreSQL         config_values table     OVERRIDES files ← NEW PRIORITY
5         settings.{env}     settings.production.yaml Environment-specific
6         settings.yaml      settings.yaml           Project base
7         defaults.yaml      defaults.yaml           Safe defaults
8         Hard-coded         code fallback           Last resort
```

**Rationale:** The database is the source of truth for shared configuration. Local files are defaults that PostgreSQL overrides.

---

## Database Schema

### Main Config Table (Key-Value with Dot Notation)

```sql
CREATE TABLE IF NOT EXISTS config_values (
    namespace   TEXT NOT NULL DEFAULT 'default',
    key         TEXT NOT NULL,
    value       JSONB NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by  TEXT,
    PRIMARY KEY (namespace, key)
);

-- Index for namespace queries
CREATE INDEX idx_config_values_namespace
    ON config_values (namespace);

-- Index for prefix queries (e.g., all kafka.* keys)
CREATE INDEX idx_config_values_key_prefix
    ON config_values USING btree (key text_pattern_ops);
```

### YAML to Schema Mapping

YAML nested structure maps to dot-notation keys:

```yaml
# YAML config
database:
  host: localhost
  port: 5432
  credentials:
    user: myuser
    password: secret
kafka:
  brokers:
    - broker1:9092
    - broker2:9092
```

Becomes these PostgreSQL rows:

| namespace | key | value (JSONB) |
|-----------|-----|---------------|
| my-app | database.host | "localhost" |
| my-app | database.port | 5432 |
| my-app | database.credentials.user | "myuser" |
| my-app | database.credentials.password | "secret" |
| my-app | kafka.brokers | ["broker1:9092", "broker2:9092"] |

**Conversion rules:**

- Nested dicts → Dot-notation keys (`database.host`)
- Arrays → Stored as JSONB arrays in a single row
- Scalars → Stored as JSONB primitives (string, number, boolean, null)

### Optional Audit Trail Table

Created with `ensure_table(with_audit=True)`:

```sql
CREATE TABLE IF NOT EXISTS config_values_history (
    id          BIGSERIAL PRIMARY KEY,
    namespace   TEXT NOT NULL,
    key         TEXT NOT NULL,
    old_value   JSONB,
    new_value   JSONB,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by  TEXT
);

-- Trigger function
CREATE OR REPLACE FUNCTION config_values_audit_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO config_values_history (namespace, key, old_value, new_value, changed_by)
        VALUES (OLD.namespace, OLD.key, OLD.value, NEW.value, NEW.updated_by);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO config_values_history (namespace, key, old_value, new_value, changed_by)
        VALUES (OLD.namespace, OLD.key, OLD.value, NULL, current_user);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER config_values_audit
    AFTER UPDATE OR DELETE ON config_values
    FOR EACH ROW EXECUTE FUNCTION config_values_audit_trigger();
```

---

## Environment Variables

### Connection Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `HYPERI_CONFIG_DSN` | PostgreSQL connection URL (required to enable) | None |
| `HYPERI_CONFIG_TABLE` | Table name for config values | `config_values` |
| `HYPERI_CONFIG_NAMESPACE` | Namespace for app isolation | `default` |
| `HYPERI_CONFIG_CACHE_TTL` | In-memory cache TTL (seconds) | `60` |
| `HYPERI_CONFIG_CONNECT_TIMEOUT` | Connection timeout (seconds) | `5` |
| `HYPERI_CONFIG_QUERY_TIMEOUT` | Query timeout (seconds) | `10` |
| `HYPERI_CONFIG_RETRY_ATTEMPTS` | Retry attempts on connection failure | `3` |
| `HYPERI_CONFIG_RETRY_DELAY_MS` | Delay between retries (milliseconds) | `1000` |
| `HYPERI_CONFIG_OPTIONAL` | Continue if PostgreSQL unavailable | `true` |

### Fallback File Settings (NEW)

| Variable | Description | Default |
|----------|-------------|---------|
| `HYPERI_CONFIG_FALLBACK_ENABLED` | Enable fallback file generation | `false` |
| `HYPERI_CONFIG_FALLBACK_FILE` | Path to fallback file | `/tmp/{namespace}_config_fallback.yaml` |
| `HYPERI_CONFIG_FALLBACK_MODE` | `replace` or `merge` | `replace` |

**Example:**

```bash
export HYPERI_CONFIG_DSN="postgres://config_user:secret@config-db:5432/config"
export HYPERI_CONFIG_NAMESPACE="dfe-loader-prod"
export HYPERI_CONFIG_FALLBACK_ENABLED="true"
export HYPERI_CONFIG_FALLBACK_FILE="/config/fallback.yaml"
```

---

## Fallback File Support

When PostgreSQL config is loaded successfully, it can optionally be written to a local YAML file. If PostgreSQL becomes unavailable on subsequent loads, the fallback file is used instead.

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Config Load Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Check in-memory cache                                        │
│     ↓ (cache miss or expired)                                    │
│                                                                  │
│  2. Try PostgreSQL connection                                    │
│     ├─ SUCCESS ──────────────────────────────────────────┐       │
│     │   a. Load config from DB                           │       │
│     │   b. Update in-memory cache                        │       │
│     │   c. Write fallback file (if enabled)              │       │
│     │   d. Return config                                 │       │
│     │                                                    │       │
│     └─ FAILURE (after retries) ──────────────────────┐   │       │
│         │                                            │   │       │
│         ▼                                            │   │       │
│  3. Try fallback file (if enabled)                   │   │       │
│     ├─ EXISTS: Load and return                       │   │       │
│     └─ NOT EXISTS: Return empty / raise error        │   │       │
│                                                      │   │       │
└──────────────────────────────────────────────────────┴───┴───────┘
```

### Fallback Modes

**Replace mode** (default): Fallback file contains only PostgreSQL config.

**Merge mode**: Fallback file merges with existing local config. New PostgreSQL values overwrite existing, but local-only keys are preserved.

---

## Python Implementation (hyperi-pylib)

### Dependencies

- `psycopg` (psycopg3) - async-capable PostgreSQL driver
- `pyyaml` - YAML serialization for fallback files

### Usage

```python
# Automatic integration - just set HYPERI_CONFIG_DSN
from hyperi_pylib.config import settings

# PostgreSQL config is automatically loaded and merged
value = settings.database.host  # Returns PostgreSQL value (overrides files)

# Manual loading for custom scenarios
from hyperi_pylib.config import PostgresConfigLoader

loader = PostgresConfigLoader(
    dsn="postgresql://user:pass@host/db",
    namespace="my-app",
    fallback_enabled=True,
    fallback_file="/config/fallback.yaml",
)

# Sync loading
config = loader.load_sync()

# Async loading
config = await loader.load_async()

# Ensure table exists (with optional audit trail)
loader.ensure_table(with_audit=True)

# CRUD operations (for admin tools)
loader.set_value("database.host", "new-host.example.com", updated_by="admin")
loader.delete_value("deprecated.setting")
loader.delete_namespace()  # Delete all keys in namespace
history = loader.get_history(key="database.host", limit=10)
```

### Key Classes

```python
class PostgresConfigLoader:
    """PostgreSQL configuration loader with caching and fallback support."""

    def __init__(
        self,
        dsn: str | None = None,
        table_name: str | None = None,
        namespace: str | None = None,
        cache_ttl: int | None = None,
        connect_timeout: int | None = None,
        query_timeout: int | None = None,
        retry_attempts: int | None = None,
        retry_delay_ms: int | None = None,
        optional: bool | None = None,
        fallback_enabled: bool | None = None,
        fallback_file: str | None = None,
        fallback_mode: str | None = None,  # "replace" or "merge"
    ): ...

class PostgresConfigError(Exception):
    """Raised when PostgreSQL config operations fail."""

class PostgresConfigUnavailable(PostgresConfigError):
    """Raised when PostgreSQL is unavailable but optional=True."""
```

---

## Rust Implementation (hs-rustlib)

### Dependencies

Add to `Cargo.toml`:

```toml
[dependencies]
sqlx = { version = "0.8", features = ["runtime-tokio", "tls-rustls", "postgres", "json"], optional = true }
serde_yaml = "0.9"

[features]
config-postgres = ["dep:sqlx"]
```

### Configuration Struct

```rust
use std::path::PathBuf;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub enum FallbackMode {
    #[default]
    Replace,
    Merge,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PostgresConfigSource {
    /// Enable PostgreSQL config source
    pub enabled: bool,

    /// PostgreSQL connection URL
    pub url: Option<String>,

    /// Application ID for multi-tenant config (called "namespace" in Python)
    pub app_id: String,

    /// Connection timeout in seconds
    pub connect_timeout_secs: u64,

    /// Query timeout in seconds
    pub query_timeout_secs: u64,

    /// Retry attempts on connection failure
    pub retry_attempts: u32,

    /// Retry delay in milliseconds
    pub retry_delay_ms: u64,

    /// Continue startup if PostgreSQL is unavailable
    pub optional: bool,

    /// Enable fallback file generation
    pub fallback_enabled: bool,

    /// Path to fallback file (default: /tmp/{app_id}_config_fallback.yaml)
    pub fallback_file: Option<PathBuf>,

    /// Fallback mode: Replace or Merge
    pub fallback_mode: FallbackMode,
}

impl Default for PostgresConfigSource {
    fn default() -> Self {
        Self {
            enabled: false,
            url: None,
            app_id: "default".to_string(),
            connect_timeout_secs: 5,
            query_timeout_secs: 10,
            retry_attempts: 3,
            retry_delay_ms: 1000,
            optional: true,
            fallback_enabled: false,
            fallback_file: None,
            fallback_mode: FallbackMode::Replace,
        }
    }
}
```

### Config Loader

```rust
use sqlx::postgres::{PgPool, PgPoolOptions};
use std::collections::HashMap;
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct PostgresConfig {
    /// Flat map of dot-notation keys to JSON values
    pub values: HashMap<String, serde_json::Value>,
}

impl PostgresConfig {
    /// Load configuration from PostgreSQL with fallback support
    pub async fn load(source: &PostgresConfigSource) -> Result<Option<Self>, PostgresConfigError> {
        if !source.enabled {
            return Ok(None);
        }

        let url = match &source.url {
            Some(url) => url.clone(),
            None => {
                if source.optional {
                    return Ok(None);
                } else {
                    return Err(PostgresConfigError::NotConfigured);
                }
            }
        };

        // Try to load from database
        match Self::load_from_db(&url, source).await {
            Ok(config) => {
                // Success: write fallback file if enabled
                if source.fallback_enabled && !config.values.is_empty() {
                    if let Err(e) = Self::write_fallback_file(source, &config) {
                        tracing::warn!(error = %e, "Failed to write fallback file");
                    }
                }
                Ok(Some(config))
            }
            Err(e) => {
                // Failed: try fallback file if enabled
                if source.fallback_enabled {
                    if let Ok(Some(fallback)) = Self::load_fallback_file(source) {
                        tracing::info!("Loaded config from fallback file (PostgreSQL unavailable)");
                        return Ok(Some(fallback));
                    }
                }

                if source.optional {
                    tracing::warn!(error = %e, "PostgreSQL config unavailable, continuing without");
                    Ok(None)
                } else {
                    Err(e)
                }
            }
        }
    }

    async fn load_from_db(url: &str, source: &PostgresConfigSource) -> Result<Self, PostgresConfigError> {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .acquire_timeout(Duration::from_secs(source.connect_timeout_secs))
            .connect(url)
            .await
            .map_err(|e| PostgresConfigError::Connection(e.to_string()))?;

        let rows = sqlx::query(
            r#"SELECT key, value FROM config_values WHERE namespace = $1 ORDER BY key"#
        )
        .bind(&source.app_id)
        .fetch_all(&pool)
        .await
        .map_err(|e| PostgresConfigError::Query(e.to_string()))?;

        let mut values = HashMap::with_capacity(rows.len());
        for row in rows {
            let key: String = row.try_get("key")?;
            let value: serde_json::Value = row.try_get("value")?;
            values.insert(key, value);
        }

        Ok(Self { values })
    }

    fn write_fallback_file(source: &PostgresConfigSource, config: &Self) -> Result<(), PostgresConfigError> {
        let path = source.fallback_file.clone()
            .unwrap_or_else(|| PathBuf::from(format!("/tmp/{}_config_fallback.yaml", source.app_id)));

        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let nested = config.to_nested();

        let config_to_write = match source.fallback_mode {
            FallbackMode::Merge if path.exists() => {
                let file = std::fs::File::open(&path)?;
                let existing: HashMap<String, serde_json::Value> = serde_yaml::from_reader(file)?;
                deep_merge(existing, nested)
            }
            _ => nested,
        };

        let mut file = std::fs::File::create(&path)?;
        writeln!(file, "# PostgreSQL config fallback file")?;
        writeln!(file, "# Generated at: {}", chrono::Utc::now().format("%Y-%m-%d %H:%M:%S UTC"))?;
        writeln!(file, "# Namespace: {}", source.app_id)?;
        writeln!(file, "# Mode: {:?}", source.fallback_mode)?;
        writeln!(file, "# This file is auto-generated. Do not edit manually.\n")?;
        serde_yaml::to_writer(&mut file, &config_to_write)?;

        Ok(())
    }

    fn load_fallback_file(source: &PostgresConfigSource) -> Result<Option<Self>, PostgresConfigError> {
        let path = source.fallback_file.clone()
            .unwrap_or_else(|| PathBuf::from(format!("/tmp/{}_config_fallback.yaml", source.app_id)));

        if !path.exists() {
            return Ok(None);
        }

        let file = std::fs::File::open(&path)?;
        let nested: HashMap<String, serde_json::Value> = serde_yaml::from_reader(file)?;
        let values = flatten_nested(nested);

        Ok(Some(Self { values }))
    }

    /// Convert flat dot-notation keys to nested HashMap
    pub fn to_nested(&self) -> HashMap<String, serde_json::Value> {
        let mut root = HashMap::new();
        for (key, value) in &self.values {
            insert_nested(&mut root, key, value.clone());
        }
        root
    }
}

/// Insert a dot-notation key into a nested map
fn insert_nested(map: &mut HashMap<String, serde_json::Value>, key: &str, value: serde_json::Value) {
    let parts: Vec<&str> = key.split('.').collect();

    if parts.len() == 1 {
        map.insert(key.to_string(), value);
        return;
    }

    let first = parts[0];
    let rest = parts[1..].join(".");

    let entry = map.entry(first.to_string())
        .or_insert_with(|| serde_json::Value::Object(serde_json::Map::new()));

    if let serde_json::Value::Object(ref mut obj) = entry {
        let mut inner: HashMap<String, serde_json::Value> = obj
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        insert_nested(&mut inner, &rest, value);
        *obj = inner.into_iter().collect();
    }
}

/// Deep merge two HashMaps (override values take precedence)
fn deep_merge(
    base: HashMap<String, serde_json::Value>,
    override_map: HashMap<String, serde_json::Value>,
) -> HashMap<String, serde_json::Value> {
    let mut result = base;
    for (key, value) in override_map {
        match (result.get(&key), &value) {
            (Some(serde_json::Value::Object(base_obj)), serde_json::Value::Object(override_obj)) => {
                let base_map: HashMap<String, serde_json::Value> = base_obj.iter()
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect();
                let override_map: HashMap<String, serde_json::Value> = override_obj.iter()
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect();
                let merged = deep_merge(base_map, override_map);
                result.insert(key, serde_json::Value::Object(merged.into_iter().collect()));
            }
            _ => {
                result.insert(key, value);
            }
        }
    }
    result
}

#[derive(Debug, thiserror::Error)]
pub enum PostgresConfigError {
    #[error("PostgreSQL config source not configured")]
    NotConfigured,

    #[error("PostgreSQL connection error: {0}")]
    Connection(String),

    #[error("PostgreSQL query error: {0}")]
    Query(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),
}
```

### Integration with Config Cascade

```rust
impl Config {
    /// Load configuration with PostgreSQL OVERRIDING file-based config
    pub async fn load_async(config_path: Option<&str>) -> Result<Self> {
        let _ = dotenvy::dotenv();

        let pg_source = Self::load_postgres_source_from_env();
        let pg_config = PostgresConfig::load(&pg_source).await?;

        let mut builder = config::Config::builder();

        // 8. Hard-coded defaults (lowest priority)
        builder = builder.add_source(config::Config::try_from(&Config::default())?);

        // 7. defaults.yaml
        // 6. settings.yaml
        // 5. settings.{env}.yaml
        if let Some(path) = config_path {
            if Path::new(path).exists() {
                builder = builder.add_source(config::File::new(path, config::FileFormat::Yaml));
            }
        }

        // 4. PostgreSQL config - OVERRIDES files using set_override
        if let Some(ref pg) = pg_config {
            for (key, value) in &pg.values {
                // Use set_override to ensure PostgreSQL takes precedence over files
                builder = builder.set_override(&key, json_to_config_value(value))?;
            }
            tracing::info!(keys = pg.values.len(), "PostgreSQL config loaded (overrides files)");
        }

        // 3. .env already loaded via dotenvy
        // 2. Environment variables (highest after CLI)
        builder = builder.add_source(
            config::Environment::with_prefix("LOADER")
                .separator("_")
                .try_parsing(true),
        );

        // 1. CLI args handled by application layer

        let config = builder.build()?;
        config.try_deserialize()
    }

    fn load_postgres_source_from_env() -> PostgresConfigSource {
        PostgresConfigSource {
            enabled: std::env::var("HYPERI_CONFIG_DSN").is_ok(),
            url: std::env::var("HYPERI_CONFIG_DSN").ok(),
            app_id: std::env::var("HYPERI_CONFIG_NAMESPACE")
                .unwrap_or_else(|_| "default".to_string()),
            connect_timeout_secs: std::env::var("HYPERI_CONFIG_CONNECT_TIMEOUT")
                .ok().and_then(|v| v.parse().ok()).unwrap_or(5),
            query_timeout_secs: std::env::var("HYPERI_CONFIG_QUERY_TIMEOUT")
                .ok().and_then(|v| v.parse().ok()).unwrap_or(10),
            retry_attempts: std::env::var("HYPERI_CONFIG_RETRY_ATTEMPTS")
                .ok().and_then(|v| v.parse().ok()).unwrap_or(3),
            retry_delay_ms: std::env::var("HYPERI_CONFIG_RETRY_DELAY_MS")
                .ok().and_then(|v| v.parse().ok()).unwrap_or(1000),
            optional: std::env::var("HYPERI_CONFIG_OPTIONAL")
                .map(|v| !v.eq_ignore_ascii_case("false") && v != "0")
                .unwrap_or(true),
            fallback_enabled: std::env::var("HYPERI_CONFIG_FALLBACK_ENABLED")
                .map(|v| v.eq_ignore_ascii_case("true") || v == "1")
                .unwrap_or(false),
            fallback_file: std::env::var("HYPERI_CONFIG_FALLBACK_FILE")
                .ok().map(PathBuf::from),
            fallback_mode: std::env::var("HYPERI_CONFIG_FALLBACK_MODE")
                .map(|v| if v.eq_ignore_ascii_case("merge") { FallbackMode::Merge } else { FallbackMode::Replace })
                .unwrap_or_default(),
        }
    }
}
```

---

## K8s/HELM Deployment

```yaml
# values.yaml
config:
  postgres:
    enabled: true
    namespace: "my-app-prod"
    fallbackEnabled: true
    fallbackFile: "/config/fallback.yaml"

# deployment.yaml
env:
  - name: HYPERI_CONFIG_DSN
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: config-dsn
  - name: HYPERI_CONFIG_NAMESPACE
    value: {{ .Values.config.postgres.namespace | quote }}
  - name: HYPERI_CONFIG_FALLBACK_ENABLED
    value: {{ .Values.config.postgres.fallbackEnabled | quote }}
  - name: HYPERI_CONFIG_FALLBACK_FILE
    value: {{ .Values.config.postgres.fallbackFile | quote }}

volumeMounts:
  - name: config-volume
    mountPath: /config

volumes:
  - name: config-volume
    emptyDir: {}  # Or persistentVolumeClaim for durability
```

---

## Testing

### Unit Tests (Required)

```python
# Python tests - see tests/unit/test_config_postgres_loader.py
def test_init_fallback_disabled_by_default(): ...
def test_init_fallback_enabled_from_env(): ...
def test_init_fallback_file_from_env(): ...
def test_init_fallback_mode_from_env(): ...
def test_write_fallback_file_creates_file(): ...
def test_write_fallback_file_merge_mode(): ...
def test_load_fallback_file_success(): ...
def test_deep_merge_nested(): ...
def test_load_sync_uses_fallback_on_connection_error(): ...
def test_postgres_overrides_file_config(): ...
```

```rust
// Rust tests
#[test]
fn test_fallback_file_disabled_by_default() { ... }

#[test]
fn test_fallback_file_created_on_success() { ... }

#[test]
fn test_fallback_file_merge_mode() { ... }

#[test]
fn test_fallback_file_used_when_db_unavailable() { ... }

#[test]
fn test_postgres_overrides_file_config() { ... }

#[test]
fn test_insert_nested_multi_level() { ... }

#[test]
fn test_deep_merge_preserves_base_keys() { ... }
```

### Integration Tests (Requires PostgreSQL)

```bash
# Start local PostgreSQL
docker compose -f docker-compose.postgres.yml up -d

# Run integration tests
pytest tests/integration/test_config_postgres_loader.py -v
```

---

## Migration Checklist

### hyperi-pylib (Python) ✅ COMPLETE

- [x] Update cascade priority (PostgreSQL now layer 4)
- [x] Add fallback file support
- [x] Add `_write_fallback_file()` method
- [x] Add `_load_fallback_file()` method
- [x] Add `_deep_merge()` method
- [x] Update `load_sync()` to write fallback on success
- [x] Update `load_sync()` to use fallback on failure
- [x] Update `load_async()` similarly
- [x] Add unit tests for fallback functionality
- [x] Update docstrings and documentation

### hs-rustlib (Rust) ⬜ TODO

- [ ] Add `FallbackMode` enum
- [ ] Add fallback fields to `PostgresConfigSource`
- [ ] Implement `write_fallback_file()` function
- [ ] Implement `load_fallback_file()` function
- [ ] Implement `deep_merge()` function
- [ ] Update `PostgresConfig::load()` for fallback support
- [ ] Update config cascade to use `set_override()` for PostgreSQL
- [ ] Add unit tests for fallback functionality
- [ ] Update documentation

---

## References

- [psycopg3 documentation](https://www.psycopg.org/psycopg3/docs/)
- [sqlx documentation](https://docs.rs/sqlx/)
- [config-rs documentation](https://docs.rs/config/)
- [Dynaconf documentation](https://www.dynaconf.com/)
