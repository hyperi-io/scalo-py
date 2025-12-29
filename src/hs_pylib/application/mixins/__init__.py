"""
Application mixins for container-native patterns.

Mixins provide reusable functionality through composition:
- ProfileMixin: Profile loading and application
- SignalHandlerMixin: Graceful shutdown handling
- CLIExecutableMixin: Typer CLI commands
- HealthCheckMixin: Health/readiness endpoints
- MetricsMixin: Auto-instrumentation
"""

from .cli import CLIExecutableMixin
from .health import HealthCheckMixin
from .metrics import MetricsMixin
from .profile import ProfileMixin
from .signals import SignalHandlerMixin

__all__ = [
    "ProfileMixin",
    "SignalHandlerMixin",
    "CLIExecutableMixin",
    "HealthCheckMixin",
    "MetricsMixin",
]
