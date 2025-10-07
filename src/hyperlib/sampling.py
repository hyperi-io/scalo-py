"""
HyperLib Log Sampling with Token Constraints
Random sampling that fits within LLM token limits with incremental adjustment
Includes container resource management for temporary file handling
"""

import json
import os
import random
import shutil
import threading
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    from filelock import FileLock

    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False

from .logger import logger

# ============================================================================
# Container Resource Management (previously resources.py)
# ============================================================================


class ContainerResource:
    """
    Abstract container resource management with thread safety and auto-cleanup

    Handles:
    - READ-ONLY: /container/app/config/* (never writes)
    - PERSISTENT: /container/app/data/* (thread-safe concurrent access)
    - EPHEMERAL: /container/app/tmp/* (unique workspaces, auto-cleanup)
    - CACHE: /container/app/data/*/cache/* (retention management)
    """

    def __init__(self, resource_type: str):
        """
        Initialize container resource manager

        Args:
            resource_type: 'config', 'data', 'tmp', 'cache'
        """
        self.resource_type = resource_type
        self.base_path = self._resolve_container_path(resource_type)
        self._lock = threading.RLock()  # Re-entrant lock for nested calls
        self._cleanup_registry = []  # Track resources for cleanup
        self._thread_local = threading.local()  # Thread-local storage

        logger.debug(f"🏗️ ContainerResource initialized: {resource_type} → {self.base_path}")

    def _resolve_container_path(self, resource_type: str) -> Path:
        """Resolve container path for resource type"""

        # Detect container root (same logic as config)
        current_file = Path(__file__)
        if "/src/hyperlib/" in str(current_file):
            # Development: use container simulation
            project_root = current_file.parent.parent.parent
            container_root = project_root / "container"
        else:
            # Production: use actual container paths
            container_root = Path("/")

        # Map resource types to container paths
        path_mapping = {
            "config": container_root / "app" / "config" / "dfe_ai",
            "external": container_root / "app" / "config" / "external",
            "data": container_root / "app" / "data" / "dfe_ai",
            "tmp": container_root / "app" / "tmp" / "dfe_ai",
            "cache": container_root / "app" / "data" / "dfe_ai" / "cache",
            "logs": container_root / "var" / "log" / "dfe_ai",
        }

        if resource_type not in path_mapping:
            raise ValueError(f"Unknown resource type: {resource_type}")

        return path_mapping[resource_type]

    @contextmanager
    def get_unique_workspace(self, prefix: str = "workspace") -> Generator[Path, None, None]:
        """
        Get unique workspace with automatic cleanup

        Returns unique directory: /container/app/tmp/dfe_ai/working/{prefix}_{PID}_{TID}_{UUID}/
        Automatically cleaned up on exit
        """

        # Create unique workspace identifier
        pid = os.getpid()
        tid = threading.get_ident()
        unique_id = str(uuid.uuid4())[:8]

        workspace_name = f"{prefix}_{pid}_{tid}_{unique_id}"
        workspace_path = self.base_path / "working" / workspace_name

        try:
            # Create workspace with proper permissions
            workspace_path.mkdir(parents=True, exist_ok=True)

            # Register for cleanup
            with self._lock:
                self._cleanup_registry.append(workspace_path)

            logger.debug(f"📁 Created unique workspace: {workspace_path}")

            yield workspace_path

        finally:
            # Automatic cleanup (C-style memory management)
            try:
                if workspace_path.exists():
                    shutil.rmtree(workspace_path)
                    logger.debug(f"🧹 Cleaned up workspace: {workspace_path}")

                # Remove from cleanup registry
                with self._lock:
                    if workspace_path in self._cleanup_registry:
                        self._cleanup_registry.remove(workspace_path)

            except Exception as e:
                logger.warning(f"⚠️ Workspace cleanup failed: {workspace_path}: {e}")

    @contextmanager
    def concurrent_file_access(
        self, file_path: str, mode: str = "r", encoding: str = "utf-8", timeout: float = 30.0
    ) -> Generator:
        """
        Thread-safe file access with locking for concurrent operations

        Perfect for dfe_knowledge.yaml concurrent writes

        Args:
            file_path: Relative path from resource base
            mode: File open mode ('r', 'w', 'a')
            encoding: File encoding
            timeout: Lock timeout in seconds
        """

        full_path = self.base_path / file_path
        lock_path = full_path.with_suffix(f"{full_path.suffix}.lock")

        # Ensure parent directory exists for writes
        if "w" in mode or "a" in mode:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        # Use filelock for cross-process safety, threading.Lock for fallback
        if FILELOCK_AVAILABLE and ("w" in mode or "a" in mode):
            # Use file-based locking for writes (cross-process safe)
            file_lock = FileLock(str(lock_path), timeout=timeout)

            try:
                with file_lock:
                    logger.debug(f"🔒 Acquired file lock: {full_path}")
                    with open(full_path, mode, encoding=encoding) as f:
                        yield f
                    logger.debug(f"🔓 Released file lock: {full_path}")

            except Exception as e:
                logger.error(f"❌ Concurrent file access failed: {full_path}: {e}")
                raise

        else:
            # Use threading lock for reads or when filelock unavailable
            with self._lock:
                try:
                    with open(full_path, mode, encoding=encoding) as f:
                        yield f

                except Exception as e:
                    logger.error(f"❌ File access failed: {full_path}: {e}")
                    raise

    def cleanup_all(self):
        """Manual cleanup of all registered resources"""
        with self._lock:
            for resource_path in self._cleanup_registry[:]:  # Copy list to avoid modification during iteration
                try:
                    if resource_path.exists():
                        shutil.rmtree(resource_path)
                        logger.debug(f"🧹 Manual cleanup: {resource_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Manual cleanup failed: {resource_path}: {e}")

            self._cleanup_registry.clear()

    def __del__(self):
        """Destructor cleanup (Python garbage collection)"""
        try:
            self.cleanup_all()
        except:
            pass  # Don't raise exceptions in destructor


def get_tmp_resource() -> ContainerResource:
    """Get EPHEMERAL temp resource manager with auto-cleanup"""
    return ContainerResource("tmp")


# ============================================================================
# Log Sampling (original sampling.py functionality)
# ============================================================================


@dataclass
class SamplingResult:
    """Result of log sampling operation"""

    sampled_file: Path
    original_count: int
    sampled_count: int
    estimated_tokens: int
    target_tokens: int
    sampling_ratio: float
    success: bool


class LogSampler:
    """
    Token-constrained random log sampling

    Takes large log files and creates smaller samples that fit within token limits
    Uses incremental adjustment to optimize token usage
    """

    def __init__(self):
        self.tmp_resource = get_tmp_resource()

        # Token estimation fallbacks if tiktoken unavailable
        self.char_to_token_ratio = 3.5  # Approximate chars per token

        logger.info("📊 LogSampler initialized with token constraints")

    def sample_logs_for_token_limit(
        self,
        source_file: Path,
        target_tokens: int,
        model_name: str = "auto",
        seed: int | None = None,
        format_hint: str = "json",
    ) -> SamplingResult:
        """
        Sample logs to fit within token count with incremental optimization

        Args:
            source_file: Large log file to sample from
            target_tokens: Maximum tokens for result
            model_name: Model for accurate token counting
            seed: Random seed for reproducible sampling
            format_hint: Log format ("json", "text", "syslog")

        Returns:
            SamplingResult with sampled file and statistics
        """

        if seed is not None:
            random.seed(seed)

        logger.info(f"📊 Sampling {source_file.name} for {target_tokens} tokens")
        logger.info(f"   Model: {model_name}")
        logger.info(f"   Format: {format_hint}")

        # Load all log records
        original_logs = self._load_log_records(source_file, format_hint)
        if not original_logs:
            return SamplingResult(
                sampled_file=source_file,
                original_count=0,
                sampled_count=0,
                estimated_tokens=0,
                target_tokens=target_tokens,
                sampling_ratio=0.0,
                success=False,
            )

        logger.info(f"   Loaded: {len(original_logs)} original records")

        # Get token encoder for model
        token_encoder = self._get_token_encoder(model_name)

        # Incremental sampling to fit token limit
        sampled_logs, actual_tokens = self._incremental_sample(original_logs, target_tokens, token_encoder)

        # Save sampled logs to unique temp file
        with self.tmp_resource.get_unique_workspace("log_sampling") as workspace:
            sampled_file = workspace / f"sampled_{source_file.stem}_{len(sampled_logs)}.ndjson"

            with open(sampled_file, "w") as f:
                for log_record in sampled_logs:
                    if format_hint == "json":
                        json.dump(log_record, f)
                        f.write("\\n")
                    else:
                        f.write(str(log_record) + "\\n")

            # Copy to persistent location for return
            persistent_result = self.tmp_resource.base_path / "working" / sampled_file.name
            persistent_result.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(sampled_file, persistent_result)

        result = SamplingResult(
            sampled_file=persistent_result,
            original_count=len(original_logs),
            sampled_count=len(sampled_logs),
            estimated_tokens=actual_tokens,
            target_tokens=target_tokens,
            sampling_ratio=len(sampled_logs) / len(original_logs),
            success=actual_tokens <= target_tokens,
        )

        logger.success("✅ Log sampling complete")
        logger.info(f"   {result.original_count} → {result.sampled_count} records ({result.sampling_ratio:.1%})")
        logger.info(
            f"   {result.estimated_tokens}/{result.target_tokens} tokens ({result.estimated_tokens/result.target_tokens:.1%})"
        )

        return result

    def _load_log_records(self, log_file: Path, format_hint: str) -> list[dict[str, Any]]:
        """Load log records from file based on format"""

        records = []

        try:
            with open(log_file) as f:
                if format_hint == "json":
                    # NDJSON format
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError as e:
                                logger.warning(f"⚠️ JSON parse error line {line_num}: {e}")
                                continue
                else:
                    # Text/syslog format - convert to dict
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            records.append({"message": line, "line_number": line_num})

        except Exception as e:
            logger.error(f"❌ Failed to load log records: {e}")

        return records

    def _get_token_encoder(self, model_name: str):
        """Get token encoder for model"""

        if not TIKTOKEN_AVAILABLE:
            logger.warning("⚠️ tiktoken not available, using character estimation")
            return None

        try:
            # Get encoding for model (approximate when auto)
            if model_name != "auto" and ("gpt-4" in model_name or "gpt-5" in model_name):
                encoding = tiktoken.encoding_for_model("gpt-4")
            elif model_name != "auto" and "" in model_name or model_name != "auto" and "gemini" in model_name:
                encoding = tiktoken.encoding_for_model("gpt-4")  # Use GPT-4 as approximation
            else:
                encoding = tiktoken.get_encoding("cl100k_base")  # Default

            return encoding

        except Exception as e:
            logger.warning(f"⚠️ Token encoder setup failed: {e}")
            return None

    def _count_tokens(self, text: str, encoder) -> int:
        """Count tokens in text"""

        if encoder and TIKTOKEN_AVAILABLE:
            try:
                return len(encoder.encode(text))
            except Exception as e:
                logger.warning(f"⚠️ Token counting failed: {e}")

        # Fallback to character estimation
        return int(len(text) / self.char_to_token_ratio)

    def _incremental_sample(
        self, original_logs: list[dict[str, Any]], target_tokens: int, token_encoder
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Incrementally sample logs to fit token limit

        Uses binary search approach to find optimal sample size
        """

        if not original_logs:
            return [], 0

        # Start with initial estimate
        estimated_sample_size = int(len(original_logs) * 0.1)  # Start with 10%

        # Binary search for optimal sample size
        min_size = 1
        max_size = len(original_logs)
        best_sample = []
        best_tokens = 0

        attempts = 0
        max_attempts = 10  # Limit iterations

        while min_size <= max_size and attempts < max_attempts:
            attempts += 1
            current_size = min(estimated_sample_size, len(original_logs))

            # Random sample of current size
            sample = random.sample(original_logs, current_size)

            # Calculate tokens for sample
            sample_text = ""
            for record in sample:
                if isinstance(record, dict):
                    sample_text += json.dumps(record) + "\\n"
                else:
                    sample_text += str(record) + "\\n"

            sample_tokens = self._count_tokens(sample_text, token_encoder)

            logger.debug(f"   Attempt {attempts}: {current_size} records = {sample_tokens} tokens")

            if sample_tokens <= target_tokens:
                # This sample fits - try larger
                best_sample = sample
                best_tokens = sample_tokens
                min_size = current_size + 1
                estimated_sample_size = min(int(current_size * 1.2), max_size)
            else:
                # Too big - try smaller
                max_size = current_size - 1
                estimated_sample_size = int(current_size * 0.8)

        if not best_sample and original_logs:
            # Fallback: use single record if nothing fits
            best_sample = [original_logs[0]]
            best_tokens = self._count_tokens(json.dumps(original_logs[0]), token_encoder)

        logger.info(f"   Incremental sampling: {attempts} attempts to optimize fit")

        return best_sample, best_tokens

    def _update_cache_index(self, cache_entry):
        """This method is defined in LogPipelineCache, not needed here"""
        pass


# Factory function
def get_log_sampler() -> LogSampler:
    """Get log sampler instance"""
    return LogSampler()
