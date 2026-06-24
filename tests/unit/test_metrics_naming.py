#  Project:      scalo
#  File:         test_metrics_naming.py
#  Purpose:      Tests for metric naming + configurable prefix validation
#  Language:     Python
#
#  License:      Apache-2.0
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for metric naming validation and the configurable metric prefix."""

from scalo._env_compat import metric_prefix, set_metric_prefix
from scalo.metrics.naming import (
    validate_dfe_prefix,
    validate_metric_name,
    validate_metric_prefix,
)


class TestValidateMetricName:
    """Test metric naming convention validation (suffix rules)."""

    def test_counter_with_total_suffix_passes(self):
        """Counter ending in _total produces no warnings."""
        warnings = validate_metric_name("loader_records_received_total", "counter")
        assert warnings == []

    def test_counter_without_total_suffix_warns(self):
        """Counter missing _total suffix produces a warning."""
        warnings = validate_metric_name("loader_records_received", "counter")
        assert len(warnings) == 1
        assert "_total" in warnings[0]

    def test_histogram_with_seconds_suffix_passes(self):
        """Histogram ending in _seconds produces no warnings."""
        warnings = validate_metric_name("loader_flush_duration_seconds", "histogram")
        assert warnings == []

    def test_histogram_with_bytes_suffix_passes(self):
        """Histogram ending in _bytes produces no warnings."""
        warnings = validate_metric_name("loader_file_size_bytes", "histogram")
        assert warnings == []

    def test_histogram_with_ratio_suffix_passes(self):
        """Histogram ending in _ratio produces no warnings."""
        warnings = validate_metric_name("archiver_compression_ratio", "histogram")
        assert warnings == []

    def test_histogram_without_unit_suffix_warns(self):
        """Histogram without a unit suffix produces a warning."""
        warnings = validate_metric_name("loader_flush_duration", "histogram")
        assert len(warnings) == 1
        assert "unit suffix" in warnings[0].lower() or "seconds" in warnings[0].lower()

    def test_gauge_with_bytes_suffix_passes(self):
        """Gauge ending in _bytes produces no warnings."""
        warnings = validate_metric_name("loader_buffer_bytes", "gauge")
        assert warnings == []

    def test_gauge_without_unit_not_warned(self):
        """Gauge without a unit suffix produces no warnings (gauges are flexible)."""
        warnings = validate_metric_name("loader_buffer_records", "gauge")
        assert warnings == []

    def test_info_gauge_passes(self):
        """Info gauge (ending in _info or named 'info') passes."""
        warnings = validate_metric_name("loader_info", "gauge")
        assert warnings == []

    def test_unknown_metric_type_no_crash(self):
        """Unknown metric type should not crash."""
        warnings = validate_metric_name("some_metric", "summary")
        assert isinstance(warnings, list)


class TestMetricPrefixSsot:
    """The metric prefix is bare by default and configurable like the env prefix."""

    def test_default_is_bare(self):
        """With nothing set, the metric prefix is bare ("")."""
        assert metric_prefix() == ""

    def test_set_metric_prefix_overrides(self):
        """set_metric_prefix establishes the active prefix (trailing _ stripped)."""
        set_metric_prefix("dfe_")
        assert metric_prefix() == "dfe"

    def test_metric_prefix_from_control_var(self, monkeypatch):
        """METRIC_PREFIX env var is honoured when no explicit override is set."""
        monkeypatch.setenv("METRIC_PREFIX", "acme")
        assert metric_prefix() == "acme"


class TestValidateMetricPrefix:
    """Test the configurable-prefix validator."""

    def test_bare_default_accepts_any_name(self):
        """With the bare default prefix and no app, any non-empty name passes."""
        assert validate_metric_prefix("records_received_total") == []

    def test_explicit_prefix_enforced(self):
        """An explicit prefix is required at the front of the name."""
        assert validate_metric_prefix("myapp_records_total", prefix="myapp") == []
        warnings = validate_metric_prefix("records_total", prefix="myapp")
        assert len(warnings) == 1
        assert "myapp_" in warnings[0]

    def test_prefix_and_app_enforced(self):
        """prefix + app expects '{prefix}_{app}_'."""
        assert validate_metric_prefix("myapp_loader_records_total", app="loader", prefix="myapp") == []
        warnings = validate_metric_prefix("myapp_receiver_records_total", app="loader", prefix="myapp")
        assert len(warnings) == 1
        assert "myapp_loader_" in warnings[0]

    def test_active_prefix_used_when_none(self):
        """prefix=None falls back to the active metric_prefix()."""
        set_metric_prefix("dfe")
        warnings = validate_metric_prefix("loader_records_total")
        assert len(warnings) == 1
        assert "dfe_" in warnings[0]

    def test_empty_name_warns(self):
        """Empty metric name produces a warning."""
        assert len(validate_metric_prefix("", app="loader", prefix="myapp")) >= 1


class TestValidateDfePrefixDeprecated:
    """The deprecated validate_dfe_prefix alias keeps enforcing the dfe_ prefix."""

    def test_correct_prefix_passes(self):
        assert validate_dfe_prefix("dfe_loader_records_total", "loader") == []

    def test_missing_dfe_prefix_warns(self):
        warnings = validate_dfe_prefix("loader_records_total", "loader")
        assert len(warnings) == 1
        assert "dfe_loader_" in warnings[0]

    def test_platform_metrics_with_no_app(self):
        assert validate_dfe_prefix("dfe_records_received_total", "") == []
