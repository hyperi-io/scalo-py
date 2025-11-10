"""
ProfileMixin: Load and apply profile configuration to applications.

This mixin enables profile-based configuration for different deployment
environments (dev, docker, prod).
"""

from typing import Any, Dict, Optional

from ..profiles import load_profile


class ProfileMixin:
    """
    Mixin to add profile support to application classes.

    Loads profile configuration and applies it to the application instance.
    Profile settings are stored in self.profile for access by other mixins.

    Example:
        class MyApp(ProfileMixin):
            def __init__(self, name: str, profile: str = "dev", **overrides):
                super().__init__(profile=profile, **overrides)
                # self.profile is now available
                print(f"Logging level: {self.profile['logging']['level']}")
    """

    def __init__(
        self,
        profile: str = "dev",
        profile_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize profile mixin.

        Args:
            profile: Profile name ("dev", "docker", or "prod")
            profile_overrides: Optional dict to override profile settings
            **kwargs: Additional args passed to next mixin in chain
        """
        # Load profile configuration
        self.profile_name = profile
        self.profile = load_profile(profile, profile_overrides)

        # Apply profile settings
        self._apply_profile()

        # Call next mixin in MRO chain
        super().__init__(**kwargs)

    def _apply_profile(self) -> None:
        """
        Apply profile settings to application.

        This method is called during initialization and can be overridden
        by subclasses to apply profile-specific configuration.

        Base implementation does nothing - subclasses should override.
        """
        pass

    def get_profile_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a profile setting by key with optional default.

        Args:
            key: Setting key (supports nested keys with dots, e.g., "logging.level")
            default: Default value if key not found

        Returns:
            Setting value or default

        Example:
            >>> app.get_profile_setting("logging.level")
            'DEBUG'
            >>> app.get_profile_setting("missing.key", "default")
            'default'
        """
        # Split nested keys (e.g., "logging.level" -> ["logging", "level"])
        keys = key.split(".")
        value = self.profile

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value
