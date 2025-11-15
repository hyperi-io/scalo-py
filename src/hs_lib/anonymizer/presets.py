"""
Entity presets for common use cases.

Presets define which PII entity types to detect and anonymize based on
different security and compliance requirements.
"""

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
    entities: list[str]
    description: str

    def get_entities(self) -> set[str]:
        """Get entity set (for deduplication)."""
        return set(self.entities)


# Preset definitions
#
# NOTE: Presidio doesn't have built-in recognizers for PASSWORD, API_KEY, SECRET_KEY, etc.
# These patterns are better handled by regex-based filtering (hs_lib.logger.filters)
# Presidio presets focus on ML-detectable PII (SSN, credit cards, names, etc.)
MINIMAL = EntityPreset(
    name="minimal",
    description="Basic PII (crypto, email, phone) - use logger filters for passwords/API keys",
    entities=[
        # Presidio-supported entities only
        "CRYPTO",  # Crypto wallet addresses
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
    ],
)

STANDARD = EntityPreset(
    name="standard",
    description="Common PII for most applications (financial + contact + identifiers)",
    entities=[
        # From minimal
        "CRYPTO",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        # Financial
        "CREDIT_CARD",
        "IBAN_CODE",
        # Personal identifiers
        "US_SSN",
        "PERSON",
    ],
)

COMPLIANCE = EntityPreset(
    name="compliance",
    description="Full PII for HIPAA, GDPR, PCI-DSS compliance",
    entities=[
        # From standard
        "CRYPTO",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD",
        "IBAN_CODE",
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
        # NOTE: MAC_ADDRESS not supported by Presidio
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


def list_presets() -> list[str]:
    """List available preset names."""
    return list(PRESETS.keys())
