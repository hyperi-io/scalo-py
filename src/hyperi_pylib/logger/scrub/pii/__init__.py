#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/__init__.py
#  Purpose:   Layer 3 PII validators (strong-structural + TOML-driven national IDs)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Layer 3 — structured PII validators.

Two tiers per spec §9:

**Strong-structural** (fires from any context) — hand-coded classes:

- :class:`CreditCardValidator` (Luhn via stdnum.luhn)
- :class:`IbanValidator` (mod-97 via stdnum.iban)
- :class:`EmailValidator` (RFC 5322 subset regex)
- :class:`PhoneValidator` (libphonenumber via phonenumbers)

**Context-required** (keyword anchor required) — TOML-driven:

National-ID validators load from the bundled
``hyperi_pylib/data/national_ids.toml`` (vendored from
``hyperi-ai/standards/patterns/national_ids.toml`` per spec §3.0).
Per-country entries with ``enabled = true`` materialise as
:class:`_DynamicValidator` instances via :func:`build_national_id_validators`.

AU ships pre-active (ABN, ACN, TFN, Medicare). Other countries are
seeded as stubs (``enabled = false``) — operators opt-in after
hand-curating ``detection_regex`` and ``keywords``.
"""

from __future__ import annotations

from ._dynamic import _DynamicValidator
from ._loader import build_national_id_validators, load_registry
from .credit_card import CreditCardValidator
from .email import EmailValidator
from .iban import IbanValidator
from .phone import PhoneValidator

__all__ = [
    "CreditCardValidator",
    "EmailValidator",
    "IbanValidator",
    "PhoneValidator",
    "_DynamicValidator",
    "build_national_id_validators",
    "load_registry",
]
