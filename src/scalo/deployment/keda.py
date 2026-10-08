# Project:   scalo
# File:      deployment/keda.py
# Purpose:   KEDA autoscaling configuration and contract types
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""KEDA autoscaling models -- mirrors scalo-rs's ``scalo::deployment::keda``.

``KedaConfig`` lives in the app's config cascade so thresholds are
overridable via env vars (e.g., ``MYAPP__KEDA__KAFKA_LAG_THRESHOLD=5000``).

``KedaContract`` is the subset validated against Helm ``values.yaml``.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_TRIGGER_BASE = "config.kafka"
"""The values section the Kafka lag trigger reads unless told otherwise."""


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


class KafkaLagTrigger(BaseModel):
    """Where the Kafka lag trigger reads its connection details in the chart's values.

    Each path is dotted and ``.Values``-relative. The default suits a config
    with a top-level ``kafka`` section; :meth:`under` names another section and
    :meth:`disabled` turns the trigger off, as in scalo-rs.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    """Emit the Kafka lag trigger. Off leaves CPU as the only scaler."""

    brokers_path: str = f"{_DEFAULT_TRIGGER_BASE}.brokers"
    """Values path of the broker list, as a list or a comma-separated string."""

    group_path: str = f"{_DEFAULT_TRIGGER_BASE}.group_id"
    """Values path of the consumer group id."""

    topics_path: str = f"{_DEFAULT_TRIGGER_BASE}.topics"
    """Values path of the topics, as a list or a comma-separated string. KEDA watches the first."""

    @classmethod
    def under(cls, base: str) -> Self:
        """A trigger reading ``brokers``, ``group_id`` and ``topics`` under ``base``, e.g. ``config.source``."""
        return cls(
            brokers_path=f"{base}.brokers",
            group_path=f"{base}.group_id",
            topics_path=f"{base}.topics",
        )

    @classmethod
    def disabled(cls) -> Self:
        """No Kafka lag trigger, for an app that does not consume from Kafka."""
        return cls(enabled=False)


class KedaContract(BaseModel):
    """KEDA contract points validated against Helm ``values.yaml``.

    Built from ``KedaConfig`` defaults via ``KedaContract.from_config``.
    Field validation mirrors ``KedaConfig`` so a contract carrying nonsense
    (e.g. negative replicas) fails at construction, not at deploy time.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    """Whether the chart turns KEDA on. False generates exactly what ``keda=None`` does."""

    min_replicas: int = Field(default=1, ge=0)
    max_replicas: int = Field(default=10, ge=1)
    polling_interval: int = Field(default=15, ge=1)
    cooldown_period: int = Field(default=300, ge=0)
    kafka_lag_threshold: int = Field(default=1000, ge=0)
    activation_lag_threshold: int = Field(default=0, ge=0)
    cpu_enabled: bool = True
    cpu_threshold: int = Field(default=80, ge=1, le=100)

    kafka_trigger: KafkaLagTrigger = Field(default_factory=KafkaLagTrigger)
    """Where the Kafka lag trigger finds its connection details, or that there is none."""

    @classmethod
    def from_config(cls, config: KedaConfig) -> Self:
        """Build a contract from a KedaConfig, with the default Kafka lag trigger."""
        return cls(
            enabled=config.enabled,
            min_replicas=config.min_replicas,
            max_replicas=config.max_replicas,
            polling_interval=config.polling_interval,
            cooldown_period=config.cooldown_period,
            kafka_lag_threshold=config.kafka_lag_threshold,
            activation_lag_threshold=config.activation_lag_threshold,
            cpu_enabled=config.cpu_enabled,
            cpu_threshold=config.cpu_threshold,
        )


__all__ = ["KafkaLagTrigger", "KedaConfig", "KedaContract"]
