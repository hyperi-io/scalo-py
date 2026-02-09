"""Tests for hyperi_pylib.database module."""

import os

import pytest

from hyperi_pylib.database import build_database_url, get_database_config


class TestClickHouseSupport:
    """Test ClickHouse database URL building."""

    def test_clickhouse_default_port(self):
        """Test ClickHouse uses port 9000 by default."""
        config = get_database_config("clickhouse")
        assert config["port"] == 9000

    def test_clickhouse_url_native_protocol(self, monkeypatch):
        """Test ClickHouse native protocol URL building."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch.example.com")
        monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
        monkeypatch.setenv("CLICKHOUSE_USER", "analyst")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "secret")
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "analytics")

        url = build_database_url("clickhouse")
        assert url == "clickhouse://analyst:secret@ch.example.com:9000/analytics"

    def test_clickhouse_url_without_password(self, monkeypatch):
        """Test ClickHouse URL without password."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "localhost")
        monkeypatch.setenv("CLICKHOUSE_USER", "default")
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "default")

        url = build_database_url("clickhouse")
        assert url == "clickhouse://default@localhost:9000/default"

    def test_clickhouse_url_defaults(self):
        """Test ClickHouse with all defaults."""
        # Clear any existing CLICKHOUSE_* env vars
        for key in list(os.environ.keys()):
            if key.startswith("CLICKHOUSE_"):
                del os.environ[key]

        url = build_database_url("clickhouse")
        # Should use defaults: localhost:9000, no user/pass, no database
        assert "clickhouse://" in url
        assert "localhost:9000" in url

    def test_clickhouse_url_with_special_chars(self, monkeypatch):
        """Test ClickHouse URL with special characters in password."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "ch.example.com")
        monkeypatch.setenv("CLICKHOUSE_USER", "user")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "p@ss:word!")
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "db")

        url = build_database_url("clickhouse")
        # Password should be URL-encoded
        assert url == "clickhouse://user:p%40ss%3Aword%21@ch.example.com:9000/db"

    def test_clickhouse_config_from_env(self, monkeypatch):
        """Test ClickHouse configuration from environment variables."""
        monkeypatch.setenv("CLICKHOUSE_HOST", "prod-ch.internal")
        monkeypatch.setenv("CLICKHOUSE_PORT", "9440")
        monkeypatch.setenv("CLICKHOUSE_USER", "analytics_user")
        monkeypatch.setenv("CLICKHOUSE_PASSWORD", "prod_secret")
        monkeypatch.setenv("CLICKHOUSE_DATABASE", "metrics")

        config = get_database_config("clickhouse")

        assert config["host"] == "prod-ch.internal"
        assert config["port"] == 9440
        assert config["user"] == "analytics_user"
        assert config["password"] == "prod_secret"
        assert config["database"] == "metrics"

    def test_clickhouse_custom_env_prefix(self, monkeypatch):
        """Test ClickHouse with custom environment prefix."""
        monkeypatch.setenv("ANALYTICS_HOST", "analytics-ch.svc")
        monkeypatch.setenv("ANALYTICS_PORT", "9000")
        monkeypatch.setenv("ANALYTICS_USER", "analytics")
        monkeypatch.setenv("ANALYTICS_PASSWORD", "secret")
        monkeypatch.setenv("ANALYTICS_DATABASE", "events")

        url = build_database_url("clickhouse", env_prefix="ANALYTICS")
        assert url == "clickhouse://analytics:secret@analytics-ch.svc:9000/events"


class TestExistingDatabases:
    """Test existing database URL building still works."""

    def test_postgresql_url(self, monkeypatch):
        """Test PostgreSQL URL building."""
        monkeypatch.setenv("POSTGRES_HOST", "db.example.com")
        monkeypatch.setenv("POSTGRES_USER", "myuser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "mypass")
        monkeypatch.setenv("POSTGRES_DATABASE", "mydb")

        url = build_database_url("postgresql")
        assert "postgresql://myuser:mypass@db.example.com:5432/mydb" in url

    def test_mysql_url(self, monkeypatch):
        """Test MySQL URL building."""
        monkeypatch.setenv("MYSQL_HOST", "mysql.example.com")
        monkeypatch.setenv("MYSQL_USER", "root")
        monkeypatch.setenv("MYSQL_PASSWORD", "secret")
        monkeypatch.setenv("MYSQL_DATABASE", "app")

        url = build_database_url("mysql")
        assert "mysql://root:secret@mysql.example.com:3306/app" in url

    def test_mongodb_url(self, monkeypatch):
        """Test MongoDB URL building."""
        monkeypatch.setenv("MONGO_HOST", "mongo.example.com")
        monkeypatch.setenv("MONGO_USER", "admin")
        monkeypatch.setenv("MONGO_PASSWORD", "secret")
        monkeypatch.setenv("MONGO_DATABASE", "myapp")

        url = build_database_url("mongodb")
        assert "mongodb://admin:secret@mongo.example.com:27017/myapp" in url

    def test_redis_url(self, monkeypatch):
        """Test Redis URL building."""
        monkeypatch.setenv("REDIS_HOST", "redis.example.com")
        monkeypatch.setenv("REDIS_PASSWORD", "secret")
        monkeypatch.setenv("REDIS_DB", "0")

        url = build_database_url("redis")
        # Redis URL format doesn't include port in path by default
        assert url == "redis://:secret@redis.example.com/0"
