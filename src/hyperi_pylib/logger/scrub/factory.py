#  Project:   hyperi-pylib
#  File:      src/hyperi_pylib/logger/scrub/factory.py
#  Purpose:   build_scrubber() -- factory composing all enabled layers
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Factory for constructing a :class:`LayeredScrubber` from config.

Reads :class:`ScrubConfig`, builds the per-layer scrubber list in
spec-mandated order (L1 -> L2 -> L3 -> L4), skips disabled layers,
returns a single composed scrubber.

This is the canonical way for application code to obtain a scrubber.
Direct construction of :class:`LayeredScrubber` is fine but the
factory handles the wiring details correctly.
"""

from __future__ import annotations

from .chain import LayeredScrubber
from .config import ScrubConfig
from .labeler import resolve_labeler
from .metrics import ScrubMetrics
from .types import Scrubber

__all__ = ["build_scrubber"]


def build_scrubber(
    config: ScrubConfig | None = None,
    metrics: ScrubMetrics | None = None,
) -> LayeredScrubber:
    """Build a :class:`LayeredScrubber` per the supplied config.

    Composes layers in spec §2.1 order -- L1 -> L2 -> L3 -- including only
    those layers enabled by the config. There is no L4: NLP/NER
    scrubbing was dropped from scope (false-positive rate on log
    content was unacceptable; both pylib and rustlib stop at L3).

    Args:
        config: scrubber configuration. ``None`` means use the canonical
            defaults from :class:`ScrubConfig`.

    Returns:
        A :class:`LayeredScrubber` ready to call. Always returns an
        instance -- even ``ScrubConfig(enabled=False)`` returns a
        scrubber that passes input through.

    Example:
        >>> from hyperi_pylib.logger.scrub import build_scrubber, ScrubConfig
        >>> scrubber = build_scrubber()  # canonical defaults
        >>> clean = scrubber.scrub("API token ghp_abcdef1234... sent")
    """
    config = config if config is not None else ScrubConfig()
    # Operator kill-switch: ScrubConfig.metrics_enabled=False forces noop
    # regardless of what the caller passed in. Honours the hot-path opt-out
    # described in spec §8.
    if not config.metrics_enabled or metrics is None:
        metrics = ScrubMetrics.noop()
    layers: list[Scrubber] = []

    # Resolve the labeler once -- every layer that produces labels shares it
    # so per-value correlation works across L1 + L3 within a single line.
    labeler = resolve_labeler(hash_redaction=config.hash_redaction)

    # L1 -- secret artefacts (gitleaks-style)
    if config.secrets.enabled and config.secrets.patterns != "off":
        from .secrets import SecretsScrubber

        layers.append(
            SecretsScrubber(
                patterns=config.secrets.patterns,
                labeler=labeler,
                metrics=metrics,
            )
        )

    # L2 -- field-name regex (uses static ***REDACTED***; field name itself
    # carries the type signal, no correlation value from hashing).
    if config.fields.enabled:
        from .field_names import FieldNameScrubber

        layers.append(FieldNameScrubber())

    # L3 -- structured PII validators
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
            layers.append(CreditCardValidator(labeler=labeler, metrics=metrics))
        if v.iban:
            layers.append(IbanValidator(labeler=labeler, metrics=metrics))
        if v.email:
            layers.append(EmailValidator(labeler=labeler, metrics=metrics))
        if v.phone:
            layers.append(PhoneValidator(labeler=labeler, metrics=metrics))
        layers.extend(
            build_national_id_validators(
                enabled_countries=v.national_ids.enabled,
                labeler=labeler,
                metrics=metrics,
            )
        )

    # No L4 (NLP/NER) -- dropped from the spec. See PiiConfig docstring
    # for why.

    # Per spec §8: emit pattern_version metrics at scrubber build time so
    # operators know which pattern set the running service is using. The
    # version sources are read from the bundled TOML / installed package
    # metadata at startup (rather than threaded through config) because
    # they describe what's COMPILED in, not configuration choices.
    _emit_pattern_versions(metrics)

    return LayeredScrubber(config=config, layers=layers, metrics=metrics)


def _emit_pattern_versions(metrics: ScrubMetrics) -> None:
    """Emit `log_scrub_pattern_version{source, version}` per spec §8."""
    # L1 -- canonical TOML-driven path (gitleaks.toml vendored from hyperi-ai).
    try:
        from .gitleaks_toml import load_gitleaks_rules

        _, meta = load_gitleaks_rules()
        if isinstance(meta, dict):
            metrics.set_pattern_version("gitleaks", str(meta.get("version", "unversioned")))
    except Exception:
        pass

    # detect-secrets -- still available as the entropy/heuristic fallback path.
    try:
        from importlib.metadata import version as _pkg_version

        metrics.set_pattern_version("detect-secrets", _pkg_version("detect-secrets"))
    except Exception:
        pass

    # Bundled national-IDs registry -- version stamped in the TOML.
    try:
        from .pii import load_registry

        reg = load_registry()
        # The seeder emits a top-level _meta block with version; tolerate
        # absence (older TOMLs).
        meta = reg.get("_meta", {})
        if isinstance(meta, dict):
            version = str(meta.get("version", "unversioned"))
        else:
            version = "unversioned"
        metrics.set_pattern_version("national_ids", version)
    except Exception:
        pass

    # phonenumbers library version (libphonenumber-grade phone matching).
    try:
        from importlib.metadata import version as _pkg_version

        metrics.set_pattern_version("phonenumbers", _pkg_version("phonenumbers"))
    except Exception:
        pass
