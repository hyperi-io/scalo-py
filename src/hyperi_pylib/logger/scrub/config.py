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
class NationalIdsConfig:
    """Layer 3 national-ID validators — per-jurisdiction toggles.

    Country codes are ISO 3166-1 alpha-2, lowercase. Each enabled
    country loads its national-ID validators from the bundled
    ``national_ids.toml`` registry (vendored from hyperi-ai).

    The default enables AU only — operators opt-in to additional
    jurisdictions by listing country codes:

    .. code-block:: yaml

        national_ids:
          enabled: ["au", "us", "uk"]    # enable AU + US + UK

    Entries within enabled countries are STILL gated on
    ``enabled = true`` in the TOML registry — listing a country
    here doesn't activate IDs that haven't been hand-curated.
    See spec §3.4 for the registry shape.
    """

    enabled: list[str] = field(default_factory=lambda: ["au"])


@dataclass(slots=True)
class PiiValidatorsConfig:
    """Layer 3 validator toggles (spec §6).

    Strong-structural validators (jurisdiction-agnostic) are listed
    individually. Country-specific national IDs are managed as a
    set via :class:`NationalIdsConfig`.

    Strong-structural — fire from any context:

    - ``credit_card`` — Luhn (ISO/IEC 7812-1)
    - ``iban`` — mod-97 (ISO 13616)
    - ``email`` — RFC 5322 subset
    - ``phone`` — libphonenumber

    Context-required national IDs:

    - ``national_ids.enabled`` — list of country codes. Default
      ``["au"]`` (ABN, ACN, TFN, Medicare). Adds US/UK/EU
      jurisdictions by appending their country codes.
    """

    credit_card: bool = True
    iban: bool = True
    email: bool = True
    phone: bool = True
    national_ids: NationalIdsConfig = field(default_factory=NationalIdsConfig)


@dataclass(slots=True)
class PiiConfig:
    """Layer 3 — structured PII validators.

    Args:
        enabled: master toggle for L3.
        validators: per-validator toggles (see :class:`PiiValidatorsConfig`).
        token_efficiency: opt-in cache for repeated-match results.

    Note: there is no Layer 4 (NLP/NER). Earlier drafts of the spec
    described an opt-in spaCy backend for unstructured entities
    (PERSON / LOCATION / ORG). That layer was dropped — both pylib and
    rustlib — because the false-positive rate on log content is
    unacceptable and the cost (5–200ms/call) is incompatible with
    structured-logging budgets. PII detection in HyperI services is
    L3 algorithmic + L1 secrets, full stop.
    """

    enabled: bool = True
    validators: PiiValidatorsConfig = field(default_factory=PiiValidatorsConfig)
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
        metrics_enabled: emit per-layer scrub metrics (spec §8). True
            by default. Operator kill-switch — set False to skip every
            metric call on ultra-hot paths where the ~1-2µs/layer
            histogram observation is unacceptable. Independent of
            ``observe_only`` (which is about whether to redact, not
            whether to measure).
        metrics_type_cardinality_cap: soft cap on distinct values for
            the ``type`` label of ``log_scrub_matches_total`` and
            ``log_scrub_redactions_total`` within a single scrubber
            instance. Once the cap is reached, further new ``type``
            labels are recorded under ``"OVER_CAP"`` and a one-shot
            warning is emitted. Defaults to 64 — bounded by the
            current detect-secrets type set (~24) plus headroom for
            extra_patterns. Set to 0 to disable the cap.
        fields: Layer 2 config.
        secrets: Layer 1 config.
        pii: Layer 3 + Layer 4 config.
        log_levels: per-log-level gate (Layer 0).
    """

    enabled: bool = True
    observe_only: bool = False
    hash_redaction: bool = False
    metrics_enabled: bool = True
    metrics_type_cardinality_cap: int = 64
    fields: FieldsConfig = field(default_factory=FieldsConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    pii: PiiConfig = field(default_factory=PiiConfig)
    log_levels: LogLevelsConfig = field(default_factory=LogLevelsConfig)
