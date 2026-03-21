#  Project:      hyperi-pylib
#  File:         test_metrics_naming.py
#  Purpose:      Tests for DFE metric naming validation
#  Language:     Python
#
#  License:      FSL-1.1-ALv2
#  Copyright:    (c) 2026 HYPERI PTY LIMITED

"""Tests for DFE metric naming validation."""

from hyperi_pylib.metrics.naming import validate_dfe_prefix, validate_metric_name


class TestValidateMetricName:
    """Test metric naming convention validation."""

    def test_counter_with_total_suffix_passes(self):
        """Counter ending in _total produces no warnings."""
        warnings = validate_metric_name("dfe_loader_records_received_total", "counter")
        assert warnings == []

    def test_counter_without_total_suffix_warns(self):
        """Counter missing _total suffix produces a warning."""
        warnings = validate_metric_name("dfe_loader_records_received", "counter")
        assert len(warnings) == 1
        assert "_total" in warnings[0]

    def test_histogram_with_seconds_suffix_passes(self):
        """Histogram ending in _seconds produces no warnings."""
        warnings = validate_metric_name("dfe_loader_flush_duration_seconds", "histogram")
        assert warnings == []

    def test_histogram_with_bytes_suffix_passes(self):
        """Histogram ending in _bytes produces no warnings."""
        warnings = validate_metric_name("dfe_loader_file_size_bytes", "histogram")
        assert warnings == []

    def test_histogram_with_ratio_suffix_passes(self):
        """Histogram ending in _ratio produces no warnings."""
        warnings = validate_metric_name("dfe_archiver_compression_ratio", "histogram")
        assert warnings == []

    def test_histogram_without_unit_suffix_warns(self):
        """Histogram without a unit suffix produces a warning."""
        warnings = validate_metric_name("dfe_loader_flush_duration", "histogram")
        assert len(warnings) == 1
        assert "unit suffix" in warnings[0].lower() or "seconds" in warnings[0].lower()

    def test_gauge_with_bytes_suffix_passes(self):
        """Gauge ending in _bytes produces no warnings."""
        warnings = validate_metric_name("dfe_loader_buffer_bytes", "gauge")
        assert warnings == []

    def test_gauge_without_unit_not_warned(self):
        """Gauge without a unit suffix produces no warnings (gauges are flexible)."""
        warnings = validate_metric_name("dfe_loader_buffer_records", "gauge")
        assert warnings == []

    def test_info_gauge_passes(self):
        """Info gauge (ending in _info or named 'info') passes."""
        warnings = validate_metric_name("dfe_loader_info", "gauge")
        assert warnings == []

    def test_unknown_metric_type_no_crash(self):
        """Unknown metric type should not crash."""
        warnings = validate_metric_name("some_metric", "summary")
        assert isinstance(warnings, list)


class TestValidateDfePrefix:
    """Test DFE prefix validation."""

    def test_correct_prefix_passes(self):
        """Metric with correct dfe_{app}_ prefix produces no warnings."""
        warnings = validate_dfe_prefix("dfe_loader_records_total", "loader")
        assert warnings == []

    def test_missing_dfe_prefix_warns(self):
        """Metric without dfe_ prefix produces a warning."""
        warnings = validate_dfe_prefix("loader_records_total", "loader")
        assert len(warnings) == 1
        assert "dfe_loader_" in warnings[0]

    def test_wrong_app_prefix_warns(self):
        """Metric with wrong app name produces a warning."""
        warnings = validate_dfe_prefix("dfe_receiver_records_total", "loader")
        assert len(warnings) == 1
        assert "dfe_loader_" in warnings[0]

    def test_platform_metrics_with_no_app(self):
        """Platform metrics (dfe_* without app) pass when app is empty string."""
        warnings = validate_dfe_prefix("dfe_records_received_total", "")
        assert warnings == []

    def test_empty_name_warns(self):
        """Empty metric name produces a warning."""
        warnings = validate_dfe_prefix("", "loader")
        assert len(warnings) >= 1
