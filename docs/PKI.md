# hyperi-pylib TLS/PKI Integration Guide

## Overview

This document covers TLS configuration for hyperi-pylib components. All TLS settings follow the [PKI standards](../ai/standards/common/PKI.md) with profile-based security levels.

## Security Profiles

| Profile | TLS Certs | Use Case |
| ------- | --------- | -------- |
| **prod** | ECDSA P-384 | Production, customer-facing (corporate default) |
| devtest | ECDSA P-256 | Dev, staging, internal tools |
| highsec | P-384 + FIPS | Federal/defence contracts |

**Default profile: `prod`** - If unsure, use prod.

---

## Planned: `hyperi_pylib.tls` Module

The following module will provide zero-config TLS with profile-based defaults.

### SSL Context Factory

```python
# Future API - hyperi_pylib.tls module
from hyperi_pylib.tls import create_ssl_context

# Usage
ctx = create_ssl_context(profile="prod")     # Corporate default (P-384)
ctx = create_ssl_context(profile="devtest")  # Dev/staging (P-256)
ctx = create_ssl_context(profile="highsec")  # Federal/CNSA 2.0

# With custom CA bundle
ctx = create_ssl_context(profile="prod", ca_bundle="/path/to/ca.crt")
```

### Implementation Reference

```python
"""
hyperi_pylib/tls.py - TLS configuration factory

Implementation notes for contributors.
"""
import ssl
from enum import Enum
from typing import Optional
import certifi

class TlsProfile(str, Enum):
    """Security profile for TLS configuration."""
    PROD = "prod"        # P-384, SHA-384, TLS 1.2+
    DEVTEST = "devtest"  # P-256, SHA-256, TLS 1.2+
    HIGHSEC = "highsec"  # P-384, SHA-384, TLS 1.3 only, FIPS

# Cipher suites by profile
CIPHERS_PROD = [
    "TLS_AES_256_GCM_SHA384",           # TLS 1.3
    "TLS_CHACHA20_POLY1305_SHA256",     # TLS 1.3
    "ECDHE-ECDSA-AES256-GCM-SHA384",    # TLS 1.2
    "ECDHE-RSA-AES256-GCM-SHA384",      # TLS 1.2 fallback
]

CIPHERS_DEVTEST = [
    "TLS_AES_128_GCM_SHA256",           # TLS 1.3
    "TLS_AES_256_GCM_SHA384",           # TLS 1.3
    "ECDHE-ECDSA-AES128-GCM-SHA256",    # TLS 1.2
    "ECDHE-RSA-AES128-GCM-SHA256",      # TLS 1.2
]

CIPHERS_HIGHSEC = [
    "TLS_AES_256_GCM_SHA384",           # TLS 1.3 only
]


def create_ssl_context(
    profile: str = "prod",
    ca_bundle: Optional[str] = None,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    verify_hostname: bool = True,
) -> ssl.SSLContext:
    """
    Create an SSL context with profile-appropriate settings.

    Args:
        profile: Security profile (prod, devtest, highsec)
        ca_bundle: Path to CA bundle (default: system/certifi)
        client_cert: Path to client certificate (for mTLS)
        client_key: Path to client private key (for mTLS)
        verify_hostname: Enable hostname verification (default: True)

    Returns:
        Configured ssl.SSLContext

    Example:
        ctx = create_ssl_context(profile="prod")
        response = requests.get(url, verify=True)  # Uses system CA

        # Or with explicit context
        import urllib.request
        urllib.request.urlopen(url, context=ctx)
    """
    profile_enum = TlsProfile(profile)

    # Create context with appropriate protocol
    if profile_enum == TlsProfile.HIGHSEC:
        # TLS 1.3 only for highsec
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
        ciphers = CIPHERS_HIGHSEC
    else:
        # TLS 1.2+ for prod/devtest
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ciphers = CIPHERS_PROD if profile_enum == TlsProfile.PROD else CIPHERS_DEVTEST

    # Set cipher suites
    ctx.set_ciphers(":".join(ciphers))

    # Certificate verification
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = verify_hostname

    # Load CA bundle
    if ca_bundle:
        ctx.load_verify_locations(ca_bundle)
    else:
        # Use certifi bundle (cross-platform, up-to-date)
        ctx.load_verify_locations(certifi.where())

    # Client certificate (mTLS)
    if client_cert and client_key:
        ctx.load_cert_chain(client_cert, client_key)

    return ctx
```

---

## Database SSL Configuration

### Current: `build_database_url()`

The existing `build_database_url()` reads `POSTGRES_SSLMODE` from environment:

```python
from hyperi_pylib.database import build_database_url

# Current behaviour - reads ENV
# POSTGRES_SSLMODE=verify-full
db_url = build_database_url("postgresql")
# → postgresql://user:pass@host:5432/db?sslmode=verify-full
```

### Planned Enhancement

Auto-configure SSL based on profile:

```python
# Future API
from hyperi_pylib.database import build_database_url

# Auto-applies sslmode based on profile
db_url = build_database_url("postgresql", profile="prod")
# → postgresql://user:pass@host:5432/db?sslmode=verify-full&sslrootcert=/etc/ssl/...

# With explicit CA
db_url = build_database_url(
    "postgresql",
    profile="prod",
    sslrootcert="/path/to/ca.crt"
)
```

### Implementation Reference

```python
# Enhancement to hyperi_pylib/database/connection.py

# SSL mode by profile
SSLMODE_BY_PROFILE = {
    "prod": "verify-full",      # Verify cert and hostname
    "devtest": "require",       # Encrypt, but don't verify
    "highsec": "verify-full",   # Full verification required
}

def build_database_url(
    db_type: str,
    profile: str = "prod",
    sslrootcert: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Build database URL with profile-appropriate SSL settings.

    For prod/highsec:
    - sslmode=verify-full (verify certificate and hostname)
    - sslrootcert from config or system default

    For devtest:
    - sslmode=require (encrypted but no verification)
    """
    # ... existing logic ...

    # Add SSL params if not already specified
    if "sslmode" not in kwargs:
        kwargs["sslmode"] = SSLMODE_BY_PROFILE.get(profile, "verify-full")

    if profile in ("prod", "highsec") and sslrootcert:
        kwargs["sslrootcert"] = sslrootcert

    # ... build URL ...
```

### PostgreSQL SSL Verification

```python
# Direct psycopg2/asyncpg usage with profile settings
import ssl
from hyperi_pylib.tls import create_ssl_context

# Create SSL context for database
ctx = create_ssl_context(profile="prod")

# psycopg2
import psycopg2
conn = psycopg2.connect(
    host="db.example.com",
    sslmode="verify-full",
    sslrootcert="/path/to/ca.crt",
)

# asyncpg
import asyncpg
conn = await asyncpg.connect(
    host="db.example.com",
    ssl=ctx,  # Pass SSL context directly
)

# SQLAlchemy with SSL
from sqlalchemy import create_engine
engine = create_engine(
    "postgresql://user:pass@host/db",
    connect_args={
        "sslmode": "verify-full",
        "sslrootcert": "/path/to/ca.crt",
    }
)
```

---

## Kafka mTLS Configuration

### Current: `merge_config()`

The existing Kafka module supports SSL via `merge_config()`:

```python
from hyperi_pylib.kafka import merge_config, PRODUCER_DEFAULTS

config = merge_config(
    {
        "bootstrap.servers": "kafka:9093",
        "security.protocol": "SSL",
        "ssl.ca.location": "/path/to/ca.crt",
        "ssl.certificate.location": "/path/to/client.crt",
        "ssl.key.location": "/path/to/client.key",
    },
    PRODUCER_DEFAULTS,
)
```

### Planned Enhancement

Zero-config mTLS from settings:

```python
# Future API
from hyperi_pylib.kafka import KafkaProducer

# Auto-loads TLS config from settings.yaml or ENV
producer = KafkaProducer(
    bootstrap_servers=["kafka:9093"],
    profile="prod",  # Uses prod TLS settings
)
```

### Implementation Reference

```python
# Enhancement to hyperi_pylib/kafka/config.py

# Kafka SSL settings by profile
KAFKA_SSL_DEFAULTS = {
    "prod": {
        "security.protocol": "SSL",
        "ssl.endpoint.identification.algorithm": "https",  # Hostname verification
    },
    "devtest": {
        "security.protocol": "SSL",
        "ssl.endpoint.identification.algorithm": "",  # No hostname verification
    },
    "highsec": {
        "security.protocol": "SSL",
        "ssl.endpoint.identification.algorithm": "https",
        # Additional FIPS settings as needed
    },
}

def get_kafka_ssl_config(
    profile: str = "prod",
    ca_location: Optional[str] = None,
    cert_location: Optional[str] = None,
    key_location: Optional[str] = None,
) -> dict:
    """
    Get Kafka SSL configuration for profile.

    Args:
        profile: Security profile (prod, devtest, highsec)
        ca_location: Path to CA certificate
        cert_location: Path to client certificate (mTLS)
        key_location: Path to client key (mTLS)

    Returns:
        Dict of librdkafka SSL configuration

    Example:
        ssl_config = get_kafka_ssl_config(
            profile="prod",
            ca_location="/etc/kafka/ca.crt",
            cert_location="/etc/kafka/client.crt",
            key_location="/etc/kafka/client.key",
        )

        producer = KafkaProducer(
            bootstrap_servers=["kafka:9093"],
            **ssl_config,
        )
    """
    config = dict(KAFKA_SSL_DEFAULTS.get(profile, KAFKA_SSL_DEFAULTS["prod"]))

    if ca_location:
        config["ssl.ca.location"] = ca_location
    if cert_location:
        config["ssl.certificate.location"] = cert_location
    if key_location:
        config["ssl.key.location"] = key_location

    return config
```

### Manual Kafka mTLS Setup

```python
from confluent_kafka import Producer

# Production mTLS configuration
producer = Producer({
    "bootstrap.servers": "kafka:9093",
    "security.protocol": "SSL",

    # CA certificate (verify broker)
    "ssl.ca.location": "/etc/kafka/ca.crt",

    # Client certificate (mTLS authentication)
    "ssl.certificate.location": "/etc/kafka/client.crt",
    "ssl.key.location": "/etc/kafka/client.key",

    # Hostname verification (prod/highsec only)
    "ssl.endpoint.identification.algorithm": "https",
})
```

---

## HTTP Client Configuration

### requests with TLS

```python
import requests
from hyperi_pylib.tls import create_ssl_context

# Simple: use system CA (works for most cases)
response = requests.get("https://api.example.com", verify=True)

# Explicit CA bundle
response = requests.get(
    "https://api.example.com",
    verify="/path/to/ca-bundle.crt"
)

# Client certificate (mTLS)
response = requests.get(
    "https://api.example.com",
    cert=("/path/to/client.crt", "/path/to/client.key"),
    verify="/path/to/ca.crt",
)
```

### httpx with TLS

```python
import httpx
import ssl

# Create SSL context with profile settings
ctx = ssl.create_default_context()
ctx.minimum_version = ssl.TLSVersion.TLSv1_2
ctx.load_verify_locations("/path/to/ca.crt")

# Async client
async with httpx.AsyncClient(verify=ctx) as client:
    response = await client.get("https://api.example.com")

# mTLS
ctx.load_cert_chain("/path/to/client.crt", "/path/to/client.key")
async with httpx.AsyncClient(verify=ctx) as client:
    response = await client.get("https://api.example.com")
```

---

## Config Cascade

Settings can be provided via YAML config or environment variables:

### settings.yaml

```yaml
# settings.yaml
tls:
  profile: prod             # prod | devtest | highsec
  ca_bundle: auto           # auto = system/certifi default
  verify_hostname: true

database:
  postgresql:
    sslmode: verify-full    # Default for prod
    sslrootcert: auto       # auto = system CA bundle

kafka:
  security_protocol: SSL
  ssl_ca_location: /etc/kafka/ca.crt
  ssl_certificate_location: /etc/kafka/client.crt
  ssl_key_location: /etc/kafka/client.key
```

### Environment Variables

```bash
# TLS profile
HS_TLS_PROFILE=prod

# Database SSL
POSTGRES_SSLMODE=verify-full
POSTGRES_SSLROOTCERT=/path/to/ca.crt

# Kafka SSL
KAFKA_SSL_CA_LOCATION=/etc/kafka/ca.crt
KAFKA_SSL_CERTIFICATE_LOCATION=/etc/kafka/client.crt
KAFKA_SSL_KEY_LOCATION=/etc/kafka/client.key
```

---

## Certificate Generation

### Generate P-384 Certificate (prod profile)

```bash
# Private key
openssl ecparam -genkey -name secp384r1 -out server.key

# CSR
openssl req -new -key server.key -out server.csr \
    -subj "/CN=app.example.com/O=HyperI/C=AU"

# Self-signed (dev only)
openssl req -x509 -new -key server.key -out server.crt -days 365 \
    -subj "/CN=app.example.com/O=HyperI/C=AU"
```

### Generate P-256 Certificate (devtest profile)

```bash
# Private key
openssl ecparam -genkey -name prime256v1 -out server.key

# CSR
openssl req -new -key server.key -out server.csr \
    -subj "/CN=dev.local/O=HyperI/C=AU"

# Self-signed
openssl req -x509 -new -key server.key -out server.crt -days 365 \
    -subj "/CN=dev.local/O=HyperI/C=AU"
```

---

## Troubleshooting

### SSL Certificate Verify Failed

```python
# Error: ssl.SSLCertVerificationError: certificate verify failed
#
# Causes:
# 1. Missing CA bundle
# 2. Self-signed cert not in trust store
# 3. Certificate expired
# 4. Hostname mismatch

# Debug: check certificate
import ssl
import socket

hostname = "api.example.com"
ctx = ssl.create_default_context()

with socket.create_connection((hostname, 443)) as sock:
    with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
        cert = ssock.getpeercert()
        print(f"Subject: {cert['subject']}")
        print(f"Issuer: {cert['issuer']}")
        print(f"Expires: {cert['notAfter']}")
```

### Kafka SSL Handshake Failed

```python
# Error: SSL handshake failed
#
# Common causes:
# 1. Wrong protocol (check ssl vs sasl_ssl)
# 2. Missing client cert for mTLS
# 3. CA doesn't trust broker cert

# Debug: test connection
from confluent_kafka import Producer

producer = Producer({
    "bootstrap.servers": "kafka:9093",
    "security.protocol": "SSL",
    "ssl.ca.location": "/path/to/ca.crt",
    "debug": "security,broker",  # Enable debug logging
})
```

---

## References

- [PKI Standards](../ai/standards/common/PKI.md) - Full PKI/TLS standards
- [certifi](https://pypi.org/project/certifi/) - Mozilla CA bundle for Python
- [Python ssl module](https://docs.python.org/3/library/ssl.html)
- [librdkafka SSL configuration](https://github.com/confluentinc/librdkafka/blob/master/CONFIGURATION.md)
