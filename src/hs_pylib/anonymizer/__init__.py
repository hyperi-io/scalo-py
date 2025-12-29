"""
hs-pylib Anonymizer - Opinionated PII detection and anonymization.

This module provides a simple, opinionated API for anonymizing sensitive data
using Microsoft Presidio as the underlying engine. It offers:

- **Zero-config defaults:** Works out of the box for common use cases
- **Presets:** "minimal", "standard", "compliance" for different security needs
- **Streaming support:** Efficient processing of large data streams (Kafka, etc.)
- **Multiple strategies:** Replace, redact, mask, hash, encrypt
- **Multi-format:** Text, JSON, dicts, config files

Installation:
    pip install hs-pylib[presidio]

Quick Start:
    from hs_pylib.anonymizer import anonymize_text

    result = anonymize_text("My SSN is 123-45-6789")
    # Output: "My SSN is <SSN>"

Advanced Usage:
    from hs_pylib.anonymizer import Anonymizer, AnonymizationStrategy

    # Custom configuration
    anonymizer = Anonymizer(
        preset="compliance",
        strategy=AnonymizationStrategy.MASK
    )

    # Text
    result = anonymizer.anonymize("My credit card is 4532-0151-1283-0366")

    # Dictionary
    data = {"ssn": "123-45-6789", "name": "John"}
    result = anonymizer.anonymize_dict(data)

    # Streaming (for Kafka, large files)
    for chunk in anonymizer.stream_anonymize(large_text_iterator):
        kafka_producer.send(chunk)

See: https://microsoft.github.io/presidio/ for Presidio documentation
"""

try:
    from .anonymizer import AnonymizationStrategy, Anonymizer
    from .convenience import (
        anonymize_config_file,
        anonymize_dict,
        anonymize_text,
        scan_for_pii,
    )
    from .presets import PRESETS, EntityPreset
    from .streaming import StreamingAnonymizer

    __all__ = [
        "Anonymizer",
        "AnonymizationStrategy",
        "StreamingAnonymizer",
        "PRESETS",
        "EntityPreset",
        "anonymize_text",
        "anonymize_dict",
        "scan_for_pii",
        "anonymize_config_file",
    ]

except ImportError:
    # Presidio not installed - provide helpful error message
    import warnings

    warnings.warn(
        "Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer\n"
        "Or: pip install hs-pylib[presidio]",
        ImportWarning,
        stacklevel=2,
    )

    # Stub implementations that raise helpful errors
    class Anonymizer:
        def __init__(self, *args, **kwargs):
            raise ImportError("Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer")

    class AnonymizationStrategy:
        pass

    class StreamingAnonymizer:
        def __init__(self, *args, **kwargs):
            raise ImportError("Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer")

    PRESETS = {}
    EntityPreset = None

    def anonymize_text(*args, **kwargs):
        raise ImportError("Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer")

    def anonymize_dict(*args, **kwargs):
        raise ImportError("Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer")

    def scan_for_pii(*args, **kwargs):
        raise ImportError("Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer")

    def anonymize_config_file(*args, **kwargs):
        raise ImportError("Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer")

    __all__ = [
        "Anonymizer",
        "AnonymizationStrategy",
        "StreamingAnonymizer",
        "PRESETS",
        "EntityPreset",
        "anonymize_text",
        "anonymize_dict",
        "scan_for_pii",
        "anonymize_config_file",
    ]
