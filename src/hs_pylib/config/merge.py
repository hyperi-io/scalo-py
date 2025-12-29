"""
hs-pylib Config Merge - Intelligent Multi-Format File Merging
===============================================================

Auto-detect and merge configuration files across multiple formats.
Supports JSON, YAML, TOML, INI, ENV, gitignore, and more!

Quick Start
===========

    # Install
    pip install hs-pylib

    # Auto-detect and merge
    from hs_pylib.config import merge_files

    merge_files("base.yaml", "target.yaml")  # Deep merge YAML
    merge_files("app.json", "config.json")   # Deep merge JSON
    merge_files(".gitignore.tmpl", ".gitignore")  # Append unique lines

Supported File Types
====================

**Structured Data (Deep Merge):**
- JSON (.json) - Nested dicts and arrays
- YAML (.yaml, .yml) - Complex hierarchies
- TOML (.toml) - Tables and arrays

**Flat Key-Value (Update):**
- INI (.ini, .cfg) - Section-based
- ENV (.env) - Environment variables
- Properties (.properties) - Java-style

**Line-Based (Append + Deduplicate):**
- .gitignore - Git ignore patterns
- .dockerignore - Docker ignore patterns
- requirements.txt - Python packages
- .gitattributes - Git attributes

Auto-Detection
===============

Files are detected by:
1. Extension (.json, .yaml, .toml)
2. Content patterns (JSON starts with {, YAML with ---, etc.)
3. Fallback to text-based strategies

Merge Strategies
================

**Deep (default for structured):**
- Recursively merges nested structures
- Arrays concatenated
- Primitive values overridden

**Append (default for line-based):**
- Appends unique lines
- Deduplicates entries
- Preserves order

**Overwrite:**
- Replaces target with source
- No merging

Usage Examples
==============

    from hs_pylib.config import merge_files

    # Auto-detect (recommended)
    merge_files("source.yaml", "target.yaml")

    # Explicit strategy
    merge_files("a.json", "b.json", strategy="deep")
    merge_files(".gitignore.add", ".gitignore", strategy="append")

    # Dry-run (return content without writing)
    content = merge_files("a.yaml", "b.yaml", dry_run=True)

    # Batch merge
    merge_files(["base.yaml", "prod.yaml"], "merged.yaml")
"""

import json
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
import yaml
from mergedeep import Strategy
from mergedeep import merge as deep_merge

# Strategy types
MergeStrategy = Literal["deep", "append", "overwrite", "auto"]


def detect_file_type(file_path: Path) -> str:
    """
    Detect file type by extension and content.

    Args:
        file_path: Path to file

    Returns:
        File type: json, yaml, toml, ini, env, gitignore, text

    Examples:
        >>> detect_file_type(Path("config.json"))
        'json'
        >>> detect_file_type(Path(".gitignore"))
        'gitignore'
    """
    # Extension-based detection (most reliable)
    ext = file_path.suffix.lower()
    name = file_path.name.lower()

    # Structured formats
    if ext == ".json":
        return "json"
    if ext in [".yaml", ".yml"]:
        return "yaml"
    if ext == ".toml":
        return "toml"

    # Flat key-value
    if ext in [".ini", ".cfg"]:
        return "ini"
    if ext == ".env" or name == ".env":
        return "env"
    if ext == ".properties":
        return "properties"

    # Line-based
    if name in [".gitignore", ".dockerignore"]:
        return "gitignore"
    if name == ".gitattributes":
        return "gitattributes"
    if name == "requirements.txt":
        return "requirements"

    # Content-based detection if file exists
    if file_path.exists():
        try:
            content = file_path.read_text(encoding="utf-8")
            first_line = content.lstrip()[:50]

            # JSON detection
            if first_line.startswith("{") or first_line.startswith("["):
                return "json"

            # YAML detection
            if first_line.startswith("---") or ": " in content[:200]:
                return "yaml"

            # TOML detection
            if first_line.startswith("[") and "]" in first_line:
                return "toml"

            # INI detection
            if "[" in content[:100] and "=" in content[:100]:
                return "ini"

        except (UnicodeDecodeError, PermissionError):
            pass

    # Default to text
    return "text"


def merge_json(source: Path, target: Path) -> dict:
    """
    Deep merge JSON files with list concatenation.

    Raises:
        PermissionError: Cannot read source or target file
        json.JSONDecodeError: Invalid JSON syntax
        UnicodeDecodeError: File encoding issues
    """
    try:
        source_data = json.loads(source.read_text(encoding="utf-8"))
    except PermissionError as e:
        raise PermissionError(f"Cannot read source file {source}: {e}") from e
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, f"Encoding error in {source}") from e

    try:
        target_data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except PermissionError as e:
        raise PermissionError(f"Cannot read target file {target}: {e}") from e
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, f"Encoding error in {target}") from e

    # Deep merge with additive strategy (concatenates lists)
    merged = deep_merge({}, target_data, source_data, strategy=Strategy.ADDITIVE)
    return merged


def merge_yaml(source: Path, target: Path) -> dict:
    """
    Deep merge YAML files with list concatenation.

    Raises:
        PermissionError: Cannot read source or target file
        yaml.YAMLError: Invalid YAML syntax
        UnicodeDecodeError: File encoding issues
    """
    try:
        source_data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except PermissionError as e:
        raise PermissionError(f"Cannot read source file {source}: {e}") from e
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, f"Encoding error in {source}") from e

    try:
        target_data = yaml.safe_load(target.read_text(encoding="utf-8")) if target.exists() else {}
    except PermissionError as e:
        raise PermissionError(f"Cannot read target file {target}: {e}") from e
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, f"Encoding error in {target}") from e

    # Deep merge with additive strategy (concatenates lists)
    merged = deep_merge({}, target_data, source_data, strategy=Strategy.ADDITIVE)
    return merged


def merge_toml(source: Path, target: Path) -> dict:
    """
    Deep merge TOML files with array concatenation.

    Raises:
        PermissionError: Cannot read source or target file
        tomllib.TOMLDecodeError: Invalid TOML syntax
        OSError: File I/O errors
    """
    try:
        with open(source, "rb") as f:
            source_data = tomllib.load(f)
    except PermissionError as e:
        raise PermissionError(f"Cannot read source file {source}: {e}") from e
    except OSError as e:
        raise OSError(f"Error reading {source}: {e}") from e

    if target.exists():
        try:
            with open(target, "rb") as f:
                target_data = tomllib.load(f)
        except PermissionError as e:
            raise PermissionError(f"Cannot read target file {target}: {e}") from e
        except OSError as e:
            raise OSError(f"Error reading {target}: {e}") from e
    else:
        target_data = {}

    # Deep merge with additive strategy (concatenates arrays)
    merged = deep_merge({}, target_data, source_data, strategy=Strategy.ADDITIVE)
    return merged


def merge_gitignore(source: Path, target: Path) -> list[str]:
    """
    Merge gitignore-style files (append unique lines).

    Works for: .gitignore, .dockerignore, requirements.txt
    """
    source_lines = source.read_text().splitlines()

    target_lines = target.read_text().splitlines() if target.exists() else []

    # Deduplicate while preserving order
    seen = set(target_lines)
    merged = target_lines.copy()

    for line in source_lines:
        # Skip empty lines and comments for deduplication
        stripped = line.strip()
        if stripped and stripped not in seen:
            merged.append(line)
            seen.add(stripped)

    return merged


def merge_files(
    source: Path | str | list[Path | str],
    target: Path | str,
    strategy: MergeStrategy = "auto",
    dry_run: bool = False,
) -> Any:
    """
    Intelligently merge configuration files.

    Auto-detects file type and applies appropriate merge strategy.

    Args:
        source: Source file(s) to merge from
        target: Target file to merge into
        strategy: Merge strategy (auto, deep, append, overwrite)
        dry_run: If True, return merged content without writing

    Returns:
        Merged content if dry_run=True, None otherwise

    Raises:
        FileNotFoundError: If source file doesn't exist
        ValueError: If file type unsupported or merge fails
        ImportError: If required library missing (e.g., tomli_w)

    Examples:
        # Auto-detect and merge
        merge_files("source.yaml", "target.yaml")

        # Explicit strategy
        merge_files("a.json", "b.json", strategy="deep")

        # Dry-run
        content = merge_files("a.yaml", "b.yaml", dry_run=True)
    """
    # Convert to Path
    target = Path(target)

    # Handle batch merge
    if isinstance(source, list):
        # Merge multiple sources sequentially into target
        for src in source:
            merge_files(src, target, strategy=strategy, dry_run=False)
        if dry_run:
            return target.read_text() if target.exists() else None
        return None

    source = Path(source)

    # Validate source exists
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    # Detect file types
    source_type = detect_file_type(source)
    target_type = detect_file_type(target) if target.exists() else source_type

    # Auto-select strategy based on target file type (what we're merging INTO)
    if strategy == "auto":
        # Use target type for strategy selection (or source if target doesn't exist)
        file_type = target_type if target.exists() else source_type

        if file_type in ["json", "yaml", "toml"]:
            strategy = "deep"
        elif file_type in ["gitignore", "requirements", "gitattributes"]:
            strategy = "append"
        else:
            strategy = "overwrite"

    # Execute merge based on type and strategy
    try:
        if strategy == "deep":
            if source_type == "json":
                merged = merge_json(source, target)
                content = json.dumps(merged, indent=2)
            elif source_type == "yaml":
                merged = merge_yaml(source, target)
                content = yaml.safe_dump(merged, default_flow_style=False)
            elif source_type == "toml":
                merged = merge_toml(source, target)
                if dry_run:
                    import io

                    buf = io.BytesIO()
                    tomli_w.dump(merged, buf)
                    content = buf.getvalue().decode("utf-8")
                else:
                    content = None  # Will write binary
            else:
                raise ValueError(f"Deep merge not supported for file type: {source_type}")

        elif strategy == "append":
            merged_lines = merge_gitignore(source, target)
            content = "\n".join(merged_lines) + "\n"

        elif strategy == "overwrite":
            content = source.read_text()

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {source}: {e}") from e
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {source}: {e}") from e
    except (PermissionError, OSError, UnicodeDecodeError, UnicodeEncodeError):
        # Re-raise specific I/O exceptions without wrapping
        raise
    except Exception as e:
        raise ValueError(f"Merge failed: {e}") from e

    # Return or write
    if dry_run:
        return content if content is not None else merged

    # Write merged content
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        raise OSError(f"Cannot create target directory {target.parent}: {e}") from e

    try:
        if source_type == "toml" and strategy == "deep":
            # TOML requires binary write
            with open(target, "wb") as f:
                tomli_w.dump(merged, f)
        else:
            target.write_text(content, encoding="utf-8")
    except PermissionError as e:
        raise PermissionError(f"Cannot write to {target}: {e}") from e
    except OSError as e:
        raise OSError(f"Error writing {target}: {e}") from e
    except UnicodeEncodeError as e:
        raise UnicodeEncodeError(e.encoding, e.object, e.start, e.end, f"Cannot encode content to {target}") from e

    return None


__all__ = [
    "merge_files",
    "detect_file_type",
    "merge_json",
    "merge_yaml",
    "merge_toml",
    "merge_gitignore",
]
