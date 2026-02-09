"""
Streaming anonymizer for efficient processing of large data streams.

Optimized for:
- Large database result sets (ClickHouse, PostgreSQL, etc.)
- Data processing frameworks (Polars, Pandas, Dask)
- Message queues (Kafka, RabbitMQ, Redis Streams)
- Large files (GB+ log files, CSVs, JSON Lines)
- Real-time data pipelines

Uses chunked processing and caching to minimize overhead.
"""

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .anonymizer import AnonymizationStrategy, Anonymizer

# Optional imports for data frame support
if TYPE_CHECKING:
    import pandas as pd
    import polars as pl


class StreamingAnonymizer:
    """
    Efficient anonymizer for large datasets (millions of rows, GB+ files).

    Optimized for:
    - ClickHouse/PostgreSQL queries (millions of rows)
    - Polars lazy evaluation (GB+ CSV/Parquet)
    - Kafka/RabbitMQ streams
    - Large log files (JSONL, CSV)

    Features:
    - LRU caching (same PII → same anonymized value)
    - Lazy evaluation (only processes when consumed)
    - Memory efficient (doesn't load entire dataset)

    See docs/ANONYMIZER.md for examples.
    """

    def __init__(
        self,
        preset: str = "standard",
        entities: list[str] | None = None,
        strategy: AnonymizationStrategy = AnonymizationStrategy.REPLACE,
        replacements: dict[str, str] | None = None,
        language: str = "en",
        cache_results: bool = True,
        cache_size: int = 10000,
    ):
        """
        Initialize streaming anonymizer.

        Args:
            preset: Preset entity group ("minimal", "standard", "compliance")
            entities: Override with custom entity list
            strategy: How to anonymize (REPLACE, REDACT, MASK, HASH)
            replacements: Custom replacement per entity type
            language: Language for analysis
            cache_results: Enable result caching (recommended for streams with repeated values)
            cache_size: Max cache size (default 10000, LRU eviction)
        """
        self.anonymizer = Anonymizer(
            preset=preset,
            entities=entities,
            strategy=strategy,
            replacements=replacements,
            language=language,
        )

        self.cache_results = cache_results
        self.cache_size = cache_size

        # LRU cache for anonymized values (same input → same output)
        self._cache: dict[str, str] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def anonymize(self, text: str) -> str:
        """
        Anonymize text with caching.

        Args:
            text: Text to anonymize

        Returns:
            Anonymized text
        """
        if not text or not isinstance(text, str):
            return text

        # Check cache first
        if self.cache_results and text in self._cache:
            self._cache_hits += 1
            return self._cache[text]

        # Cache miss - anonymize
        self._cache_misses += 1
        result = self.anonymizer.anonymize(text)

        # Update cache (LRU eviction if full)
        if self.cache_results:
            if len(self._cache) >= self.cache_size:
                # Evict oldest entry (simple FIFO, could be improved to true LRU)
                self._cache.pop(next(iter(self._cache)))
            self._cache[text] = result

        return result

    def anonymize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Anonymize dictionary (field-by-field for better caching).

        This processes each string field independently, allowing better
        cache hit rates for repeated field values.

        Args:
            data: Dictionary to anonymize

        Returns:
            Anonymized dictionary
        """
        if not data:
            return data

        return self._anonymize_dict_recursive(data)

    def _anonymize_dict_recursive(self, data: Any) -> Any:
        """Recursively anonymize dictionary fields."""
        if isinstance(data, dict):
            return {key: self._anonymize_dict_recursive(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._anonymize_dict_recursive(item) for item in data]
        elif isinstance(data, str):
            return self.anonymize(data)
        else:
            return data

    def stream_anonymize_lines(self, lines: Iterator[str]) -> Iterator[str]:
        """
        Stream-process lines of text.

        Args:
            lines: Iterator of text lines (e.g., file object)

        Yields:
            Anonymized lines

        Example:
            >>> with open("large_file.txt") as f:
            ...     for line in anonymizer.stream_anonymize_lines(f):
            ...         output.write(line)
        """
        for line in lines:
            yield self.anonymize(line)

    def stream_anonymize_json_lines(self, lines: Iterator[str]) -> Iterator[str]:
        """
        Stream-process JSON lines (JSONL format).

        Args:
            lines: Iterator of JSON-encoded strings

        Yields:
            Anonymized JSON strings

        Example:
            >>> with open("events.jsonl") as f:
            ...     for json_line in anonymizer.stream_anonymize_json_lines(f):
            ...         kafka_producer.send(json_line)
        """
        for line in lines:
            try:
                data = json.loads(line)
                anonymized = self.anonymize_dict(data)
                yield json.dumps(anonymized)
            except json.JSONDecodeError:
                # Pass through invalid JSON unchanged
                yield line

    def stream_anonymize_dicts(self, records: Iterator[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """
        Stream-process dictionaries.

        Args:
            records: Iterator of dictionaries

        Yields:
            Anonymized dictionaries

        Example:
            >>> records = database.stream_records()
            >>> for record in anonymizer.stream_anonymize_dicts(records):
            ...     kafka_producer.send("anonymized", record)
        """
        for record in records:
            yield self.anonymize_dict(record)

    def get_cache_stats(self) -> dict[str, int]:
        """
        Get cache performance statistics.

        Returns:
            Dict with hits, misses, size, and hit rate

        Example:
            >>> stats = anonymizer.get_cache_stats()
            >>> print(f"Cache hit rate: {stats['hit_rate']:.1%}")
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0

        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._cache),
            "max_size": self.cache_size,
            "hit_rate": hit_rate,
        }

    def clear_cache(self):
        """Clear the result cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    # DataFrame support methods

    def anonymize_polars(
        self, df: "pl.LazyFrame | pl.DataFrame", columns: list[str] | None = None
    ) -> "pl.LazyFrame | pl.DataFrame":
        """
        Anonymize Polars DataFrame efficiently.

        Works with both eager and lazy DataFrames. For large datasets,
        use lazy frames (pl.scan_csv, pl.scan_parquet) for streaming processing.

        Args:
            df: Polars DataFrame or LazyFrame
            columns: List of columns to anonymize (None = all string columns)

        Returns:
            Anonymized DataFrame (same type as input)

        Example:
            >>> import polars as pl
            >>> from hyperi_pylib.anonymizer import StreamingAnonymizer
            >>>
            >>> # Lazy (streaming, memory-efficient)
            >>> anonymizer = StreamingAnonymizer(preset="compliance")
            >>> df = pl.scan_csv("large_file.csv")
            >>> anonymized = anonymizer.anonymize_polars(df)
            >>> anonymized.sink_csv("output.csv")  # Stream to disk
            >>>
            >>> # Eager (in-memory)
            >>> df = pl.read_csv("small_file.csv")
            >>> anonymized = anonymizer.anonymize_polars(df)
        """
        try:
            import polars as pl
        except ImportError:
            raise ImportError("Polars not installed. Install with: pip install polars")

        is_lazy = isinstance(df, pl.LazyFrame)

        # Convert to lazy if needed (for uniform processing)
        lf = df.lazy() if not is_lazy else df

        # Determine columns to anonymize
        if columns is None:
            # Anonymize all string columns
            columns = []
            for col, dtype in zip(lf.columns, lf.dtypes, strict=False):
                if dtype == pl.Utf8:
                    columns.append(col)

        # Apply anonymization to each column
        for col in columns:
            lf = lf.with_columns(
                pl.col(col).map_elements(lambda x: self.anonymize(x) if isinstance(x, str) else x, return_dtype=pl.Utf8)
            )

        # Return same type as input
        return lf if is_lazy else lf.collect()

    def anonymize_pandas(
        self, df: "pd.DataFrame", columns: list[str] | None = None, inplace: bool = False
    ) -> "pd.DataFrame":
        """
        Anonymize Pandas DataFrame.

        Args:
            df: Pandas DataFrame
            columns: List of columns to anonymize (None = all object/string columns)
            inplace: Modify DataFrame in place (default False)

        Returns:
            Anonymized DataFrame

        Example:
            >>> import pandas as pd
            >>> from hyperi_pylib.anonymizer import StreamingAnonymizer
            >>>
            >>> anonymizer = StreamingAnonymizer(preset="standard")
            >>> df = pd.read_csv("data.csv")
            >>> anonymized = anonymizer.anonymize_pandas(df, columns=["email", "phone"])
        """
        try:
            import pandas as pd  # noqa: F401, unused-import
        except ImportError:
            raise ImportError("Pandas not installed. Install with: pip install pandas")

        # Determine columns to anonymize
        if columns is None:
            # Anonymize all object (string) columns
            columns = [col for col in df.columns if df[col].dtype == "object"]

        # Create copy if not inplace
        result = df if inplace else df.copy()

        # Apply anonymization to each column
        for col in columns:
            result[col] = result[col].apply(lambda x: self.anonymize(x) if isinstance(x, str) else x)

        return result
