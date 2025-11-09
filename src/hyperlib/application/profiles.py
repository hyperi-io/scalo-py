"""
Application profile system for environment-specific configuration.

Profiles enable the same application code to run in different environments
(dev, docker, prod) with appropriate settings for each context.
"""

from typing import Any, Dict, Optional

# Profile definitions for different deployment environments
PROFILES: Dict[str, Dict[str, Any]] = {
    "dev": {
        # Local development profile
        "logging": {
            "format": "console",  # Human-readable console output
            "level": "DEBUG",  # Verbose logging for development
            "colors": True,  # Colored output for readability
        },
        "health_check": False,  # No health endpoints locally
        "metrics": False,  # No metrics collection locally
        "graceful_shutdown": True,  # Still handle Ctrl+C gracefully
        "reload": True,  # Hot reload for development (where supported)
    },
    "docker": {
        # Integration testing, CI/CD profile
        "logging": {
            "format": "json",  # Structured logging for log aggregation
            "level": "INFO",  # Standard log level
            "colors": False,  # No color codes in logs
        },
        "health_check": True,  # Enable health endpoints
        "health_check_port": 8080,  # Health check HTTP port
        "metrics": True,  # Enable metrics collection
        "metrics_port": 9090,  # Prometheus metrics port
        "graceful_shutdown": True,  # Graceful shutdown on SIGTERM
        "shutdown_timeout": 30,  # Max seconds to wait for shutdown
        "reload": False,  # No hot reload in containers
    },
    "prod": {
        # Production profile (k8s + HELM + ArgoCD + KEDA)
        "logging": {
            "format": "json",  # Structured logging
            "level": "INFO",  # Production log level
            "colors": False,  # No color codes
        },
        "health_check": True,  # Health endpoints for k8s probes
        "health_check_port": 8080,  # Health check HTTP port
        "readiness_initial_delay": 5,  # k8s readiness probe delay (seconds)
        "liveness_initial_delay": 30,  # k8s liveness probe delay (seconds)
        "startup_initial_delay": 0,  # k8s startup probe delay (seconds)
        "metrics": True,  # Metrics for KEDA autoscaling
        "metrics_port": 9090,  # Prometheus metrics port
        "graceful_shutdown": True,  # Graceful shutdown on SIGTERM
        "shutdown_timeout": 30,  # Max seconds to wait for shutdown
        "reload": False,  # No hot reload in production
    },
}


def load_profile(name: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Load a profile by name with optional overrides.

    Args:
        name: Profile name ("dev", "docker", or "prod")
        overrides: Optional dict of settings to override profile defaults

    Returns:
        Profile configuration dict

    Raises:
        ValueError: If profile name is invalid

    Example:
        >>> profile = load_profile("dev")
        >>> profile["logging"]["format"]
        'console'

        >>> profile = load_profile("prod", {"metrics_port": 9091})
        >>> profile["metrics_port"]
        9091
    """
    if name not in PROFILES:
        valid = ", ".join(PROFILES.keys())
        raise ValueError(f"Invalid profile '{name}'. Valid profiles: {valid}")

    # Deep copy to avoid mutating the original
    profile = _deep_copy(PROFILES[name])

    # Apply overrides if provided
    if overrides:
        profile = _deep_merge(profile, overrides)

    return profile


def _deep_copy(obj: Any) -> Any:
    """Deep copy a nested dict/list structure."""
    if isinstance(obj, dict):
        return {k: _deep_copy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_copy(item) for item in obj]
    else:
        return obj


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dicts, with updates taking precedence.

    Args:
        base: Base configuration dict
        updates: Updates to apply (overrides base values)

    Returns:
        Merged configuration dict
    """
    result = base.copy()

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = _deep_merge(result[key], value)
        else:
            # Override value
            result[key] = value

    return result
