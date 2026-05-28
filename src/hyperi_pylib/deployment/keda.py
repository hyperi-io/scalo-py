# Project:   hyperi-pylib
# File:      deployment/keda.py
# Purpose:   KEDA autoscaling configuration and contract types
# Language:  Python
#
# License:   BUSL-1.1
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""KEDA autoscaling models -- mirrors rustlib's ``hyperi_rustlib::deployment::keda``.

``KedaConfig`` lives in the app's config cascade so thresholds are
overridable via env vars (e.g., ``DFE_LOADER__KEDA__KAFKA_LAG_THRESHOLD=5000``).

``KedaContract`` is the subset validated against Helm ``values.yaml``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KedaConfig(BaseModel):
    """KEDA autoscaling configuration for the app config cascade.

    Include this in your app's ``Config`` model so KEDA thresholds participate
    in the Dynaconf cascade and are env-var overridable.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    """Whether KEDA scaling is enabled."""

    min_replicas: int = Field(default=1, ge=0)
    """Minimum replica count (0 = scale-to-zero)."""

    max_replicas: int = Field(default=10, ge=1)
    """Maximum replica count."""

    polling_interval: int = Field(default=15, ge=1)
    """Seconds between KEDA polling the scaler."""

    cooldown_period: int = Field(default=300, ge=0)
    """Seconds before scale-down after load drops."""

    kafka_lag_threshold: int = Field(default=1000, ge=0)
    """Scale when consumer group lag exceeds this per partition."""

    activation_lag_threshold: int = Field(default=0, ge=0)
    """Wake from zero replicas when lag exceeds this."""

    cpu_enabled: bool = True
    """Enable CPU-based scaling trigger."""

    cpu_threshold: int = Field(default=80, ge=1, le=100)
    """CPU utilisation percentage threshold."""


class KedaContract(BaseModel):
    """KEDA contract points validated against Helm ``values.yaml``.

    Built from ``KedaConfig`` defaults via ``KedaContract.from_config``.
    Field validation mirrors ``KedaConfig`` so a contract carrying nonsense
    (e.g. negative replicas) fails at construction, not at deploy time.
    """

    model_config = ConfigDict(extra="forbid")

    min_replicas: int = Field(default=1, ge=0)
    max_replicas: int = Field(default=10, ge=1)
    polling_interval: int = Field(default=15, ge=1)
    cooldown_period: int = Field(default=300, ge=0)
    kafka_lag_threshold: int = Field(default=1000, ge=0)
    activation_lag_threshold: int = Field(default=0, ge=0)
    cpu_enabled: bool = True
    cpu_threshold: int = Field(default=80, ge=1, le=100)

    @classmethod
    def from_config(cls, config: KedaConfig) -> KedaContract:
        """Build a contract from a KedaConfig -- strips the ``enabled`` flag."""
        return cls(
            min_replicas=config.min_replicas,
            max_replicas=config.max_replicas,
            polling_interval=config.polling_interval,
            cooldown_period=config.cooldown_period,
            kafka_lag_threshold=config.kafka_lag_threshold,
            activation_lag_threshold=config.activation_lag_threshold,
            cpu_enabled=config.cpu_enabled,
            cpu_threshold=config.cpu_threshold,
        )


__all__ = ["KedaConfig", "KedaContract"]
