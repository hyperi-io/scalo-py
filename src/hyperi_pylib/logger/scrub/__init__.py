#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/__init__.py
#  Purpose:   Public surface for the layered log-scrub system
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Layered log-scrubbing.

Defines the contract that every log record passes through before it
hits a sink. Four layers compose in spec-mandated order:

- **L1**: secret artefacts (gitleaks-style — AWS keys, GitHub tokens,
  JWTs, private keys, third-party API keys)
- **L2**: field-name leaks (``password=...``, ``"token":"..."``)
- **L3**: PII validators (CC + Luhn, IBAN + mod-97, email, phone,
  AU ABN, AU TFN)
- **L4**: NLP entity recognition (PERSON, LOCATION, ORG — opt-in
  via ``[pii-ner]`` extra)

See ``docs/superpowers/specs/2026-05-13-log-scrub-spec.md`` for the
full cross-language contract. This module implements the pylib side.

Public surface:

- :class:`Scrubber` — protocol every scrubber satisfies
- :class:`LayeredScrubber` — concrete implementation composing the
  four layers
- :class:`NoOpScrubber` — passes input through unchanged; for tests
  and dependency-injection swaps
- :class:`ScrubConfig` — config dataclasses matching spec §6
"""

from __future__ import annotations

from .chain import LayeredScrubber, NoOpScrubber
from .config import (
    FieldsConfig,
    LogLevelsConfig,
    NationalIdsConfig,
    PiiConfig,
    PiiValidatorsConfig,
    ScrubConfig,
    SecretsConfig,
)
from .factory import build_scrubber
from .field_names import FieldNameScrubber
from .labeler import LabelFn, make_hash_labeler, resolve_labeler
from .secrets import SecretsScrubber
from .types import Scrubber

__all__ = [
    "FieldNameScrubber",
    "FieldsConfig",
    "LabelFn",
    "LayeredScrubber",
    "LogLevelsConfig",
    "NationalIdsConfig",
    "NoOpScrubber",
    "PiiConfig",
    "PiiValidatorsConfig",
    "ScrubConfig",
    "Scrubber",
    "SecretsConfig",
    "SecretsScrubber",
    "build_scrubber",
    "make_hash_labeler",
    "resolve_labeler",
]
