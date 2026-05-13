#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/pii/__init__.py
#  Purpose:   Layer 3 PII validators (strong-structural + context-required)
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Layer 3 — structured PII validators.

Two tiers per spec §9:

- **Strong-structural** (fires from any context):
  :class:`CreditCardValidator`, :class:`IbanValidator`,
  :class:`EmailValidator`, :class:`PhoneValidator`
- **Context-required** (requires keyword nearby):
  :class:`AbnValidator`, :class:`AcnValidator`,
  :class:`TfnValidator`, :class:`MedicareValidator`

Each is a :class:`Scrubber` (per the Protocol in
``hyperi_pylib.logger.scrub.types``) and can be composed into a
:class:`LayeredScrubber`.

Validation logic delegates to ``python-stdnum`` where available
(ABN, ACN, TFN, IBAN, Luhn) and is implemented locally where it
isn't (Medicare — per ATO spec §9.7).
"""

from __future__ import annotations

from .au_abn import AbnValidator
from .au_acn import AcnValidator
from .au_medicare import MedicareValidator
from .au_tfn import TfnValidator
from .credit_card import CreditCardValidator
from .email import EmailValidator
from .iban import IbanValidator
from .phone import PhoneValidator

__all__ = [
    "AbnValidator",
    "AcnValidator",
    "CreditCardValidator",
    "EmailValidator",
    "IbanValidator",
    "MedicareValidator",
    "PhoneValidator",
    "TfnValidator",
]
