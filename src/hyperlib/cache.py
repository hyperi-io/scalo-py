"""
HyperLib Smart Caching System
Multi-layer caching with retention management
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .logger import logger
from .resources import get_cache_resource


@dataclass
class CacheEntry:
    """Cache entry with metadata and retention info"""

    cache_key: str
    original_log_path: str  # Full Kafka log file
    reduced_log_path: str  # LogReducer output (.1%)
    tokenized_result_path: str  # Pre-tokenized LLM data
    created_at: datetime
    last_accessed: datetime
    retention_hours: float
    metadata: dict[str, Any]

    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        expiry_time = self.created_at + timedelta(hours=self.retention_hours)
        return datetime.now() > expiry_time

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["last_accessed"] = self.last_accessed.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        """Create from dictionary"""
        data = data.copy()
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["last_accessed"] = datetime.fromisoformat(data["last_accessed"])
        return cls(**data)


class LogPipelineCache:
    """
    Multi-layer caching system for log processing pipeline

    Caches:
    1. Original large log file (from Kafka)
    2. Reduced log file (LogReducer output, ~0.1%)
    3. Pre-tokenized LLM data (ready for immediate use)

    Features:
    - Retention period enforcement
    - Thread-safe concurrent access
    - Automatic cleanup of expired entries
    - Cache statistics and monitoring
    """

    def __init__(self, retention_hours: float = 24.0):
        """
        Initialize log pipeline cache

        Args:
            retention_hours: Default retention period for cache entries
        """
        self.retention_hours = retention_hours
        self.cache_resource = get_cache_resource()
        self.cache_index_file = "log_pipeline_cache.json"

        # Ensure cache directory structure exists
        cache_base = self.cache_resource.base_path
        for subdir in ["original", "reduced", "tokenized"]:
            (cache_base / subdir).mkdir(parents=True, exist_ok=True)

        logger.info(f"💾 LogPipelineCache initialized (retention: {retention_hours}h)")

    def cache_log_pipeline(
        self,
        original_log: Path,
        reduced_log: Path,
        tokenized_result: dict[str, Any],
        metadata: dict[str, Any | None] = None,
    ) -> CacheEntry:
        """
        Cache complete log processing pipeline

        Args:
            original_log: Full Kafka topic extract
            reduced_log: LogReducer output (.1% of original)
            tokenized_result: Pre-tokenized LLM input data
            metadata: Additional metadata to store

        Returns:
            CacheEntry with paths and metadata
        """

        # Generate cache key from original log hash
        cache_key = self._generate_cache_key(original_log)

        # Copy files to cache with organized structure
        cache_base = self.cache_resource.base_path

        # Cache original log
        original_cached = cache_base / "original" / f"{cache_key}_original.ndjson"
        if original_log.exists():
            import shutil

            shutil.copy2(original_log, original_cached)

        # Cache reduced log
        reduced_cached = cache_base / "reduced" / f"{cache_key}_reduced.ndjson"
        if reduced_log.exists():
            import shutil

            shutil.copy2(reduced_log, reduced_cached)

        # Cache tokenized result
        tokenized_cached = cache_base / "tokenized" / f"{cache_key}_tokenized.json"
        with open(tokenized_cached, "w") as f:
            json.dump(tokenized_result, f, indent=2)

        # Create cache entry
        cache_entry = CacheEntry(
            cache_key=cache_key,
            original_log_path=str(original_cached),
            reduced_log_path=str(reduced_cached),
            tokenized_result_path=str(tokenized_cached),
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            retention_hours=self.retention_hours,
            metadata=metadata or {},
        )

        # Update cache index with thread safety
        self._update_cache_index(cache_entry)

        logger.success(f"💾 Cached log pipeline: {cache_key}")
        logger.info(f"   Original: {original_cached.stat().st_size} bytes")
        logger.info(f"   Reduced: {reduced_cached.stat().st_size} bytes")
        logger.info(f"   Tokenized: {tokenized_cached.stat().st_size} bytes")

        return cache_entry

    def get_cached_pipeline(self, original_log: Path) -> CacheEntry | None:
        """
        Get cached pipeline for original log file

        Args:
            original_log: Original log file to check cache for

        Returns:
            CacheEntry if valid cache exists, None otherwise
        """

        cache_key = self._generate_cache_key(original_log)

        # Load cache index with thread safety
        cache_index = self._load_cache_index()

        if cache_key in cache_index:
            cache_entry = CacheEntry.from_dict(cache_index[cache_key])

            # Check if expired
            if cache_entry.is_expired():
                logger.warning(f"⏰ Cache expired: {cache_key}")
                self._remove_cache_entry(cache_key)
                return None

            # Check if files still exist
            if not all(
                Path(p).exists()
                for p in [
                    cache_entry.original_log_path,
                    cache_entry.reduced_log_path,
                    cache_entry.tokenized_result_path,
                ]
            ):
                logger.warning(f"📁 Cache files missing: {cache_key}")
                self._remove_cache_entry(cache_key)
                return None

            # Update last accessed time
            cache_entry.last_accessed = datetime.now()
            self._update_cache_index(cache_entry)

            logger.success(f"💾 Cache hit: {cache_key}")
            return cache_entry

        logger.info(f"💨 Cache miss: {cache_key}")
        return None

    def _generate_cache_key(self, log_file: Path) -> str:
        """Generate unique cache key for log file"""

        if not log_file.exists():
            # Use filename + timestamp for non-existent files
            content = f"{log_file.name}_{log_file.stat().st_mtime if log_file.exists() else time.time()}"
        else:
            # Use file content hash for existing files
            hasher = hashlib.sha256()
            with open(log_file, "rb") as f:
                # Read first 64KB for hash (efficient for large files)
                content_sample = f.read(65536)
                hasher.update(content_sample)
                # Add file size and mtime for uniqueness
                hasher.update(f"{log_file.stat().st_size}_{log_file.stat().st_mtime}".encode())

            return hasher.hexdigest()[:16]  # 16 char hex

        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _load_cache_index(self) -> dict[str, dict[str, Any]]:
        """Load cache index with thread safety"""

        try:
            with self.cache_resource.concurrent_file_access(self.cache_index_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        except Exception as e:
            logger.warning(f"⚠️ Cache index load failed: {e}")
            return {}

    def _update_cache_index(self, cache_entry: CacheEntry):
        """Update cache index with thread safety"""

        try:
            # Load current index
            cache_index = self._load_cache_index()

            # Update entry
            cache_index[cache_entry.cache_key] = cache_entry.to_dict()

            # Save with thread safety
            with self.cache_resource.concurrent_file_access(self.cache_index_file, "w") as f:
                json.dump(cache_index, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"❌ Cache index update failed: {e}")

    def _remove_cache_entry(self, cache_key: str):
        """Remove cache entry and files"""

        try:
            cache_index = self._load_cache_index()

            if cache_key in cache_index:
                entry_data = cache_index[cache_key]

                # Remove cache files
                for file_key in ["original_log_path", "reduced_log_path", "tokenized_result_path"]:
                    file_path = Path(entry_data[file_key])
                    file_path.unlink(missing_ok=True)

                # Remove from index
                del cache_index[cache_key]

                # Save updated index
                with self.cache_resource.concurrent_file_access(self.cache_index_file, "w") as f:
                    json.dump(cache_index, f, indent=2, default=str)

                logger.info(f"🗑️ Removed cache entry: {cache_key}")

        except Exception as e:
            logger.error(f"❌ Cache entry removal failed: {cache_key}: {e}")

    def cleanup_expired_entries(self):
        """Cleanup all expired cache entries"""

        cache_index = self._load_cache_index()
        expired_keys = []

        for cache_key, entry_data in cache_index.items():
            try:
                cache_entry = CacheEntry.from_dict(entry_data)
                if cache_entry.is_expired():
                    expired_keys.append(cache_key)
            except Exception as e:
                logger.warning(f"⚠️ Cache entry validation failed: {cache_key}: {e}")
                expired_keys.append(cache_key)  # Remove invalid entries

        logger.info(f"🧹 Cleaning up {len(expired_keys)} expired cache entries")

        for cache_key in expired_keys:
            self._remove_cache_entry(cache_key)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics"""

        cache_index = self._load_cache_index()

        total_size = 0
        expired_count = 0

        for entry_data in cache_index.values():
            try:
                cache_entry = CacheEntry.from_dict(entry_data)

                # Calculate total size
                for file_key in ["original_log_path", "reduced_log_path", "tokenized_result_path"]:
                    file_path = Path(entry_data[file_key])
                    if file_path.exists():
                        total_size += file_path.stat().st_size

                if cache_entry.is_expired():
                    expired_count += 1

            except Exception:
                expired_count += 1  # Count invalid entries as expired

        return {
            "total_entries": len(cache_index),
            "expired_entries": expired_count,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "cache_path": str(self.cache_resource.base_path),
        }


# Global cache instance
_log_cache = None


def get_log_pipeline_cache(retention_hours: float = 24.0) -> LogPipelineCache:
    """Get global log pipeline cache instance"""
    global _log_cache
    if _log_cache is None:
        _log_cache = LogPipelineCache(retention_hours)
    return _log_cache
