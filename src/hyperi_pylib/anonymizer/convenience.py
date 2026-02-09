"""
Convenience functions for quick anonymization tasks.
"""

from pathlib import Path
from typing import Any

from .anonymizer import AnonymizationStrategy, Anonymizer


def anonymize_text(
    text: str,
    preset: str = "standard",
    strategy: AnonymizationStrategy = AnonymizationStrategy.REPLACE,
) -> str:
    """
    Quick text anonymization with sensible defaults.

    Args:
        text: Text to anonymize
        preset: Preset entity group ("minimal", "standard", "compliance")
        strategy: How to anonymize

    Returns:
        Anonymized text

    Example:
        >>> from hyperi_pylib.anonymizer import anonymize_text
        >>> anonymize_text("My SSN is 123-45-6789")
        "My SSN is <US_SSN>"
    """
    anonymizer = Anonymizer(preset=preset, strategy=strategy)
    return anonymizer.anonymize(text)


def anonymize_dict(
    data: dict[str, Any],
    preset: str = "standard",
    strategy: AnonymizationStrategy = AnonymizationStrategy.REPLACE,
) -> dict[str, Any]:
    """
    Quick dictionary anonymization.

    Args:
        data: Dictionary to anonymize
        preset: Preset entity group
        strategy: How to anonymize

    Returns:
        Anonymized dictionary

    Example:
        >>> from hyperi_pylib.anonymizer import anonymize_dict
        >>> data = {"ssn": "123-45-6789", "name": "John"}
        >>> anonymize_dict(data)
        {"ssn": "<US_SSN>", "name": "John"}
    """
    anonymizer = Anonymizer(preset=preset, strategy=strategy)
    return anonymizer.anonymize_dict(data)


def scan_for_pii(text: str, preset: str = "standard", min_score: float = 0.5) -> list[dict[str, Any]]:
    """
    Quick PII scan (detection without anonymization).

    Args:
        text: Text to scan
        preset: Preset entity group
        min_score: Minimum confidence score (0.0-1.0)

    Returns:
        List of detected PII entities with metadata

    Example:
        >>> from hyperi_pylib.anonymizer import scan_for_pii
        >>> results = scan_for_pii("My SSN is 123-45-6789")
        >>> print(results[0]["entity_type"])
        "US_SSN"
    """
    anonymizer = Anonymizer(preset=preset, score_threshold=min_score)
    return anonymizer.scan(text)


def anonymize_config_file(
    input_path: str,
    output_path: str,
    preset: str = "compliance",
    strategy: AnonymizationStrategy = AnonymizationStrategy.REPLACE,
    scan_only: bool = False,
) -> list[dict[str, Any]]:
    """
    Anonymize a configuration file (YAML, JSON, .env).

    Detects and anonymizes PII in config files. Useful for:
    - Creating sanitized config samples
    - Sharing configs for debugging
    - Auditing configs before commit

    Args:
        input_path: Path to config file
        output_path: Path to write anonymized config (ignored if scan_only=True)
        preset: Preset entity group
        strategy: How to anonymize
        scan_only: Only scan, don't write output (for auditing)

    Returns:
        List of detected PII (empty if scan_only=False and no PII found)

    Example:
        >>> # Scan config for PII before commit
        >>> results = anonymize_config_file(
        ...     "settings.yaml",
        ...     "settings.anonymized.yaml",
        ...     scan_only=True
        ... )
        >>> if results:
        ...     print(f"WARNING: Found {len(results)} PII items in config!")
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Config file not found: {input_path}")

    # Read file content
    content = input_file.read_text()

    # Create anonymizer
    anonymizer = Anonymizer(preset=preset, strategy=strategy)

    # Scan for PII
    detected_pii = anonymizer.scan(content)

    if scan_only:
        return detected_pii

    # Anonymize and write output
    anonymized_content = anonymizer.anonymize(content)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(anonymized_content)

    return detected_pii


def scan_file_for_secrets(file_path: str, min_score: float = 0.7) -> list[dict[str, Any]]:
    """
    Scan a file for secrets (passwords, API keys, tokens).

    Optimized for pre-commit hooks to detect secrets before git push.

    Args:
        file_path: Path to file to scan
        min_score: Minimum confidence score (default 0.7 for fewer false positives)

    Returns:
        List of detected secrets with line numbers and context

    Example:
        >>> # Pre-commit hook
        >>> results = scan_file_for_secrets("config.py")
        >>> if results:
        ...     for item in results:
        ...         print(f"  Line {item['line']}: {item['entity_type']}")
        ...     sys.exit(1)  # Block commit
    """
    file = Path(file_path)
    if not file.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    content = file.read_text()
    lines = content.splitlines()

    # Use minimal preset (secrets only) for pre-commit scanning
    anonymizer = Anonymizer(preset="minimal", score_threshold=min_score)

    # Get all detections
    detections = anonymizer.scan(content)

    # Enhance with line numbers
    results = []
    for detection in detections:
        # Find line number for detection
        char_pos = detection["start"]
        line_num = content[:char_pos].count("\n") + 1

        # Get line content
        line_content = lines[line_num - 1] if line_num <= len(lines) else ""

        results.append(
            {
                "entity_type": detection["entity_type"],
                "score": detection["score"],
                "text": detection["text"],
                "line": line_num,
                "line_content": line_content.strip(),
                "file": file_path,
            }
        )

    return results
