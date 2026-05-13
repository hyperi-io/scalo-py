#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/config.py
#  Purpose:   Configuration dataclasses matching spec §6
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Scrubber configuration schema.

Mirrors the canonical YAML in spec §6. Each language maps these keys
identically — the config is part of the cross-language contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FieldsConfig:
    """Layer 2 — field-name regex (``password=...``, ``"token":...``)."""

    enabled: bool = True


@dataclass(slots=True)
class SecretsConfig:
    """Layer 1 — secret artefacts (gitleaks-style).

    Args:
        enabled: master toggle for the layer.
        patterns: rule-set selector — ``"gitleaks"`` (full),
            ``"minimal"`` (high-signal subset), or ``"off"``.
        entropy_filter: opt-in pure-entropy scan. False by default —
            FP-prone on normal log content (UUIDs, hashes, request
            IDs read high-entropy).
        token_efficiency: opt-in cache for repeated-token matches.
            Reduces hot-path cost when bursts contain the same
            secret value many times.
    """

    enabled: bool = True
    patterns: str = "gitleaks"
    entropy_filter: bool = False
    token_efficiency: bool = False


@dataclass(slots=True)
class PiiValidatorsConfig:
    """Per-validator toggles for Layer 3.

    Each defaults True. Operators disable specific validators when
    they want to log e.g. emails in support tooling.
    """

    credit_card: bool = True
    iban: bool = True
    email: bool = True
    phone: bool = True
    abn: bool = True
    tfn: bool = True


@dataclass(slots=True)
class PiiConfig:
    """Layer 3 — structured PII validators + optional Layer 4 NLP.

    Args:
        enabled: master toggle for L3.
        validators: per-validator toggles (see :class:`PiiValidatorsConfig`).
        nlp: opt-in L4 (NER for PERSON/LOCATION/ORG). Requires
            ``[pii-ner]`` extra. Default False for cross-language
            parity (rustlib has no NER).
        token_efficiency: opt-in cache for repeated-match results.
    """

    enabled: bool = True
    validators: PiiValidatorsConfig = field(default_factory=PiiValidatorsConfig)
    nlp: bool = False
    token_efficiency: bool = False


@dataclass(slots=True)
class LogLevelsConfig:
    """Per-log-level scrubbing gate (spec §5.6).

    Setting a level to False bypasses the scrubber entirely for
    records at that level. Useful to disable on ``trace`` (volume),
    or to keep enabled on ``debug`` (where devs sometimes paste
    secrets into temporary logs).
    """

    error: bool = True
    warn: bool = True
    info: bool = True
    debug: bool = True
    trace: bool = False


@dataclass(slots=True)
class ScrubConfig:
    """Top-level scrubber configuration. Mirrors spec §6 verbatim.

    Args:
        enabled: master switch. False disables the scrubber entirely.
        observe_only: detect-only mode. Emit metrics, leave output
            unchanged. For tuning in staging (spec §5.5).
        hash_redaction: deterministic short-hash labels. When True,
            redactions look like ``[EMAIL_a3f5b2]`` so operators can
            correlate the same value across log lines without
            revealing it (spec §4.4).
        fields: Layer 2 config.
        secrets: Layer 1 config.
        pii: Layer 3 + Layer 4 config.
        log_levels: per-log-level gate (Layer 0).
    """

    enabled: bool = True
    observe_only: bool = False
    hash_redaction: bool = False
    fields: FieldsConfig = field(default_factory=FieldsConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    pii: PiiConfig = field(default_factory=PiiConfig)
    log_levels: LogLevelsConfig = field(default_factory=LogLevelsConfig)
