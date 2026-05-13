#  Project:   hyperi-pylib
#  File:      tests/unit/test_scrub_resolver.py
#  Purpose:   Tests for resolve_scrubber() — config + kwargs → Scrubber
#  Language:  Python
#
#  License:   FSL-1.1-ALv2
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""Tests for the scrubber resolver — priority order, legacy mapping,
new schema parsing."""

from __future__ import annotations

import pytest

from hyperi_pylib.logger.scrub import (
    LayeredScrubber,
    NoOpScrubber,
    ScrubConfig,
    SecretsConfig,
)
from hyperi_pylib.logger.scrub_resolver import (
    _legacy_to_scrub_config,
    _parse_scrub_dict,
    resolve_scrubber,
)


# ---------------------------------------------------------------------------
# Priority order (highest wins)
# ---------------------------------------------------------------------------


class TestResolverPriority:
    def test_explicit_scrubber_wins(self):
        mock = NoOpScrubber()
        result = resolve_scrubber(
            scrubber=mock,
            scrub_config=ScrubConfig(enabled=False),  # ignored
            mask_sensitive=False,  # ignored
            config_dict={"scrub": {"enabled": False}},  # ignored
        )
        assert result is mock

    def test_scrub_config_wins_over_legacy(self):
        # ScrubConfig arg takes priority over legacy kwargs and config
        cfg = ScrubConfig(secrets=SecretsConfig(enabled=False))
        result = resolve_scrubber(
            scrub_config=cfg,
            mask_sensitive=True,  # legacy ignored
            config_dict={"mask_sensitive_data": True},  # legacy config ignored
        )
        assert isinstance(result, LayeredScrubber)
        # secrets disabled per the ScrubConfig
        assert result.config.secrets.enabled is False

    def test_legacy_kwargs_win_over_config_dict(self):
        result = resolve_scrubber(
            mask_sensitive=False,
            config_dict={"scrub": {"enabled": True}},  # ignored
        )
        # mask_sensitive=False → ScrubConfig(enabled=False)
        assert isinstance(result, LayeredScrubber)
        assert result.config.enabled is False

    def test_new_schema_wins_over_legacy_in_config(self):
        # Both new and legacy keys present — new wins, no deprecation warning
        import warnings as _w
        with _w.catch_warnings(record=True) as captured:
            _w.simplefilter("always")
            result = resolve_scrubber(
                config_dict={
                    "scrub": {"enabled": True},
                    "mask_sensitive_data": False,  # legacy — ignored
                }
            )
        assert not any(
            issubclass(w.category, DeprecationWarning) for w in captured
        )
        assert result.config.enabled is True

    def test_legacy_config_emits_deprecation(self):
        with pytest.warns(DeprecationWarning, match="deprecated"):
            resolve_scrubber(
                config_dict={"mask_sensitive_data": True}
            )

    def test_defaults_when_nothing_provided(self):
        result = resolve_scrubber()
        assert isinstance(result, LayeredScrubber)
        assert result.config.enabled is True


# ---------------------------------------------------------------------------
# Legacy → ScrubConfig mapping
# ---------------------------------------------------------------------------


class TestLegacyMapping:
    def test_mask_sensitive_false_disables_all(self):
        cfg = _legacy_to_scrub_config(mask_sensitive=False, masking_level=None)
        assert cfg.enabled is False

    def test_masking_level_simple(self):
        cfg = _legacy_to_scrub_config(mask_sensitive=True, masking_level="simple")
        # simple = field-name only, no PII layer
        assert cfg.pii.enabled is False
        assert cfg.fields.enabled is True
        assert cfg.secrets.enabled is True

    def test_masking_level_advanced(self):
        cfg = _legacy_to_scrub_config(mask_sensitive=True, masking_level="advanced")
        assert cfg.pii.enabled is True
        assert cfg.pii.nlp is False

    def test_masking_level_advanced_ner(self):
        cfg = _legacy_to_scrub_config(mask_sensitive=True, masking_level="advanced-ner")
        assert cfg.pii.enabled is True
        assert cfg.pii.nlp is True

    def test_masking_level_presidio_deprecated(self):
        with pytest.warns(DeprecationWarning, match="presidio"):
            cfg = _legacy_to_scrub_config(mask_sensitive=True, masking_level="presidio")
        # maps to advanced-ner
        assert cfg.pii.nlp is True

    def test_unknown_masking_level_warns(self):
        with pytest.warns(UserWarning, match="not recognised"):
            cfg = _legacy_to_scrub_config(mask_sensitive=True, masking_level="bogus")
        # Falls back to defaults
        assert cfg.enabled is True


# ---------------------------------------------------------------------------
# New schema parsing
# ---------------------------------------------------------------------------


class TestSchemaParsing:
    def test_empty_dict_gives_defaults(self):
        cfg = _parse_scrub_dict({})
        assert cfg.enabled is True
        assert cfg.observe_only is False
        assert cfg.pii.enabled is True
        assert cfg.log_levels.trace is False

    def test_master_disable(self):
        cfg = _parse_scrub_dict({"enabled": False})
        assert cfg.enabled is False

    def test_observe_only(self):
        cfg = _parse_scrub_dict({"observe_only": True})
        assert cfg.observe_only is True

    def test_secrets_patterns(self):
        cfg = _parse_scrub_dict({"secrets": {"patterns": "minimal"}})
        assert cfg.secrets.patterns == "minimal"

    def test_pii_nlp_opt_in(self):
        cfg = _parse_scrub_dict({"pii": {"nlp": True}})
        assert cfg.pii.nlp is True

    def test_national_ids_enabled_list(self):
        cfg = _parse_scrub_dict(
            {"pii": {"validators": {"national_ids": {"enabled": ["au", "us"]}}}}
        )
        assert cfg.pii.validators.national_ids.enabled == ["au", "us"]

    def test_national_ids_csv_string(self):
        # Env-var convenience — comma-separated string converts to list
        cfg = _parse_scrub_dict(
            {"pii": {"validators": {"national_ids": {"enabled": "au, us, uk"}}}}
        )
        assert cfg.pii.validators.national_ids.enabled == ["au", "us", "uk"]

    def test_log_levels_off_trace_on_others(self):
        cfg = _parse_scrub_dict(
            {"log_levels": {"trace": False, "debug": True, "info": True}}
        )
        assert cfg.log_levels.trace is False
        assert cfg.log_levels.debug is True
        assert cfg.log_levels.info is True

    def test_bool_coercion_from_strings(self):
        # Env vars come through as strings
        cfg = _parse_scrub_dict({"enabled": "true", "observe_only": "yes"})
        assert cfg.enabled is True
        assert cfg.observe_only is True

        cfg2 = _parse_scrub_dict({"enabled": "false", "observe_only": "0"})
        assert cfg2.enabled is False
        assert cfg2.observe_only is False

    def test_unknown_keys_ignored(self):
        cfg = _parse_scrub_dict({"bogus": True, "enabled": True})
        assert cfg.enabled is True


# ---------------------------------------------------------------------------
# Log-level gating via _scrub_level_enabled
# ---------------------------------------------------------------------------


from hyperi_pylib.logger.logger import _scrub_level_enabled
from hyperi_pylib.logger.scrub import LogLevelsConfig


class TestLogLevelGate:
    def test_trace_disabled_by_default(self):
        gates = LogLevelsConfig()
        assert _scrub_level_enabled("TRACE", gates) is False
        assert _scrub_level_enabled("trace", gates) is False  # case-insensitive

    def test_info_enabled_by_default(self):
        assert _scrub_level_enabled("INFO", LogLevelsConfig()) is True

    def test_warning_maps_to_warn(self):
        gates = LogLevelsConfig(warn=False)
        assert _scrub_level_enabled("WARNING", gates) is False

    def test_critical_maps_to_error(self):
        gates = LogLevelsConfig(error=False)
        assert _scrub_level_enabled("CRITICAL", gates) is False
        assert _scrub_level_enabled("ERROR", gates) is False

    def test_success_maps_to_info(self):
        # loguru's SUCCESS level is INFO-grade
        gates = LogLevelsConfig(info=False)
        assert _scrub_level_enabled("SUCCESS", gates) is False

    def test_unknown_level_defaults_to_info(self):
        gates = LogLevelsConfig(info=False)
        assert _scrub_level_enabled("UNKNOWN_LEVEL", gates) is False
