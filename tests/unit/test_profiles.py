"""
Tests for application profile system.
"""

import pytest

from hyperlib.application.profiles import PROFILES, load_profile, _deep_copy, _deep_merge


class TestProfiles:
    """Test profile system."""

    def test_profiles_exist(self):
        """Test that all expected profiles exist."""
        assert "dev" in PROFILES
        assert "docker" in PROFILES
        assert "prod" in PROFILES

    def test_dev_profile_settings(self):
        """Test dev profile has correct settings."""
        profile = PROFILES["dev"]
        assert profile["logging"]["format"] == "console"
        assert profile["logging"]["level"] == "DEBUG"
        assert profile["logging"]["colors"] is True
        assert profile["health_check"] is False
        assert profile["metrics"] is False
        assert profile["graceful_shutdown"] is True
        assert profile["reload"] is True

    def test_docker_profile_settings(self):
        """Test docker profile has correct settings."""
        profile = PROFILES["docker"]
        assert profile["logging"]["format"] == "json"
        assert profile["logging"]["level"] == "INFO"
        assert profile["health_check"] is True
        assert profile["health_check_port"] == 8080
        assert profile["metrics"] is True
        assert profile["metrics_port"] == 9090
        assert profile["graceful_shutdown"] is True
        assert profile["shutdown_timeout"] == 30
        assert profile["reload"] is False

    def test_prod_profile_settings(self):
        """Test prod profile has correct settings (k8s)."""
        profile = PROFILES["prod"]
        assert profile["logging"]["format"] == "json"
        assert profile["health_check"] is True
        assert profile["health_check_port"] == 8080
        assert profile["readiness_initial_delay"] == 5
        assert profile["liveness_initial_delay"] == 30
        assert profile["startup_initial_delay"] == 0
        assert profile["metrics"] is True
        assert profile["metrics_port"] == 9090
        assert profile["graceful_shutdown"] is True
        assert profile["shutdown_timeout"] == 30

    def test_load_profile_dev(self):
        """Test loading dev profile."""
        profile = load_profile("dev")
        assert profile["logging"]["format"] == "console"
        assert profile["health_check"] is False

    def test_load_profile_invalid(self):
        """Test loading invalid profile raises error."""
        with pytest.raises(ValueError) as exc_info:
            load_profile("invalid")
        assert "Invalid profile" in str(exc_info.value)
        assert "invalid" in str(exc_info.value)

    def test_load_profile_with_overrides(self):
        """Test profile overrides work."""
        profile = load_profile("dev", {"metrics": True, "metrics_port": 9091})
        assert profile["metrics"] is True
        assert profile["metrics_port"] == 9091
        # Other settings unchanged
        assert profile["logging"]["format"] == "console"

    def test_load_profile_with_nested_overrides(self):
        """Test nested dict overrides work."""
        profile = load_profile("dev", {"logging": {"level": "WARNING"}})
        assert profile["logging"]["level"] == "WARNING"
        # Other logging settings preserved
        assert profile["logging"]["format"] == "console"
        assert profile["logging"]["colors"] is True

    def test_profile_isolation(self):
        """Test profiles don't share state (deep copy)."""
        profile1 = load_profile("dev")
        profile2 = load_profile("dev")

        # Modify profile1
        profile1["custom_key"] = "value"

        # profile2 should not be affected
        assert "custom_key" not in profile2

    def test_deep_copy_dict(self):
        """Test deep copy creates independent copy."""
        original = {"a": {"b": [1, 2, 3]}}
        copied = _deep_copy(original)

        copied["a"]["b"].append(4)

        assert original["a"]["b"] == [1, 2, 3]
        assert copied["a"]["b"] == [1, 2, 3, 4]

    def test_deep_merge_flat(self):
        """Test deep merge with flat dict."""
        base = {"a": 1, "b": 2}
        updates = {"b": 3, "c": 4}

        result = _deep_merge(base, updates)

        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_nested(self):
        """Test deep merge with nested dicts."""
        base = {"logging": {"format": "console", "level": "DEBUG"}}
        updates = {"logging": {"level": "INFO"}}

        result = _deep_merge(base, updates)

        # Level updated, format preserved
        assert result["logging"]["format"] == "console"
        assert result["logging"]["level"] == "INFO"

    def test_deep_merge_preserves_base(self):
        """Test deep merge doesn't modify base dict."""
        base = {"a": 1}
        updates = {"b": 2}

        result = _deep_merge(base, updates)

        assert base == {"a": 1}  # Unchanged
        assert result == {"a": 1, "b": 2}
