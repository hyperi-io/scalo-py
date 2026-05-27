#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/__init__.py
#  Purpose:   Public surface for the layered log-scrub system
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Layered log-scrubbing.

Defines the contract that every log record passes through before it
hits a sink. Three layers compose in spec-mandated order:

- **L1**: secret artefacts (gitleaks-style -- AWS keys, GitHub tokens,
  JWTs, private keys, third-party API keys)
- **L2**: field-name leaks (``password=...``, ``"token":"..."``)
- **L3**: PII validators (CC + Luhn, IBAN + mod-97, email, phone,
  AU ABN, AU TFN)

There is no L4. Earlier drafts of the spec included an opt-in NLP/NER
backend for unstructured entities (PERSON / LOCATION / ORG); it was
dropped because the false-positive rate on logs was unacceptable and
the per-call cost (5-200ms) was incompatible with structured-logging
budgets. Both pylib and rustlib stop at L3.

See ``docs/superpowers/specs/2026-05-13-log-scrub-spec.md`` for the
full cross-language contract. This module implements the pylib side.

Public surface:

- :class:`Scrubber` -- protocol every scrubber satisfies
- :class:`LayeredScrubber` -- concrete implementation composing the
  four layers
- :class:`NoOpScrubber` -- passes input through unchanged; for tests
  and dependency-injection swaps
- :class:`ScrubConfig` -- config dataclasses matching spec §6
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
from .metrics import ScrubMetrics
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
    "ScrubMetrics",
    "Scrubber",
    "SecretsConfig",
    "SecretsScrubber",
    "build_scrubber",
    "make_hash_labeler",
    "resolve_labeler",
]
