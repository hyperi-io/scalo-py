# Project:   scalo
# File:      src/scalo/kafka/providers.py
# Purpose:   Kafka provider abstraction - normalise per-provider auth +
#            capabilities behind one open, generic identity.
# Language:  Python
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

"""Kafka provider abstraction: one open ``KafkaProvider`` behind which every
provider-specific quirk is normalised. Each managed/self-hosted Kafka has its
own weirdness across MANY axes - auth, capabilities, metadata plane, schema
registry, transport tuning - and this module is the single seam that combines
them.

Two layers live here:

- The checkpoint-1 shape (``derive`` / ``validate`` / ``provider_config`` /
  ``DERIVATION``): a flat ``provider -> (security_protocol, sasl_mechanism)``
  table plus a librdkafka config-dict builder. Kept for backward
  compatibility - nothing below changes its behaviour.
- The full abstraction (``KafkaProvider`` Protocol + ``KnownProvider`` enum +
  ``ProviderCapabilities`` / ``AuthKind`` / ``MetadataMode`` /
  ``SchemaRegistry``): a generic, OPEN identity, not a closed set.
  ``KnownProvider`` implements it for the built-in providers via the SAME
  ``derive()`` table, so there is exactly one source of truth for the auth
  facts. A third party (e.g. AutoMQ) plugs in by implementing the
  ``KafkaProvider`` Protocol - no change to this module.

OPT-IN and self-contained. The core Kafka config in ``scalo.kafka.config`` works
without importing this module - reach for it when you want the provider to pick
the mechanism for you instead of hand-setting it.

One credential shape holds across every managed provider: SASL over TLS with a
username+password pair. Only the ``sasl.mechanism`` differs, and it is a property
of the PROVIDER, not a free choice:

- SCRAM-SHA-512 wherever the operator controls the broker or the platform offers
  SCRAM: self-hosted Apache Kafka / Strimzi, Redpanda (self-hosted AND Cloud),
  AWS MSK provisioned.
- PLAIN (API key) only where the platform mandates it - Confluent Cloud has no
  SCRAM. Always over TLS.
- IAM / OAUTHBEARER is a different credential shape and is quarantined (AWS MSK
  Serverless is IAM-only; provisioned MSK may opt into IAM). Not on the
  username+password contract.

The one hard security floor: PLAIN must ride an encrypted transport (SASL_SSL) -
never send a PLAIN password over a plaintext connection.

This table is the canonical record for this credential contract and is
MIRRORED in scalo-rs and its Rust consumers. Keep the tables identical -
change one, then the other.

This module is pure, generic FACT - it holds NO deployment policy. An app that
wants an opinionated contract ("SCRAM mandatory on brokers we own, never
weakened; only this blessed set is allowed") layers that ON TOP, opt-in, via
``scalo.kafka.contract``. The vanilla core here works irrespective of any such
opinion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# (security_protocol, sasl_mechanism) pairs.
_SCRAM = ("SASL_SSL", "SCRAM-SHA-512")
_PLAIN = ("SASL_SSL", "PLAIN")

# Local dev with no auth.
PLAINTEXT = "plaintext"
# Quarantined: IAM auth (OAUTHBEARER token via the AWS MSK IAM callback) - a
# different credential shape AND client-lib requirement, not username+password.
# MANDATORY for MSK Serverless (IAM is its only auth); optional on provisioned MSK.
MSK_IAM = "msk_iam"

# provider -> (security_protocol, sasl_mechanism). The username+password contract.
DERIVATION: dict[str, tuple[str, str]] = {
    "strimzi": _SCRAM,  # self-hosted Apache Kafka / Strimzi
    "redpanda": _SCRAM,  # self-hosted Redpanda
    "msk": _SCRAM,  # AWS MSK provisioned (SCRAM; serverless = msk_iam)
    "redpanda-cloud": _SCRAM,  # Redpanda Cloud (SASL_SSL + SCRAM-256/512)
    "confluent-cloud": _PLAIN,  # Confluent Cloud: no SCRAM -> API-key PLAIN over TLS
}

# Everything the presets know how to derive (for error messages).
KNOWN_PROVIDERS = sorted(DERIVATION) + [PLAINTEXT, MSK_IAM]


class KafkaProviderError(ValueError):
    """A Kafka provider/credential configuration that violates the presets."""


def derive(provider: str) -> tuple[str, str]:
    """Return ``(security_protocol, sasl_mechanism)`` for a provider.

    ``plaintext`` -> ``("PLAINTEXT", "")`` (local dev, no auth).
    ``msk_iam``   -> ``("SASL_SSL", "OAUTHBEARER")`` (quarantined IAM token path;
                     the caller wires the AWS MSK IAM callback, not user/pass).
    unknown       -> ``KafkaProviderError``.
    """
    if provider == PLAINTEXT:
        return ("PLAINTEXT", "")
    if provider == MSK_IAM:
        return ("SASL_SSL", "OAUTHBEARER")
    try:
        return DERIVATION[provider]
    except KeyError:
        raise KafkaProviderError(f"unknown kafka provider {provider!r}; expected one of {KNOWN_PROVIDERS}") from None


def validate(*, security_protocol: str, sasl_mechanism: str) -> None:
    """Refuse configurations that break the security floor. Raises ``KafkaProviderError``.

    - PLAIN credentials MUST ride SASL_SSL (never PLAIN over a plaintext transport).
    - SASL_SSL requires a mechanism.
    """
    if sasl_mechanism == "PLAIN" and security_protocol != "SASL_SSL":
        raise KafkaProviderError(
            "PLAIN credentials require security_protocol=SASL_SSL (never send PLAIN over a plaintext transport)"
        )
    if security_protocol == "SASL_SSL" and not sasl_mechanism:
        raise KafkaProviderError("security_protocol=SASL_SSL requires a sasl.mechanism")


def provider_config(
    provider: str,
    brokers: str,
    username: str = "",
    password: str = "",
    *,
    verify_ssl: bool = True,
) -> dict[str, Any]:
    """Build a librdkafka/confluent-kafka client config dict for a provider.

    The provider DERIVES ``security.protocol`` + ``sasl.mechanisms``; the caller
    supplies brokers + credentials. Merge the result with
    ``PRODUCER_DEFAULTS`` / ``CONSUMER_DEFAULTS`` / ``ADMIN_DEFAULTS`` as needed.

    ``plaintext`` yields an auth-free config (no SASL keys); every other provider
    (except the quarantined ``msk_iam``) needs a username + password.
    """
    proto, mech = derive(provider)
    validate(security_protocol=proto, sasl_mechanism=mech)

    config: dict[str, Any] = {
        "bootstrap.servers": brokers,
        "security.protocol": proto,
    }
    if mech:
        config["sasl.mechanisms"] = mech
        config["sasl.username"] = username
        config["sasl.password"] = password
    if not verify_ssl and proto == "SASL_SSL":
        config["enable.ssl.certificate.verification"] = "false"
    return config


# =============================================================================
# Full provider abstraction (mirrors scalo-rs's `KafkaProvider` trait)
# =============================================================================
#
# Everything above (DERIVATION / derive / validate / provider_config) is the
# checkpoint-1 shape: a flat provider -> (protocol, mechanism) mapping. This
# section is the FULL abstraction: one open `KafkaProvider` behind which
# every provider-specific concern (auth, capabilities, metadata plane, schema
# registry, transport tuning) is normalised. `KnownProvider` implements it
# for the seven built-in providers using the SAME `derive()` table above, so
# there is exactly one source of truth for the auth facts.


class AuthKind(Enum):
    """The credential family a provider authenticates with."""

    USER_PASSWORD = "user_password"  # noqa: S105 -- credential FAMILY label, not a secret; SASL user+pass (SCRAM or PLAIN)
    IAM = "iam"  # AWS IAM (OAUTHBEARER token via the MSK IAM callback) - quarantined
    NONE = "none"  # No auth (local dev plaintext)


class MetadataMode(Enum):
    """The cluster metadata plane - a version-implication FACT that shapes
    deployment and admin tooling (which admin features light up, how the
    cluster is stood up).
    """

    KRAFT = "kraft"  # KRaft (KIP-500) - no ZooKeeper. The modern default.
    ZOOKEEPER = "zookeeper"  # ZooKeeper-backed (legacy self-hosted)
    MANAGED = "managed"  # The platform hides the metadata plane (Confluent Cloud, MSK Serverless)


class SchemaRegistry(Enum):
    """A schema registry bundled with the provider, if any. The endpoint is a
    runtime connection detail; this is just which KIND, so a config emitter
    knows to wire it.
    """

    NONE = "none"  # No bundled registry - bring your own
    CONFLUENT = "confluent"  # Confluent Schema Registry (Confluent Cloud, or self-hosted)
    REDPANDA = "redpanda"  # Redpanda's built-in schema registry


@dataclass(frozen=True)
class ProviderCapabilities:
    """Provider-specific behaviour flags - the "weirdness" of each Kafka
    provider, combined behind one type. Static data (no I/O); the
    cluster-control lifecycle that ACTS on these reads them from the opt-in
    lifecycle layer.
    """

    managed: bool  # Managed SaaS/cloud (vs a self-hosted broker you run in-cluster)
    always_on: bool  # Bills continuously while it exists - only DELETE stops spend (no pause)
    has_billable_side_resources: bool  # Cluster-create auto-provisions a billable side resource to sweep
    serverless: bool  # A serverless / elastic (pay-per-use) tier is available for this identity
    requires_tls: bool  # TLS is mandatory (managed clouds) vs optional (in-cluster dev / mesh TLS)
    auth_kind: AuthKind  # The credential family


@runtime_checkable
class KafkaProvider(Protocol):
    """The generic, open Kafka provider abstraction.

    Implement this for any provider - built-in or your own - to teach scalo
    its auth shape, capabilities, and (at their seams) transport tuning.
    Mirrors scalo-rs's ``KafkaProvider`` trait. A third party (e.g. AutoMQ)
    plugs in by implementing this Protocol - no change to scalo required.
    ``KnownProvider`` (below) implements it via ordinary duck typing (no
    inheritance needed) - that is what makes the abstraction OPEN.
    """

    def name(self) -> str:
        """A stable identifier (e.g. ``"confluent-cloud"``). Used in config + logs."""
        ...

    def auth(self) -> tuple[str, str]:
        """The auth shape: ``(security_protocol, sasl_mechanism)``.

        An empty mechanism means no SASL (the plaintext dev case). Values are
        librdkafka strings.
        """
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Behaviour flags that drive cost + lifecycle handling."""
        ...

    def metadata_mode(self) -> MetadataMode:
        """The metadata plane (KRaft / ZooKeeper / managed-hidden).

        Default: KRaft, the modern default. Self-hosted providers may run
        either; this is the recommended default.
        """
        return MetadataMode.KRAFT

    def schema_registry(self) -> SchemaRegistry:
        """A bundled schema registry, if the provider ships one. Default: none."""
        return SchemaRegistry.NONE

    def transport_overrides(self) -> dict[str, str]:
        """Provider-specific librdkafka overrides (transport tuning). Default: none."""
        return {}


class KnownProvider(Enum):
    """The built-in, generic providers. Implements ``KafkaProvider`` - the
    canonical facts, mirrored from scalo-rs's ``KnownProvider`` enum.
    """

    STRIMZI = "strimzi"  # Self-hosted Apache Kafka / Strimzi - SCRAM-SHA-512
    REDPANDA = "redpanda"  # Self-hosted Redpanda - SCRAM-SHA-512
    MSK = "msk"  # AWS MSK provisioned - SCRAM-SHA-512 (serverless is IAM-only: MSK_IAM)
    REDPANDA_CLOUD = "redpanda-cloud"  # Redpanda Cloud - SASL_SSL + SCRAM-SHA-512
    CONFLUENT_CLOUD = "confluent-cloud"  # Confluent Cloud - no SCRAM, API-key PLAIN over TLS
    PLAINTEXT = "plaintext"  # Local dev broker with no auth
    MSK_IAM = "msk_iam"  # Quarantined: IAM auth (OAUTHBEARER). MANDATORY for MSK Serverless.

    @classmethod
    def parse(cls, value: str) -> KnownProvider:
        """Parse a provider key. The string keys match scalo-rs + dfe-engine.

        Raises ``KafkaProviderError`` with the list of known providers for an
        unknown key.
        """
        try:
            return cls(value)
        except ValueError:
            raise KafkaProviderError(f"unknown kafka provider {value!r}; expected one of {KNOWN_PROVIDERS}") from None

    def name(self) -> str:  # type: ignore[override]
        """A stable identifier - the provider key itself (e.g. ``"strimzi"``).

        Deliberately shadows ``Enum.name`` (typeshed types it as a plain
        ``str`` property, hence the override waiver) so ``KnownProvider``
        satisfies ``KafkaProvider.name() -> str`` like every other provider -
        the enum's own member name is still reachable via ``self._name_``.
        """
        return self.value

    def auth(self) -> tuple[str, str]:
        """The auth shape, from the SAME table ``derive()`` uses above."""
        return derive(self.value)

    def capabilities(self) -> ProviderCapabilities:
        # Self-hosted: you run the broker - no managed billing, TLS is the
        # operator's choice (in-cluster mesh often terminates it).
        self_hosted = ProviderCapabilities(
            managed=False,
            always_on=False,
            has_billable_side_resources=False,
            serverless=False,
            requires_tls=False,
            auth_kind=AuthKind.USER_PASSWORD,
        )
        # Managed base: SaaS/cloud, always-on billing, TLS mandatory, elastic tier.
        managed = ProviderCapabilities(
            managed=True,
            always_on=True,
            has_billable_side_resources=False,
            serverless=True,
            requires_tls=True,
            auth_kind=AuthKind.USER_PASSWORD,
        )
        if self in (KnownProvider.STRIMZI, KnownProvider.REDPANDA):
            return self_hosted
        if self is KnownProvider.MSK:
            # Provisioned MSK: fixed broker-hour capacity (MSK Serverless is
            # the separate MSK_IAM identity).
            return replace(managed, serverless=False)
        if self is KnownProvider.REDPANDA_CLOUD:
            return managed
        if self is KnownProvider.CONFLUENT_CLOUD:
            # Cluster-create auto-provisions a billable Flink compute pool to sweep.
            return replace(managed, has_billable_side_resources=True)
        if self is KnownProvider.PLAINTEXT:
            return replace(self_hosted, requires_tls=False, auth_kind=AuthKind.NONE)
        # MSK_IAM: MSK Serverless / IAM-auth - managed, IAM credential family.
        return replace(managed, auth_kind=AuthKind.IAM)

    def metadata_mode(self) -> MetadataMode:
        # Redpanda is KRaft-native (no ZooKeeper); Strimzi + local dev default
        # to KRaft on modern Kafka; provisioned MSK is KRaft-forward.
        if self in (KnownProvider.REDPANDA, KnownProvider.STRIMZI, KnownProvider.PLAINTEXT, KnownProvider.MSK):
            return MetadataMode.KRAFT
        # The clouds hide their metadata plane entirely.
        return MetadataMode.MANAGED

    def schema_registry(self) -> SchemaRegistry:
        if self is KnownProvider.CONFLUENT_CLOUD:
            return SchemaRegistry.CONFLUENT
        if self in (KnownProvider.REDPANDA, KnownProvider.REDPANDA_CLOUD):
            return SchemaRegistry.REDPANDA
        return SchemaRegistry.NONE

    def transport_overrides(self) -> dict[str, str]:
        return {}
