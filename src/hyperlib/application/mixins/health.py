"""
HealthCheckMixin: Health and readiness endpoints for Kubernetes.

This mixin provides /health and /ready endpoints for container health checks.
Full implementation in Phase 3.
"""

from typing import Any

from hyperlib.logger import logger


class HealthCheckMixin:
    """
    Mixin to add health check capabilities to applications.

    Provides /health (liveness) and /ready (readiness) endpoints for
    Kubernetes probes. Supports dependency checks (database, cache, etc.)

    NOTE: This is a placeholder for Phase 3 implementation.

    Example:
        class MyAPI(HealthCheckMixin, ProfileMixin):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)

                @self.health_check
                def check_database():
                    return db.ping()  # Return True if healthy
    """

    def __init__(self, **kwargs: Any):
        """
        Initialize health check mixin.

        Args:
            **kwargs: Additional args passed to next mixin in chain
        """
        self._health_check_handlers = []

        # Setup health check endpoints if enabled in profile
        if self._should_setup_health_checks():
            self._setup_health_checks()

        # Call next mixin in MRO chain
        super().__init__(**kwargs)

    def _should_setup_health_checks(self) -> bool:
        """Check if health checks should be enabled based on profile."""
        if hasattr(self, "profile"):
            return self.profile.get("health_check", False)
        return False

    def _setup_health_checks(self) -> None:
        """
        Setup health check endpoints.

        Phase 3 implementation will:
        - Start HTTP server on health_check_port
        - Add /health endpoint (liveness - always 200 if running)
        - Add /ready endpoint (readiness - checks dependencies)
        """
        logger.info(f"Health checks enabled on port {self.profile.get('health_check_port', 8080)}")
        # Full implementation in Phase 3

    def health_check(self, func):
        """
        Register a health check handler (decorator).

        Phase 3 implementation will call registered handlers for /ready endpoint.

        Args:
            func: Function that returns True if healthy, False if not

        Returns:
            The original function (allows use as decorator)

        Example:
            @app.health_check
            def check_database():
                return db.ping()
        """
        self._health_check_handlers.append(func)
        logger.debug(f"Registered health check: {func.__name__}")
        return func
