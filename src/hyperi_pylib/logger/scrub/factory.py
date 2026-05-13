#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/factory.py
#  Purpose:   build_scrubber() — factory composing all enabled layers
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Factory for constructing a :class:`LayeredScrubber` from config.

Reads :class:`ScrubConfig`, builds the per-layer scrubber list in
spec-mandated order (L1 → L2 → L3 → L4), skips disabled layers,
returns a single composed scrubber.

This is the canonical way for application code to obtain a scrubber.
Direct construction of :class:`LayeredScrubber` is fine but the
factory handles the wiring details correctly.
"""

from __future__ import annotations

from .chain import LayeredScrubber
from .config import ScrubConfig
from .labeler import resolve_labeler
from .types import Scrubber

__all__ = ["build_scrubber"]


def build_scrubber(config: ScrubConfig | None = None) -> LayeredScrubber:
    """Build a :class:`LayeredScrubber` per the supplied config.

    Composes layers in spec §2.1 order — L1 → L2 → L3 — including only
    those layers enabled by the config. L4 (NLP) is not wired yet (lands
    when the DataFog NER backend is exposed under the scrub namespace
    in a follow-up step).

    Args:
        config: scrubber configuration. ``None`` means use the canonical
            defaults from :class:`ScrubConfig`.

    Returns:
        A :class:`LayeredScrubber` ready to call. Always returns an
        instance — even ``ScrubConfig(enabled=False)`` returns a
        scrubber that passes input through.

    Example:
        >>> from hyperi_pylib.logger.scrub import build_scrubber, ScrubConfig
        >>> scrubber = build_scrubber()  # canonical defaults
        >>> clean = scrubber.scrub("API token ghp_abcdef1234... sent")
    """
    config = config if config is not None else ScrubConfig()
    layers: list[Scrubber] = []

    # Resolve the labeler once — every layer that produces labels shares it
    # so per-value correlation works across L1 + L3 within a single line.
    labeler = resolve_labeler(hash_redaction=config.hash_redaction)

    # L1 — secret artefacts (gitleaks-style)
    if config.secrets.enabled and config.secrets.patterns != "off":
        from .secrets import SecretsScrubber

        layers.append(
            SecretsScrubber(patterns=config.secrets.patterns, labeler=labeler)
        )

    # L2 — field-name regex (uses static ***REDACTED***; field name itself
    # carries the type signal, no correlation value from hashing).
    if config.fields.enabled:
        from .field_names import FieldNameScrubber

        layers.append(FieldNameScrubber())

    # L3 — structured PII validators
    if config.pii.enabled:
        from .pii import (
            CreditCardValidator,
            EmailValidator,
            IbanValidator,
            PhoneValidator,
            build_national_id_validators,
        )

        v = config.pii.validators
        # Strong-structural first (lower FP risk), TOML-driven national
        # IDs after.
        if v.credit_card:
            layers.append(CreditCardValidator(labeler=labeler))
        if v.iban:
            layers.append(IbanValidator(labeler=labeler))
        if v.email:
            layers.append(EmailValidator(labeler=labeler))
        if v.phone:
            layers.append(PhoneValidator(labeler=labeler))
        layers.extend(
            build_national_id_validators(
                enabled_countries=v.national_ids.enabled,
                labeler=labeler,
            )
        )

    # L4 — NLP (NER). Not yet wired into the scrub namespace; will be
    # added when the existing DataFogSensitiveDataFilter is migrated
    # to expose the Scrubber Protocol directly.

    return LayeredScrubber(config=config, layers=layers)
