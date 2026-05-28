#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub_resolver.py
#  Purpose:   Resolve a Scrubber instance from setup() args + config dict
#  Language:  Python
#
#  License:   BUSL-1.1
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Build a :class:`Scrubber` from logger setup arguments + the
``logging.*`` config dict.

Resolution priority (highest wins):

1. Explicit ``scrubber=`` kwarg to :func:`setup` -- operator chose
   exactly which scrubber object to use.
2. Explicit ``scrub_config=`` kwarg -- operator built a
   :class:`ScrubConfig` and wants the factory to materialise it.
3. ``logging.scrub.*`` keys in the config dict -- new hierarchical
   schema per spec §6.
4. ``logging.mask_sensitive_data`` / ``logging.masking_level``
   legacy keys -- emit a deprecation warning, map to ScrubConfig.
5. Defaults -- :class:`ScrubConfig` with all layers enabled.

Returns a :class:`LayeredScrubber` (or whatever the explicit
``scrubber=`` was), never ``None``. A disabled scrubber is still a
scrubber that returns input unchanged.
"""

from __future__ import annotations

import warnings
from typing import Any

from .scrub import (
    FieldsConfig,
    LayeredScrubber,
    LogLevelsConfig,
    NationalIdsConfig,
    PiiConfig,
    PiiValidatorsConfig,
    Scrubber,
    ScrubConfig,
    SecretsConfig,
    build_scrubber,
)


def resolve_scrubber(
    *,
    scrubber: Scrubber | None = None,
    scrub_config: ScrubConfig | None = None,
    mask_sensitive: bool | None = None,
    masking_level: str | None = None,
    config_dict: dict[str, Any] | None = None,
) -> Scrubber:
    """Resolve a :class:`Scrubber` from setup args + config dict.

    See module docstring for resolution priority.
    """
    # 1. Explicit scrubber instance
    if scrubber is not None:
        return scrubber

    # 2. Explicit ScrubConfig
    if scrub_config is not None:
        return build_scrubber(scrub_config)

    # 3. Explicit legacy kwargs override config_dict
    if mask_sensitive is not None or masking_level is not None:
        return build_scrubber(_legacy_to_scrub_config(mask_sensitive, masking_level))

    config = config_dict or {}

    # 4. New schema in config -- `logging.scrub.*`
    if "scrub" in config:
        return build_scrubber(_parse_scrub_dict(config["scrub"]))

    # 5. Legacy schema in config
    if "mask_sensitive_data" in config or "masking_level" in config:
        warnings.warn(
            "logging.mask_sensitive_data and logging.masking_level are "
            "deprecated. Migrate to logging.scrub.* per the spec -- old "
            "keys will be removed in a future release.",
            DeprecationWarning,
            stacklevel=3,
        )
        return build_scrubber(
            _legacy_to_scrub_config(
                config.get("mask_sensitive_data"),
                config.get("masking_level"),
            )
        )

    # 6. Defaults
    return build_scrubber()


def _legacy_to_scrub_config(
    mask_sensitive: bool | None,
    masking_level: str | None,
) -> ScrubConfig:
    """Map legacy ``mask_sensitive`` / ``masking_level`` to ScrubConfig.

    Legacy semantics:

    - ``mask_sensitive=False`` -> entire scrubber disabled
    - ``masking_level="simple"`` -> field-name regex only (no L3 PII layer)
    - ``masking_level="advanced"`` -> enables L3 algorithmic PII
      validators (credit card / IBAN / email / phone / national IDs)
    - ``masking_level="advanced-ner"`` / ``"presidio"`` -> deprecated.
      NLP/NER scrubbing was dropped from scope. Both emit deprecation
      warnings and map to ``"advanced"``.
    """
    if mask_sensitive is False:
        return ScrubConfig(enabled=False)

    level = (masking_level or "advanced").lower()

    if level == "simple":
        # Field-name only -- no PII layer
        return ScrubConfig(
            pii=PiiConfig(enabled=False),
        )
    if level == "advanced":
        # Structured PII validators on -- default ScrubConfig
        return ScrubConfig()
    if level in ("advanced-ner", "presidio"):
        warnings.warn(
            f"masking_level={level!r} is deprecated: NLP/NER scrubbing has "
            "been dropped from hyperi-pylib (false-positive rate on log "
            "content was unacceptable). Mapping to 'advanced' "
            "(algorithmic PII validators).",
            DeprecationWarning,
            stacklevel=4,
        )
        return ScrubConfig()

    # Unknown level -> default scrubber
    warnings.warn(
        f"masking_level={level!r} not recognised -- using defaults. Valid: 'simple', 'advanced'.",
        UserWarning,
        stacklevel=4,
    )
    return ScrubConfig()


def _parse_scrub_dict(d: dict[str, Any]) -> ScrubConfig:
    """Parse a ``logging.scrub.*`` config dict into a ScrubConfig.

    Tolerant: missing keys take defaults; unknown keys are silently
    dropped. Boolean-like values are coerced.
    """

    def _bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _list_str(value: Any, default: list[str]) -> list[str]:
        if value is None:
            return list(default)
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value]
        if isinstance(value, str):
            # Allow comma-separated string for env-var convenience
            return [s.strip() for s in value.split(",") if s.strip()]
        return list(default)

    # Subsection helpers
    def _fields(sub: dict | None) -> FieldsConfig:
        sub = sub or {}
        return FieldsConfig(enabled=_bool(sub.get("enabled"), True))

    def _secrets(sub: dict | None) -> SecretsConfig:
        sub = sub or {}
        return SecretsConfig(
            enabled=_bool(sub.get("enabled"), True),
            patterns=str(sub.get("patterns", "gitleaks")),
            entropy_filter=_bool(sub.get("entropy_filter"), False),
            token_efficiency=_bool(sub.get("token_efficiency"), False),
        )

    def _validators(sub: dict | None) -> PiiValidatorsConfig:
        sub = sub or {}
        nat_sub = sub.get("national_ids") or {}
        return PiiValidatorsConfig(
            credit_card=_bool(sub.get("credit_card"), True),
            iban=_bool(sub.get("iban"), True),
            email=_bool(sub.get("email"), True),
            phone=_bool(sub.get("phone"), True),
            national_ids=NationalIdsConfig(
                enabled=_list_str(nat_sub.get("enabled"), ["au"]),
            ),
        )

    def _pii(sub: dict | None) -> PiiConfig:
        sub = sub or {}
        # `nlp` is silently ignored if present in legacy configs -- see
        # the PiiConfig docstring for why NLP was dropped.
        return PiiConfig(
            enabled=_bool(sub.get("enabled"), True),
            validators=_validators(sub.get("validators")),
            token_efficiency=_bool(sub.get("token_efficiency"), False),
        )

    def _log_levels(sub: dict | None) -> LogLevelsConfig:
        sub = sub or {}
        return LogLevelsConfig(
            error=_bool(sub.get("error"), True),
            warn=_bool(sub.get("warn"), True),
            info=_bool(sub.get("info"), True),
            debug=_bool(sub.get("debug"), True),
            trace=_bool(sub.get("trace"), False),
        )

    def _int(value: Any, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    return ScrubConfig(
        enabled=_bool(d.get("enabled"), True),
        observe_only=_bool(d.get("observe_only"), False),
        hash_redaction=_bool(d.get("hash_redaction"), False),
        metrics_enabled=_bool(d.get("metrics_enabled"), True),
        metrics_type_cardinality_cap=_int(d.get("metrics_type_cardinality_cap"), 64),
        fields=_fields(d.get("fields")),
        secrets=_secrets(d.get("secrets")),
        pii=_pii(d.get("pii")),
        log_levels=_log_levels(d.get("log_levels")),
    )
