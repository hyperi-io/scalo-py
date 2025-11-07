"""
Entity presets for common use cases.

Presets define which PII entity types to detect and anonymize based on
different security and compliance requirements.
"""

from typing import List, Set
from dataclasses import dataclass


@dataclass
class EntityPreset:
    """
    Named preset of entity types to detect.

    Attributes:
        name: Preset name
        entities: List of Presidio entity types
        description: Human-readable description
    """

    name: str
    entities: List[str]
    description: str

    def get_entities(self) -> Set[str]:
        """Get entity set (for deduplication)."""
        return set(self.entities)


# Preset definitions
MINIMAL = EntityPreset(
    name="minimal",
    description="Basic secrets only (passwords, API keys, tokens)",
    entities=[
        # Secrets/Credentials (most common)
        "PASSWORD",
        "API_KEY",
        "SECRET_KEY",
        "CRYPTO",  # Crypto wallet addresses
    ],
)

STANDARD = EntityPreset(
    name="standard",
    description="Common PII for most applications (secrets + financial + contact)",
    entities=[
        # Secrets (from minimal)
        "PASSWORD",
        "API_KEY",
        "SECRET_KEY",
        "CRYPTO",
        # Financial
        "CREDIT_CARD",
        "IBAN_CODE",
        # Personal identifiers
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        # US-specific
        "US_SSN",
        # Generic person name (if available)
        "PERSON",
    ],
)

COMPLIANCE = EntityPreset(
    name="compliance",
    description="Full PII for HIPAA, GDPR, PCI-DSS compliance",
    entities=[
        # Secrets (from minimal)
        "PASSWORD",
        "API_KEY",
        "SECRET_KEY",
        "CRYPTO",
        # Financial
        "CREDIT_CARD",
        "IBAN_CODE",
        # Personal identifiers
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "PERSON",
        # US identifiers
        "US_SSN",
        "US_DRIVER_LICENSE",
        "US_PASSPORT",
        "US_BANK_NUMBER",
        "US_ITIN",  # Individual Taxpayer Identification Number
        # Medical
        "MEDICAL_LICENSE",
        # UK identifiers
        "UK_NHS",
        # Network
        "IP_ADDRESS",
        "MAC_ADDRESS",
        # Dates (for HIPAA - dates of service, birth, etc.)
        "DATE_TIME",
        # Geographic (partial address detection)
        "LOCATION",
        "URL",
    ],
)

# Preset registry
PRESETS = {
    "minimal": MINIMAL,
    "standard": STANDARD,
    "compliance": COMPLIANCE,
}


def get_preset(name: str) -> EntityPreset:
    """
    Get a preset by name.

    Args:
        name: Preset name ("minimal", "standard", "compliance")

    Returns:
        EntityPreset instance

    Raises:
        ValueError: If preset name not found
    """
    preset = PRESETS.get(name.lower())
    if not preset:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    return preset


def list_presets() -> List[str]:
    """List available preset names."""
    return list(PRESETS.keys())
