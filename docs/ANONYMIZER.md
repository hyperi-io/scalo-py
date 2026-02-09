# hyperi-pylib Anonymizer

PII detection and anonymization using Microsoft Presidio.

## Quick Start

```python
from hyperi_pylib.anonymizer import anonymize_text, scan_for_pii

# Anonymize text
text = "John's email is john@example.com and SSN is 123-45-6789"
clean = anonymize_text(text, preset="compliance")
# "John's email is <EMAIL_ADDRESS> and SSN is <US_SSN>"

# Scan for PII (returns detection results)
results = scan_for_pii(text, preset="standard")
for entity in results:
    print(f"{entity.entity_type}: {entity.text}")
```

## Installation

```bash
pip install hyperi-pylib[presidio]
```

## Presets

- **minimal** - Secrets only (API keys, tokens, passwords)
- **standard** - Common PII (email, phone, names) + secrets
- **compliance** - HIPAA/GDPR/PCI-DSS (SSN, credit cards, medical) + standard

## Strategies

- **REPLACE** - Replace with `<ENTITY_TYPE>` (default)
- **REDACT** - Replace with `***REDACTED***`
- **MASK** - Partial masking (e.g., `555-**-****`)
- **HASH** - SHA-256 hash (deterministic)
- **ENCRYPT** - AES encryption (reversible, needs key)

## Basic Usage

```python
from hyperi_pylib.anonymizer import Anonymizer, AnonymizationStrategy

# Create anonymizer
anonymizer = Anonymizer(
    preset="standard",
    strategy=AnonymizationStrategy.REPLACE
)

# Anonymize text
text = "Contact john.doe@company.com or call 555-1234"
result = anonymizer.anonymize(text)
# "Contact <EMAIL_ADDRESS> or call <PHONE_NUMBER>"

# Anonymize dict
data = {"name": "John Doe", "email": "john@example.com"}
clean = anonymizer.anonymize_dict(data)
# {"name": "<PERSON>", "email": "<EMAIL_ADDRESS>"}
```

## StreamingAnonymizer

Efficient processing for large datasets (millions of rows, GB+ files).

### Features

- Chunked processing (doesn't load entire dataset into memory)
- Result caching (same PII value → same anonymized value)
- Lazy evaluation (only processes when iterator consumed)
- DataFrame support (Polars lazy + eager, Pandas)

### ClickHouse Query (Large Result Set)

```python
from hyperi_pylib.anonymizer import StreamingAnonymizer
from clickhouse_driver import Client

client = Client('localhost')
anonymizer = StreamingAnonymizer(preset="compliance", cache_size=10000)

# Stream millions of rows efficiently
query = "SELECT user_id, email, phone, ssn FROM users"
for row in client.execute_iter(query):
    record = dict(zip(["user_id", "email", "phone", "ssn"], row))
    anonymized = anonymizer.anonymize_dict(record)
    target_db.insert(anonymized)
```

### Polars DataFrame (Lazy Evaluation)

```python
from hyperi_pylib.anonymizer import StreamingAnonymizer
import polars as pl

anonymizer = StreamingAnonymizer(preset="standard")

# Process large DataFrame efficiently (lazy + streaming)
df = pl.scan_csv("large_dataset.csv")  # Lazy scan
anonymized_df = anonymizer.anonymize_polars(df)
anonymized_df.sink_csv("anonymized.csv")  # Stream to output
```

### Kafka/Message Queue

```python
from hyperi_pylib.anonymizer import StreamingAnonymizer

anonymizer = StreamingAnonymizer(preset="compliance", cache_size=10000)

# Process messages
for message in kafka_consumer:
    data = json.loads(message.value)
    anonymized = anonymizer.anonymize_dict(data)
    kafka_producer.send("anonymized-topic", anonymized)
```

### Large Log File

```python
from hyperi_pylib.anonymizer import StreamingAnonymizer

anonymizer = StreamingAnonymizer(preset="standard")

# Process file line-by-line (memory efficient)
with open("large_log.txt") as f:
    for line in f:
        anonymized_line = anonymizer.anonymize(line)
        output_file.write(anonymized_line)
```

### Pandas DataFrame

```python
import pandas as pd
from hyperi_pylib.anonymizer import StreamingAnonymizer

anonymizer = StreamingAnonymizer(preset="standard")
df = pd.read_csv("data.csv")
anonymized = anonymizer.anonymize_pandas(df, columns=["email", "phone"])
```

### Cache Statistics

```python
anonymizer = StreamingAnonymizer(cache_size=10000)

# Process data...

stats = anonymizer.get_cache_stats()
print(f"Cache hit rate: {stats['hit_rate']:.1%}")
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

## Config File Scanning

```python
from hyperi_pylib.anonymizer import scan_file_for_secrets

# Scan for secrets in config files
results = scan_file_for_secrets(".env")
if results:
    print("WARNING: Secrets found!")
    for entity in results:
        print(f"  {entity.entity_type}: {entity.text}")
```

## Custom Entities

```python
from hyperi_pylib.anonymizer import Anonymizer

# Use specific entities only
anonymizer = Anonymizer(
    entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"],
    strategy=AnonymizationStrategy.REDACT
)
```

## Custom Replacements

```python
from hyperi_pylib.anonymizer import Anonymizer

# Custom replacement per entity type
anonymizer = Anonymizer(
    preset="standard",
    replacements={
        "EMAIL_ADDRESS": "user@example.com",
        "PHONE_NUMBER": "555-0000",
        "PERSON": "John Doe"
    }
)
```

## Performance

- **Regex filter** (logger.filters): <1ms per log message
- **Presidio** (anonymizer): 5-50ms per text chunk
- **Streaming** (large datasets): Constant memory usage, cache improves throughput

Use StreamingAnonymizer for:
- ClickHouse queries (millions of rows)
- Polars lazy evaluation (GB+ files)
- Kafka/RabbitMQ streams
- Large log files (JSONL, CSV)

Use logger filters for:
- Runtime log masking
- Fast regex patterns only
- Zero external dependencies
