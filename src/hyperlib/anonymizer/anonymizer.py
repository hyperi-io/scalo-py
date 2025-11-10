"""
Core Anonymizer class with Presidio integration.
"""

import json
from enum import Enum
from typing import Any

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from .custom_recognizers import get_custom_recognizers
from .presets import get_preset


class AnonymizationStrategy(Enum):
    """
    How to anonymize detected PII.

    - REPLACE: Replace with <ENTITY_TYPE> (default, best for debugging)
    - REDACT: Replace with "***REDACTED***" (uniform masking)
    - MASK: Partial masking (e.g., 123-45-6789 → ***-**-6789)
    - HASH: One-way hash (SHA256, consistent per value)
    - ENCRYPT: Reversible encryption (requires key, not yet implemented)
    """

    REPLACE = "replace"
    REDACT = "redact"
    MASK = "mask"
    HASH = "hash"
    ENCRYPT = "encrypt"


class Anonymizer:
    """
    Opinionated anonymizer with Presidio.

    Provides hyperlib-style ergonomics for common PII anonymization use cases.

    **Quick Start:**

    ```python
    from hyperlib.anonymizer import Anonymizer

    # Use defaults (standard preset, replace strategy)
    anonymizer = Anonymizer()
    result = anonymizer.anonymize("My SSN is 123-45-6789")
    # Output: "My SSN is <US_SSN>"
    ```

    **Presets:**

    - **minimal:** Passwords, API keys, secrets only
    - **standard:** Secrets + financial + contact info (default)
    - **compliance:** Full PII for HIPAA, GDPR, PCI-DSS

    **Strategies:**

    - **REPLACE:** `<ENTITY_TYPE>` (default, preserves structure)
    - **REDACT:** `***REDACTED***` (uniform)
    - **MASK:** Partial (e.g., `***-**-6789`)
    - **HASH:** SHA256 one-way hash

    **Examples:**

    ```python
    # Compliance preset with masking
    anonymizer = Anonymizer(preset="compliance", strategy=AnonymizationStrategy.MASK)

    # Custom entities
    anonymizer = Anonymizer(entities=["CREDIT_CARD", "SSN", "EMAIL_ADDRESS"])

    # Custom replacements per entity
    anonymizer = Anonymizer(replacements={"US_SSN": "***-**-****"})

    # Anonymize dictionary
    data = {"ssn": "123-45-6789", "email": "john@example.com"}
    result = anonymizer.anonymize_dict(data)
    ```
    """

    def __init__(
        self,
        preset: str = "standard",
        entities: list[str] | None = None,
        strategy: AnonymizationStrategy = AnonymizationStrategy.REPLACE,
        replacements: dict[str, str] | None = None,
        language: str = "en",
        score_threshold: float = 0.5,
        enable_custom_recognizers: bool = True,
    ):
        """Initialize anonymizer (see class docstring for usage)."""
        # Create analyzer engine
        self.analyzer = AnalyzerEngine()

        # Add custom recognizers (passwords, API keys, secrets)
        if enable_custom_recognizers:
            custom_recognizers = get_custom_recognizers()
            for recognizer in custom_recognizers:
                self.analyzer.registry.add_recognizer(recognizer)

        self.anonymizer = AnonymizerEngine()

        # Determine entities to detect
        if entities:
            self.entities = list(set(entities))  # Deduplicate
        else:
            preset_obj = get_preset(preset)
            self.entities = list(preset_obj.get_entities())

            # Add custom entity types if enabled
            if enable_custom_recognizers:
                self.entities.extend(["PASSWORD", "API_KEY", "SECRET_KEY"])

        self.strategy = strategy
        self.replacements = replacements or {}
        self.language = language
        self.score_threshold = score_threshold

    def anonymize(self, text: str) -> str:
        """
        Anonymize PII in text.

        Args:
            text: Text to anonymize

        Returns:
            Anonymized text with PII replaced according to strategy

        Example:
            >>> anonymizer = Anonymizer()
            >>> anonymizer.anonymize("My SSN is 123-45-6789")
            "My SSN is <US_SSN>"
        """
        if not text or not isinstance(text, str):
            return text

        # Analyze text for PII
        results = self.analyzer.analyze(
            text=text,
            entities=self.entities,
            language=self.language,
            score_threshold=self.score_threshold,
        )

        if not results:
            return text  # No PII found

        # Build operators based on strategy
        operators = self._build_operators(results)

        # Anonymize
        anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)

        return anonymized.text

    def anonymize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively anonymize PII in dictionary.

        This converts the dict to JSON, anonymizes, and parses back.
        For better performance with large nested dicts, consider
        using StreamingAnonymizer for field-by-field processing.

        Args:
            data: Dictionary to anonymize

        Returns:
            Anonymized dictionary

        Example:
            >>> anonymizer = Anonymizer()
            >>> data = {"ssn": "123-45-6789", "name": "John"}
            >>> anonymizer.anonymize_dict(data)
            {"ssn": "<US_SSN>", "name": "John"}
        """
        if not data:
            return data

        # Convert to JSON string, anonymize, parse back
        text = json.dumps(data, indent=2)
        anonymized_text = self.anonymize(text)

        try:
            return json.loads(anonymized_text)
        except json.JSONDecodeError:
            # If anonymization broke JSON structure, return original
            # (This can happen with aggressive masking)
            return data

    def scan(self, text: str) -> list[dict[str, Any]]:
        """
        Scan for PII without anonymizing.

        Useful for auditing/reporting what PII exists in data.

        Args:
            text: Text to scan

        Returns:
            List of detected PII entities with metadata

        Example:
            >>> anonymizer = Anonymizer()
            >>> results = anonymizer.scan("My SSN is 123-45-6789")
            >>> print(results)
            [
                {
                    "entity_type": "US_SSN",
                    "start": 10,
                    "end": 21,
                    "score": 0.85,
                    "text": "123-45-6789"
                }
            ]
        """
        if not text or not isinstance(text, str):
            return []

        results = self.analyzer.analyze(
            text=text,
            entities=self.entities,
            language=self.language,
            score_threshold=self.score_threshold,
        )

        return [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": r.score,
                "text": text[r.start : r.end],
            }
            for r in results
        ]

    def _build_operators(self, results) -> dict[str, OperatorConfig]:
        """
        Build Presidio operators based on strategy and custom replacements.

        Args:
            results: Analyzer results (list of RecognizerResult)

        Returns:
            Dict mapping entity type to OperatorConfig
        """
        operators = {}

        # Get unique entity types from results
        entity_types = {r.entity_type for r in results}

        for entity_type in entity_types:
            # Check for custom replacement first
            if entity_type in self.replacements:
                operators[entity_type] = OperatorConfig("replace", {"new_value": self.replacements[entity_type]})
            elif self.strategy == AnonymizationStrategy.REPLACE:
                operators[entity_type] = OperatorConfig("replace", {"new_value": f"<{entity_type}>"})
            elif self.strategy == AnonymizationStrategy.REDACT:
                operators[entity_type] = OperatorConfig("redact", {})
            elif self.strategy == AnonymizationStrategy.MASK:
                operators[entity_type] = OperatorConfig(
                    "mask",
                    {
                        "masking_char": "*",
                        "chars_to_mask": 12,
                        "from_end": False,
                    },
                )
            elif self.strategy == AnonymizationStrategy.HASH:
                operators[entity_type] = OperatorConfig("hash", {"hash_type": "sha256"})
            elif self.strategy == AnonymizationStrategy.ENCRYPT:
                # TODO: Implement encryption strategy
                # Requires key management
                raise NotImplementedError("ENCRYPT strategy not yet implemented")

        return operators
