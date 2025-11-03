"""
HyperLib Database Utilities - Zero-Config Connection Builders
===============================================================

Automatic database connection URL construction from ENV variables.
Supports PostgreSQL, MySQL, MongoDB, Redis, ClickHouse - zero configuration!

Quick Start
===========

    # Install
    pip install hyperlib[database]

    # PostgreSQL (automatic ENV detection!)
    from hyperlib import build_database_url

    # Reads: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DATABASE
    db_url = build_database_url("postgresql")
    # → postgresql://user:pass@host:5432/dbname

    # Use with SQLAlchemy, asyncpg, psycopg2, etc.
    from sqlalchemy import create_engine
    engine = create_engine(db_url)

Standard ENV Variables (Cloud-Native)
======================================

**PostgreSQL:**

    POSTGRES_HOST=prod-db.svc.cluster.local
    POSTGRES_PORT=5432
    POSTGRES_USER=myapp
    POSTGRES_PASSWORD=secret123
    POSTGRES_DATABASE=production
    POSTGRES_SSLMODE=require

**MySQL:**

    MYSQL_HOST=mysql.example.com
    MYSQL_PORT=3306
    MYSQL_USER=root
    MYSQL_PASSWORD=secret
    MYSQL_DATABASE=mydb

**MongoDB:**

    MONGO_HOST=mongo.svc.local
    MONGO_PORT=27017
    MONGO_USER=admin
    MONGO_PASSWORD=secret
    MONGO_DATABASE=app_db

**Redis:**

    REDIS_HOST=redis.svc.local
    REDIS_PORT=6379
    REDIS_PASSWORD=secret
    REDIS_DB=0

**ClickHouse:**

    CLICKHOUSE_HOST=clickhouse.svc
    CLICKHOUSE_PORT=9000
    CLICKHOUSE_USER=default
    CLICKHOUSE_PASSWORD=secret
    CLICKHOUSE_DATABASE=analytics

Usage Patterns
==============

    # Pattern 1: Auto-detect from ENV (most common)
    from hyperlib.dbconn import build_database_url

    postgres_url = build_database_url("postgresql")
    mysql_url = build_database_url("mysql")

    # Pattern 2: Get config dict
    from hyperlib.dbconn import get_database_config

    config = get_database_config("postgresql")
    # Returns: {host: "...", port: 5432, user: "...", password: "...", database: "..."}

    # Pattern 3: Custom ENV prefix (multi-database apps)
    primary_url = build_database_url("postgresql", env_prefix="PRIMARY")
    # Reads: PRIMARY_HOST, PRIMARY_PORT, etc.

    cache_url = build_database_url("redis", env_prefix="CACHE")
    # Reads: CACHE_HOST, CACHE_PORT, etc.

Deployment
==========

**Kubernetes Secrets:**

    apiVersion: v1
    kind: Secret
    metadata:
      name: database
    stringData:
      POSTGRES_HOST: prod-db.svc.cluster.local
      POSTGRES_USER: myapp
      POSTGRES_PASSWORD: super-secret
      POSTGRES_DATABASE: production

**Docker Compose:**

    environment:
      POSTGRES_HOST: db
      POSTGRES_USER: myapp
      POSTGRES_PASSWORD: secret
      POSTGRES_DATABASE: myapp_db

**Local Dev (.env file):**

    POSTGRES_HOST=localhost
    POSTGRES_USER=dev
    POSTGRES_PASSWORD=dev123
    POSTGRES_DATABASE=myapp_dev

Zero Configuration Required
============================

✅ Auto-reads standard ENV variables
✅ Builds connection URLs automatically
✅ Supports all major databases
✅ Works in K8s, Docker, local
✅ No hardcoded credentials
"""

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlunparse

from .config import get_mount_config


def get_database_config(
    db_type: str = "postgresql", env_prefix: str | None = None, use_standard_vars: bool = True
) -> dict[str, Any]:
    """
    Get database configuration from environment variables.

    Args:
        db_type: Type of database (postgresql, mysql, mongodb, redis)
        env_prefix: Environment variable prefix (defaults to db_type uppercase)
        use_standard_vars: Also check standard variable names (POSTGRES_*, MYSQL_*, etc.)

    Returns:
        Dictionary with host, port, user, password, database, and other settings

    Example:
        >>> # With POSTGRES_HOST=db.example.com, POSTGRES_USER=myuser
        >>> config = get_database_config("postgresql")
        >>> config["host"]
        'db.example.com'
    """
    if env_prefix is None:
        env_prefix = db_type.upper()

    # Default ports for common databases
    default_ports = {
        "postgresql": 5432,
        "postgres": 5432,
        "mysql": 3306,
        "mariadb": 3306,
        "mongodb": 27017,
        "redis": 6379,
        "mssql": 1433,
        "oracle": 1521,
    }

    # Try standard variable names first if enabled
    config = {}
    if use_standard_vars:
        # Check for common Docker/K8s database environment patterns
        standard_prefixes = []
        if db_type.lower() in ["postgresql", "postgres"]:
            standard_prefixes = ["POSTGRES", "POSTGRESQL", "PG"]
        elif db_type.lower() in ["mysql", "mariadb"]:
            standard_prefixes = ["MYSQL", "MARIADB"]
        elif db_type.lower() == "mongodb":
            standard_prefixes = ["MONGODB", "MONGO"]
        elif db_type.lower() == "redis":
            standard_prefixes = ["REDIS"]

        for prefix in standard_prefixes:
            if not config.get("host"):
                config["host"] = os.getenv(f"{prefix}_HOST") or os.getenv(f"{prefix}_SERVICE_HOST")
            if not config.get("port"):
                port_val = os.getenv(f"{prefix}_PORT") or os.getenv(f"{prefix}_SERVICE_PORT")
                config["port"] = int(port_val) if port_val else None
            if not config.get("user"):
                config["user"] = os.getenv(f"{prefix}_USER") or os.getenv(f"{prefix}_USERNAME")
            if not config.get("password"):
                config["password"] = os.getenv(f"{prefix}_PASSWORD") or os.getenv(f"{prefix}_PASS")
            if not config.get("database"):
                config["database"] = os.getenv(f"{prefix}_DATABASE") or os.getenv(f"{prefix}_DB")

    # Override with specific prefix values
    config.update(
        {
            "host": os.getenv(f"{env_prefix}_HOST", config.get("host", "localhost")),
            "port": int(
                os.getenv(f"{env_prefix}_PORT", config.get("port") or default_ports.get(db_type.lower(), 5432))
            ),
            "user": os.getenv(f"{env_prefix}_USER", config.get("user")),
            "password": os.getenv(f"{env_prefix}_PASSWORD", config.get("password")),
            "database": os.getenv(f"{env_prefix}_DATABASE", config.get("database")),
        }
    )

    # Additional settings based on database type
    if db_type.lower() in ["postgresql", "postgres"]:
        config["sslmode"] = os.getenv(f"{env_prefix}_SSLMODE", "prefer")
        config["connect_timeout"] = os.getenv(f"{env_prefix}_CONNECT_TIMEOUT", "10")

    elif db_type.lower() in ["mysql", "mariadb"]:
        config["charset"] = os.getenv(f"{env_prefix}_CHARSET", "utf8mb4")
        config["ssl_ca"] = os.getenv(f"{env_prefix}_SSL_CA")

    elif db_type.lower() == "mongodb":
        config["authSource"] = os.getenv(f"{env_prefix}_AUTH_SOURCE", "admin")
        config["replicaSet"] = os.getenv(f"{env_prefix}_REPLICA_SET")

    elif db_type.lower() == "redis":
        config["db"] = int(os.getenv(f"{env_prefix}_DB", "0"))
        config["ssl"] = os.getenv(f"{env_prefix}_SSL", "false").lower() == "true"

    return config


def build_database_url(
    db_type: str = "postgresql",
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
    env_prefix: str | None = None,
    **kwargs,
) -> str:
    """
    Build a complete database connection URL.

    Args:
        db_type: Type of database (postgresql, mysql, mongodb, redis, etc.)
        host: Database host (overrides environment)
        port: Database port (overrides environment)
        user: Database user (overrides environment)
        password: Database password (overrides environment)
        database: Database name (overrides environment)
        env_prefix: Environment variable prefix for auto-detection
        **kwargs: Additional connection parameters

    Returns:
        Complete database URL string

    Example:
        >>> # Build PostgreSQL URL
        >>> url = build_database_url("postgresql", host="localhost", user="myuser", database="mydb")
        >>> url
        'postgresql://myuser@localhost:5432/mydb'

        >>> # Auto-detect from environment
        >>> os.environ["POSTGRES_HOST"] = "db.example.com"
        >>> url = build_database_url("postgresql")
        >>> url
        'postgresql://user:pass@db.example.com:5432/mydb'
    """
    # Get config from environment if not provided
    config = get_database_config(db_type, env_prefix)

    # Override with provided values
    host = host or config.get("host", "localhost")
    port = port or config.get("port")
    user = user or config.get("user")
    password = password or config.get("password")
    database = database or config.get("database")

    # URL scheme mapping
    scheme_map = {
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "mysql": "mysql",
        "mariadb": "mysql",
        "mongodb": "mongodb",
        "redis": "redis",
        "mssql": "mssql+pyodbc",
        "sqlite": "sqlite",
    }

    scheme = scheme_map.get(db_type.lower(), db_type.lower())

    # Special case for SQLite
    if db_type.lower() == "sqlite":
        if database and database != ":memory:" and not Path(database).is_absolute():
            # Use data directory for SQLite files if not absolute path
            mount_config = get_mount_config()
            database = str(mount_config.data_dir / database)
        return f"sqlite:///{database or ':memory:'}"

    # Build URL components
    if user and password:
        netloc = f"{quote_plus(user)}:{quote_plus(password)}@{host}"
    elif user:
        netloc = f"{quote_plus(user)}@{host}"
    else:
        netloc = host

    if port:
        netloc = f"{netloc}:{port}"

    # Build query parameters
    params = []

    # Add database-specific parameters
    if db_type.lower() in ["postgresql", "postgres"]:
        if config.get("sslmode"):
            params.append(f"sslmode={config['sslmode']}")
        if config.get("connect_timeout"):
            params.append(f"connect_timeout={config['connect_timeout']}")

    elif db_type.lower() in ["mysql", "mariadb"]:
        if config.get("charset"):
            params.append(f"charset={config['charset']}")
        if config.get("ssl_ca"):
            params.append(f"ssl_ca={config['ssl_ca']}")

    elif db_type.lower() == "mongodb":
        if config.get("authSource"):
            params.append(f"authSource={config['authSource']}")
        if config.get("replicaSet"):
            params.append(f"replicaSet={config['replicaSet']}")

    elif db_type.lower() == "redis":
        # Redis URLs are different - redis://[:password]@host:port/db
        if password:
            netloc = f":{quote_plus(password)}@{host}"
        database = str(config.get("db", 0))

    # Add any additional kwargs as query parameters
    for key, value in kwargs.items():
        if value is not None:
            params.append(f"{key}={value}")

    query_string = "&".join(params) if params else ""

    # Build the complete URL
    url_parts = (scheme, netloc, database or "", "", query_string, "")  # params (not used)  # fragment (not used)

    return urlunparse(url_parts)


def get_database_url_from_env(env_var: str = "DATABASE_URL", fallback_type: str = "postgresql") -> str | None:
    """
    Get database URL from environment variable or build from components.

    Args:
        env_var: Environment variable name to check first
        fallback_type: Database type to use if building from components

    Returns:
        Database URL string or None if not configured

    Example:
        >>> # First checks DATABASE_URL env var
        >>> # If not found, builds from POSTGRES_* or other standard vars
        >>> url = get_database_url_from_env()
    """
    # Check for complete URL first
    url = os.getenv(env_var)
    if url:
        return url

    # Try to build from components
    config = get_database_config(fallback_type)
    if config.get("host") and config.get("database"):
        return build_database_url(fallback_type, **config)

    return None


def parse_database_url(url: str) -> dict[str, Any]:
    """
    Parse a database URL into its components.

    Args:
        url: Database URL string

    Returns:
        Dictionary with parsed components

    Example:
        >>> config = parse_database_url("postgresql://user:pass@localhost:5432/mydb")
        >>> config["host"]
        'localhost'
    """
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(url)

    # Extract user and password
    user = parsed.username
    password = parsed.password

    # Parse query parameters
    params = parse_qs(parsed.query) if parsed.query else {}
    # Flatten single-value lists
    params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "localhost",
        "port": parsed.port,
        "user": user,
        "password": password,
        "database": parsed.path.lstrip("/") if parsed.path else None,
        "params": params,
    }


# Convenience functions for specific databases
def get_postgresql_url(**kwargs) -> str:
    """Build PostgreSQL connection URL."""
    return build_database_url("postgresql", **kwargs)


def get_mysql_url(**kwargs) -> str:
    """Build MySQL connection URL."""
    return build_database_url("mysql", **kwargs)


def get_mongodb_url(**kwargs) -> str:
    """Build MongoDB connection URL."""
    return build_database_url("mongodb", **kwargs)


def get_redis_url(**kwargs) -> str:
    """Build Redis connection URL."""
    return build_database_url("redis", **kwargs)
